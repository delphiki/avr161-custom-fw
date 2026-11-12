import patchlib
import verifylib
from build_patch1 import build_patch1, EMIT_STATUS, CAVE_DISPATCH, CMD_DISPATCH


def _cave_text(img):
    # emit_status (~234 o, ~80 instrs) + cave_dispatch (~16 instrs)
    return "\n".join(verifylib.disasm(img, EMIT_STATUS, 95)
                     + verifylib.disasm(img, CAVE_DISPATCH, 18))


def test_trampoline_is_bw_to_cave():
    img = build_patch1(patchlib.load_stock(), features={"getstatus"})
    first = verifylib.disasm(img, CMD_DISPATCH, 1)[0]
    assert "b.w" in first and hex(CAVE_DISPATCH)[2:] in first.replace("0x", "")


def test_all_changes_in_rewritten_region():
    stock = patchlib.load_stock()
    img = build_patch1(bytearray(stock), features={"getstatus"})
    for off in verifylib.diff_offsets(bytes(img), bytes(stock)):
        assert 0x10000 <= off < 0x100000, f"octet modifié hors zone réécrite: {off:#x}"


def test_getstatus_calls_reply_chain():
    img = build_patch1(patchlib.load_stock(), features={"getstatus"})
    t = _cave_text(img)
    for addr in (0x804fe7c, 0x8087e0c, 0x804fdd4, 0x80953b8, 0x8095408, 0x80953d0):
        assert hex(addr) in t, f"appel manquant vers {addr:#x}"


def test_getstatus_reads_state_and_arms_ctx():
    img = build_patch1(patchlib.load_stock(), features={"getstatus"})
    t = _cave_text(img)
    # état lu (demi-mots movw) : volume, mute, source
    assert "0xe1b8" in t and "0xde40" in t and "0xe1ae" in t
    # ctx "status_name" : armé (0xcb1c) >= 2 fois (set + restore), low de 0x80defc0 = 0xefc0
    assert t.count("0xcb1c") >= 2
    assert "0xefc0" in t
    # buffer sortant net_send
    assert "0xa0b4" in t


def test_cave_dispatch_matches_getstatus_and_returns():
    img = build_patch1(patchlib.load_stock(), features={"getstatus"})
    t = "\n".join(verifylib.disasm(img, CAVE_DISPATCH, 18))
    assert hex(0x809534c) in t                 # strcmp
    assert f"b.w #{hex(CMD_DISPATCH + 4)}" in t  # retour vers cmd_dispatch après prologue déplacé


def test_bl_targets_in_flash():
    img = build_patch1(patchlib.load_stock(), features={"getstatus"})
    for line in _cave_text(img).splitlines():
        s = line.split(": ", 1)[-1]
        if s.startswith("bl #") or s.startswith("b.w #"):
            tgt = int(s.split("#")[1], 16)
            assert 0x08000000 <= tgt < 0x08100000, f"cible hors flash: {tgt:#x}"
