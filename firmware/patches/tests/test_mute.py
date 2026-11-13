"""mute : le son coupé est le bit 4 de 0x2000dddc (FUN_0801b030 le bascule ; le chemin HDMI-CEC
FUN_0802a340 le teste). Constaté sur matériel le 2026-11-14 : après `mute-on`, get-status
(qui lisait le bit 1 de 0x2000de40) annonçait toujours 0.
Deuxième constat, dans le code d'origine : `mute-on`, `mute-off` et `mute-toggle` appellent
tous la même bascule. Avec la feature `mute`, `mute-on` et `mute-off` deviennent de vraies
consignes : la commande n'atteint la bascule d'origine que si l'état doit changer."""
import pytest
import patchlib
from build_patch1 import build_patch1
from emu import run_getstatus, run_tick, run_mute
import build_patch1 as B

BASE = {"getstatus", "setvolume", "bluetooth", "keepsleep"}
VER = "9.9.9"


@pytest.fixture(scope="module")
def img():
    return build_patch1(patchlib.load_stock(), features=BASE | {"mute", "push"}, version=VER)


def _para(r):
    assert r["clean"], r["err"]
    return r["replies"][0][2]


def test_get_status_reports_muted_from_the_real_flag(img):
    assert _para(run_getstatus(img, mute=True)).split(b",")[1] == b"1"
    assert _para(run_getstatus(img, mute=False)).split(b",")[1] == b"0"


def test_get_status_mute_ignores_the_other_bits_of_that_byte(img):
    assert _para(run_getstatus(img, mute=False, other_flags=0x6f)).split(b",")[1] == b"0"
    assert _para(run_getstatus(img, mute=True, other_flags=0x00)).split(b",")[1] == b"1"


def test_push_fires_when_mute_changes(img):
    snap = bytes([110, 2, 2, 0xA5, B.PUSH_ALIVE_SECS, 0, 0, 0xff])          # mémorisé : non coupé, allumé
    r = run_tick(img, push_ram=snap, mute=True)
    assert r["clean"] and [p for _, _, p in r["replies"]] == [b"110,1,2,9.9.9,1"]
    assert run_tick(img, push_ram=snap, mute=False)["sent"] == 0


@pytest.mark.parametrize("name,muted,reaches_toggle", [
    (b"mute-on", False, True),       # pas coupé -> basculer
    (b"mute-on", True, False),       # déjà coupé -> rien
    (b"mute-off", True, True),
    (b"mute-off", False, False),
    (b"mute-toggle", False, True),   # la bascule reste une bascule
    (b"mute-toggle", True, True),
])
def test_mute_on_and_off_only_reach_the_stock_toggle_when_needed(img, name, muted, reaches_toggle):
    r = run_mute(img, name, muted)
    assert r["err"] is None
    assert r["stock"] == reaches_toggle and r["swallowed"] == (not reaches_toggle)
    assert r["flags"] == 0x41 | (0x10 if muted else 0)       # le cave ne modifie pas l'indicateur lui-même


def test_without_the_feature_mute_on_always_reaches_the_stock_toggle():
    out = build_patch1(patchlib.load_stock(), features=BASE, version=VER)
    assert run_mute(out, b"mute-on", True)["stock"] and run_mute(out, b"mute-off", False)["stock"]
