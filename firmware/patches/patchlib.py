"""Helpers de build du patch firmware AVR 161/1610.

Image 1:1 : offset fichier = adresse flash - BASE. Tout code/donnée ajouté doit
rester dans la zone REECRITE par l'USB (0x10000..0xFFFFF). cf. ../re/NOTES.md.
"""
import os

BASE = 0x08000000
STOCK = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "AVR1610_USB(V002_20).fw")
IMG_SIZE = 6291456
# Zone réécrite par l'updater USB (offsets fichier). Hors d'elle = interdit (résident / composants).
REWRITE_LO = 0x10000
REWRITE_HI = 0x100000


def load_stock():
    with open(STOCK, "rb") as f:
        data = bytearray(f.read())
    assert len(data) == IMG_SIZE, f"taille stock inattendue: {len(data)}"
    return data


def _check_region(file_off, n, allow_outside):
    if allow_outside:
        return
    if not (REWRITE_LO <= file_off and file_off + n <= REWRITE_HI):
        raise ValueError(
            f"ecriture hors zone reecrite [{REWRITE_LO:#x},{REWRITE_HI:#x}): "
            f"[{file_off:#x},{file_off + n:#x})")


def write_bytes(img, file_off, data, allow_outside=False):
    """Ecrit `data` à l'offset fichier `file_off`. Lève ValueError si la plage
    sort de la zone réécrite (sauf allow_outside pour les cas documentés)."""
    data = bytes(data)
    _check_region(file_off, len(data), allow_outside)
    img[file_off:file_off + len(data)] = data
    return file_off + len(data)


def va_to_off(va):
    return va - BASE


def asm_thumb(src, va):
    """Assemble du Thumb-2 à la VA `va` (résout bl/b.w vers adresses absolues)."""
    from keystone import Ks, KS_ARCH_ARM, KS_MODE_THUMB, KS_MODE_LITTLE_ENDIAN
    ks = Ks(KS_ARCH_ARM, KS_MODE_THUMB | KS_MODE_LITTLE_ENDIAN)
    enc, _ = ks.asm(src, addr=va, as_bytes=True)
    return enc


def _insn_len_at(img, off):
    """Longueur de l'instruction Thumb à `off` (2 ou 4 octets)."""
    hw = img[off] | (img[off + 1] << 8)
    # Thumb-2 : préfixes 32-bit = 0b11101/0b11110/0b11111 sur bits [15:11]
    top5 = hw >> 11
    return 4 if top5 in (0b11101, 0b11110, 0b11111) else 2


def displaced_len(img, at_va, need=4):
    """Longueur (instructions entières) >= need à déplacer à at_va."""
    off = va_to_off(at_va)
    n = 0
    while n < need:
        n += _insn_len_at(img, off + n)
    return n


def detour(img, at_va, cave_va):
    """Ecrit un `b.w cave_va` à at_va (zone réécrite), pad le reste du/des
    instruction(s) déplacée(s) en nop. Renvoie les octets ORIGINAUX déplacés
    (à ré-exécuter dans le cave avant de revenir à at_va + len)."""
    L = displaced_len(img, at_va, need=4)
    off = va_to_off(at_va)
    original = bytes(img[off:off + L])
    branch = asm_thumb(f"b.w #{cave_va}", at_va)
    assert len(branch) == 4, f"b.w attendu 4 octets, obtenu {len(branch)}"
    nop = asm_thumb("nop", at_va + 4)  # 0x00bf
    patch = branch + nop * ((L - 4) // 2)
    assert len(patch) == L
    write_bytes(img, off, patch)
    return original


def save(img, path):
    assert len(img) == IMG_SIZE, f"taille image: {len(img)}"
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "wb") as f:
        f.write(bytes(img))
    return path
