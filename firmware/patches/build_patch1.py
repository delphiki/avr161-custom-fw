"""Build du firmware patché #1 (rempli task par task). cf. ../patches/DESIGN-patch1.md."""
import patchlib

CAVE_VA = 0x080E0000  # base du code-cave (zone réécrite, 128 Ko de 0xFF)

# --- Test A : patch cosmétique d'un nom de source OSD (preuve de récupération USB) ---
SRCNAME_OFF = 0xd9904            # flash 0x080d9904 : "USB" dans la table d'affichage source (0x8053684)
SRCNAME_LEN = 16                 # largeur fixe OSD
_STOCK_SRCNAME = b"USB             "
TESTA_STRING = b"USB [PATCH1]    "  # 16 octets, largeur préservée, visible via `ampli.py source USB`


def build_testA(img):
    """Change UNIQUEMENT le nom OSD de la source USB (changement cosmétique observable)."""
    assert len(TESTA_STRING) == SRCNAME_LEN
    cur = bytes(img[SRCNAME_OFF:SRCNAME_OFF + SRCNAME_LEN])
    assert cur == _STOCK_SRCNAME, f"chaîne source inattendue à {SRCNAME_OFF:#x}: {cur!r}"
    patchlib.write_bytes(img, SRCNAME_OFF, TESTA_STRING)
    return img
