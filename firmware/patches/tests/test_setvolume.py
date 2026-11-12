import patchlib
import verifylib
from build_patch1 import (build_patch1, SET_VOLUME, CAVE_DISPATCH, CMD_DISPATCH,
                          CAVE_VA)

FEATS = {"getstatus", "setvolume"}


def _sv_text(img):
    return "\n".join(verifylib.disasm(img, SET_VOLUME, 55))


def test_set_volume_calls_both_steps():
    img = build_patch1(patchlib.load_stock(), features=FEATS)
    t = _sv_text(img)
    assert hex(0x801b568) in t and hex(0x801b8f0) in t   # vol_up ET vol_down
    assert "0xe1b8" in t                                 # lit la variable volume live


def test_set_volume_loop_is_bounded_with_crossing_guard():
    img = build_patch1(patchlib.load_stock(), features=FEATS)
    t = _sv_text(img)
    assert "cmp r7, #0x80" in t          # borne dure : compteur <= 128
    # garde de croisement : deux comparaisons à la cible (r5) construisant was_below/now_below
    assert t.count("cmp r6, r5") >= 1 and t.count("cmp r0, r5") >= 1


def test_dispatch_checks_setvolume():
    img = build_patch1(patchlib.load_stock(), features=FEATS)
    t = "\n".join(verifylib.disasm(img, CAVE_DISPATCH, 24))
    assert hex(SET_VOLUME) in t          # bl vers set_volume
    assert hex(0x809534c) in t           # strcmp (pour "set-volume")


def test_no_collateral_changes():
    stock = patchlib.load_stock()
    img = build_patch1(bytearray(stock), features=FEATS)
    detour = set(range(0x4f328, 0x4f32c))          # 4 octets du b.w à cmd_dispatch
    cave = set(range(0xE0000, 0xE0400))            # plage cave utilisée
    verifylib.assert_only_changed(bytes(img), bytes(stock), detour | cave)
