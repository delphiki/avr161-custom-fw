import patchlib
import verifylib
from build_patch1 import build_testA, SRCNAME_OFF, SRCNAME_LEN, TESTA_STRING


def test_testA_changes_only_source_string():
    stock = patchlib.load_stock()
    img = build_testA(bytearray(stock))
    changed = verifylib.diff_offsets(bytes(img), stock)
    assert changed  # quelque chose a changé
    assert all(SRCNAME_OFF <= o < SRCNAME_OFF + SRCNAME_LEN for o in changed)
    assert len(img) == 6291456


def test_testA_new_string_visible_and_same_width():
    stock = patchlib.load_stock()
    img = build_testA(bytearray(stock))
    assert img[SRCNAME_OFF:SRCNAME_OFF + SRCNAME_LEN] == TESTA_STRING
    assert len(TESTA_STRING) == SRCNAME_LEN  # largeur OSD préservée
