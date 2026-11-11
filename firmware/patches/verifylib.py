"""Vérification statique de l'image patchée (capstone)."""
from patchlib import BASE, REWRITE_LO, REWRITE_HI, va_to_off


def diff_offsets(a, b):
    """Ensemble des offsets où a et b diffèrent (a et b de même taille)."""
    assert len(a) == len(b)
    return {i for i in range(len(a)) if a[i] != b[i]}


def assert_only_changed(patched, stock, allowed):
    """Lève si un offset hors de `allowed` a changé."""
    changed = diff_offsets(patched, stock)
    rogue = changed - set(allowed)
    if rogue:
        sample = sorted(rogue)[:16]
        raise AssertionError(
            f"{len(rogue)} octet(s) modifié(s) hors zone autorisée, ex: "
            + ", ".join(f"{o:#x}" for o in sample))
    return changed


def in_rewritten_region(va):
    off = va - BASE
    return REWRITE_LO <= off < REWRITE_HI


def disasm(img, va, n):
    """Désassemble n instructions Thumb à partir de la VA `va`."""
    from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    off = va_to_off(va)
    out = []
    for ins in md.disasm(bytes(img[off:off + n * 4 + 8]), va):
        out.append(f"{ins.address:#010x}: {ins.mnemonic} {ins.op_str}".rstrip())
        if len(out) >= n:
            break
    return out
