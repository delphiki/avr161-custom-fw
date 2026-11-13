"""keepsleep : l'ampli ne passe plus de « Device sleep » à « éteint complètement ».
Stock : à la mise en sleep, le firmware arme un compteur de 3600 s (0x2000dd7c) ; le tick
1 s (0x08010af6) le décrémente et, à zéro, lève le bit 7 de 0x2000dddc (extinction complète,
module réseau coupé — constaté sur matériel le 2026-11-13 : réseau perdu 60 min après
power-off). Patch : le tick saute le décompte ; le compteur ne s'écoule donc jamais.
Tests COMPORTEMENTAUX : on émule le vrai fragment du tick sur l'image construite."""
import struct
import pytest
from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS
from unicorn.arm_const import UC_ARM_REG_PC
import patchlib
import verifylib
from build_patch1 import build_patch1

TICK_BEGIN = 0x08010af6      # ldr r0,=timer ; ... (début du bloc de décompte)
TICK_END = 0x08010b40        # première instruction après le bloc
TIMER = 0x2000dd7c
OFF_FLAGS = 0x2000dddc       # bit 7 = éteint complètement
PATCH_SITE = range(0x10afe, 0x10b00)
ALL = {"getstatus", "setvolume", "bluetooth", "keepsleep"}


def run_tick(img, timer):
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    mu.mem_map(0x08000000, 0x100000)
    mu.mem_write(0x08000000, bytes(img[:0x100000]))
    mu.mem_map(0x20000000, 0x20000)
    mu.mem_write(TIMER, struct.pack("<I", timer))
    mu.emu_start(TICK_BEGIN | 1, TICK_END, count=1000)
    assert mu.reg_read(UC_ARM_REG_PC) == TICK_END
    return (struct.unpack("<I", bytes(mu.mem_read(TIMER, 4)))[0],
            bool(mu.mem_read(OFF_FLAGS, 1)[0] & 0x80))


@pytest.fixture(scope="module")
def stock():
    return patchlib.load_stock()


@pytest.fixture(scope="module")
def img():
    return build_patch1(patchlib.load_stock(), features=ALL)


def test_stock_timer_expiry_raises_full_off_flag(stock):
    # Garde-fou du modèle : sur le firmware d'origine, la dernière seconde éteint complètement.
    assert run_tick(stock, 1) == (0, True)
    assert run_tick(stock, 3600) == (3599, False)


@pytest.mark.parametrize("timer", [1, 2, 3600])
def test_patched_timer_never_counts_down_nor_raises_full_off(img, timer):
    assert run_tick(img, timer) == (timer, False)


def test_patched_idle_timer_is_untouched(img):
    assert run_tick(img, 0) == (0, False)


def test_without_feature_the_tick_is_stock(stock):
    out = build_patch1(patchlib.load_stock(), features=ALL - {"keepsleep"})
    assert bytes(out[0x10af6:0x10b40]) == bytes(stock[0x10af6:0x10b40])


def test_only_the_branch_changes_outside_the_cave(stock):
    out = build_patch1(patchlib.load_stock(), features={"keepsleep"})
    verifylib.assert_only_changed(bytes(out), bytes(stock), set(PATCH_SITE))
