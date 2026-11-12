import patchlib
import verifylib
from build_patch1 import (build_patch1, BT_HANDLER, CAVE_DISPATCH,
                          STR_SOURCESEL, STR_BLUETOOTH)
from patchlib import va_to_off

FEATS = {"getstatus", "setvolume", "bluetooth"}


def test_bt_handler_replicates_homenetwork_pattern():
    img = build_patch1(patchlib.load_stock(), features=FEATS)
    t = "\n".join(verifylib.disasm(img, BT_HANDLER, 16))
    assert "0xe1ab" in t              # pose g_src_switch_flag = 0x19
    assert "0x19" in t
    assert hex(0x801af34) in t        # set_src_Bluetooth
    assert hex(0x8018944) in t        # post-step (comme HomeNetwork)


def test_dispatch_checks_source_selection_and_bluetooth():
    img = build_patch1(patchlib.load_stock(), features=FEATS)
    t = "\n".join(verifylib.disasm(img, CAVE_DISPATCH, 40))
    assert hex(BT_HANDLER) in t       # bl vers bt_handler
    # para lu à struct+0x40 (le add.w r0, r4, #0x40 avant le 2e strcmp)
    assert "r4, #0x40" in t


def test_bt_strings_embedded():
    img = build_patch1(patchlib.load_stock(), features=FEATS)
    off_ss = va_to_off(STR_SOURCESEL)
    off_bt = va_to_off(STR_BLUETOOTH)
    assert img[off_ss:off_ss + 17] == b"source-selection\x00"
    assert img[off_bt:off_bt + 10] == b"Bluetooth\x00"


def test_no_collateral_changes_full():
    stock = patchlib.load_stock()
    img = build_patch1(bytearray(stock), features=FEATS)
    detour = set(range(0x4f328, 0x4f32c))
    cave = set(range(0xE0000, 0xE0400))
    verifylib.assert_only_changed(bytes(img), bytes(stock), detour | cave)
