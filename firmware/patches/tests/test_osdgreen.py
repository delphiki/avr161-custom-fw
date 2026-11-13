"""osdgreen : le bleu du menu à l'écran devient vert, pour reconnaître d'un coup d'œil un
firmware custom. Les couleurs (6 bits RRGGBB) viennent des ressources de fenêtre, lues par
FUN_08096598 puis recopiées dans la structure de fenêtre (sl) : +0x32 texte, +0x33 fond,
+0x34/+0x35 ligne sélectionnée, +0x36/+0x37 ligne désactivée, +0x38 bordure, +0x39 séparateur.
Le patch détourne le `bl memcpy` qui suit ces copies (0x080967dc) vers une routine du cave
qui remplace les bleus connus, puis enchaîne sur memcpy.
Tests COMPORTEMENTAUX : on émule la vraie routine sur l'image construite."""
import pytest
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                               UC_ARM_REG_R4, UC_ARM_REG_R10, UC_ARM_REG_SP, UC_ARM_REG_LR,
                               UC_ARM_REG_PC)
import patchlib
import verifylib
from build_patch1 import build_patch1

HOOK = 0x080967dc            # bl memcpy (stock), après la copie des 8 couleurs
MEMCPY = 0x080a7e14
MSGBOX_TITLE = 0x0809761e    # movs r2,#3 : couleur du titre des boîtes de message
MSGBOX_BORDER = 0x08097644   # movs r2,#3 : bordure des boîtes de message
WIN = 0x20010000
SP0 = 0x2001f000
ALL = {"getstatus", "setvolume", "bluetooth", "keepsleep", "osdgreen"}
# bleu d'origine -> vert
EXPECTED = {0x07: 0x08, 0x0b: 0x0c, 0x03: 0x08, 0x1b: 0x1d, 0x16: 0x19}


def run_hook(img, colors):
    """Exécute le site détourné avec `colors` (8 octets) dans la structure de fenêtre.
    Retourne (couleurs après, octets voisins, registres à l'entrée de memcpy)."""
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    mu.mem_map(0x08000000, 0x100000)
    mu.mem_write(0x08000000, bytes(img[:0x100000]))
    mu.mem_map(0x20000000, 0x20000)
    mu.mem_write(WIN + 0x31, b"\x07" + bytes(colors) + b"\x07")   # voisins « bleus » à ne pas toucher
    regs = {UC_ARM_REG_R0: 0x11111111, UC_ARM_REG_R1: 0x22222222, UC_ARM_REG_R2: 0x10,
            UC_ARM_REG_R3: 0x33333333, UC_ARM_REG_R4: 0x44444444, UC_ARM_REG_R10: WIN,
            UC_ARM_REG_SP: SP0, UC_ARM_REG_LR: 0xdeadbeef}
    for r, v in regs.items():
        mu.reg_write(r, v)
    seen = {}

    def at_memcpy(mu, addr, size, ud):
        seen.update({r: mu.reg_read(r) for r in regs})
        mu.emu_stop()

    mu.hook_add(UC_HOOK_CODE, at_memcpy, begin=MEMCPY, end=MEMCPY)
    mu.emu_start(HOOK | 1, 0, count=2000)
    assert seen, "memcpy jamais atteint"
    return bytes(mu.mem_read(WIN + 0x32, 8)), bytes(mu.mem_read(WIN + 0x31, 1) + mu.mem_read(WIN + 0x3a, 1)), seen


@pytest.fixture(scope="module")
def img():
    return build_patch1(patchlib.load_stock(), features=ALL)


@pytest.mark.parametrize("blue,green", sorted(EXPECTED.items()))
def test_each_stock_blue_becomes_green_in_every_colour_slot(img, blue, green):
    after, _, _ = run_hook(img, [blue] * 8)
    assert after == bytes([green] * 8)


@pytest.mark.parametrize("colour", [0x00, 0x3f, 0x15, 0x2a, 0x0f, 0x3c, 0x08, 0x0c])
def test_other_colours_are_left_alone(img, colour):
    after, _, _ = run_hook(img, [colour] * 8)
    assert after == bytes([colour] * 8)


def test_real_menu_window_colours(img):
    # fenêtre de menu stock : texte blanc sur noir, barre de sélection 0x07, grisé 0x15
    after, _, _ = run_hook(img, [0x3f, 0x00, 0x3f, 0x07, 0x15, 0x00, 0x00, 0x00])
    assert after == bytes([0x3f, 0x00, 0x3f, 0x08, 0x15, 0x00, 0x00, 0x00])


def test_bytes_next_to_the_colours_are_untouched(img):
    _, neighbours, _ = run_hook(img, [0x07] * 8)
    assert neighbours == b"\x07\x07"


def test_memcpy_is_reached_with_the_stock_arguments_and_return_address(img):
    _, _, regs = run_hook(img, [0x07] * 8)
    assert regs[UC_ARM_REG_R0] == 0x11111111
    assert regs[UC_ARM_REG_R1] == 0x22222222
    assert regs[UC_ARM_REG_R2] == 0x10
    assert regs[UC_ARM_REG_R3] == 0x33333333
    assert regs[UC_ARM_REG_R4] == 0x44444444
    assert regs[UC_ARM_REG_R10] == WIN
    assert regs[UC_ARM_REG_SP] == SP0
    assert regs[UC_ARM_REG_LR] == (HOOK + 4) | 1


def test_message_boxes_use_green_instead_of_blue(img):
    for va in (MSGBOX_TITLE, MSGBOX_BORDER):
        off = va - 0x08000000
        assert bytes(img[off:off + 2]) == patchlib.asm_thumb("movs r2, #8", va)


def test_without_the_feature_the_osd_code_is_stock():
    stock = patchlib.load_stock()
    out = build_patch1(patchlib.load_stock(), features=ALL - {"osdgreen"})
    for lo, hi in ((0x967dc, 0x967e0), (0x9761e, 0x97620), (0x97644, 0x97646)):
        assert bytes(out[lo:hi]) == bytes(stock[lo:hi])


def test_only_the_three_sites_change_outside_the_cave():
    stock = patchlib.load_stock()
    out = build_patch1(patchlib.load_stock(), features={"osdgreen"})
    sites = set(range(0x967dc, 0x967e0)) | {0x9761e, 0x97644}
    cave = set(range(0xe0400, 0xe0480))
    verifylib.assert_only_changed(bytes(out), bytes(stock), sites | cave)
