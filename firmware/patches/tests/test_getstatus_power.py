"""get-status : 5e champ = état d'alimentation (1 = allumé, 2 = en veille, 0 = éteint). Allumé :
bit 1 de 0x2000ddd4 ; en veille : bit 1 de 0x2000dde0, que la fin de la temporisation de veille
efface (lu sur matériel : allumé 0x40, veille 0x03, éteint 0x01).
Tests COMPORTEMENTAUX : le vrai cave et les vraies fonctions utilitaires du firmware sont
émulés ; seuls build_reply et net_send sont interceptés (cf. emu.run_getstatus)."""
import pytest
import patchlib
from build_patch1 import build_patch1, FW_VERSION, EMIT_STATUS, CAVE_DISPATCH
from emu import run_getstatus, run_cmd

ALL = {"getstatus", "setvolume", "bluetooth", "keepsleep"}
FW = FW_VERSION.encode()


@pytest.fixture(scope="module")
def img():
    return build_patch1(patchlib.load_stock(), features=ALL)


@pytest.fixture(scope="module")
def img3():
    return build_patch1(patchlib.load_stock(), features=ALL | {"powerstate"})


def _para(r):
    assert r["clean"], r["err"]
    assert r["sent"] == 1 and len(r["replies"]) == 1
    name, zone, para = r["replies"][0]
    assert (name, zone) == (b"get-status", b"Main Zone")
    assert r["ctx_cleared"]
    return para


def test_reports_power_on_as_fifth_field(img):
    assert _para(run_getstatus(img, vol=110, mute=False, src=2, power=True)) == b"110,0,2," + FW + b",1"


def test_reports_off_as_zero(img3):
    assert _para(run_getstatus(img3, vol=110, mute=False, src=2, power=False, sleep_flags=0x01)) == b"110,0,2," + FW + b",0"


def test_reports_sleep_as_two(img3):
    assert _para(run_getstatus(img3, vol=110, mute=False, src=2, power=False, sleep_flags=0x03)) == b"110,0,2," + FW + b",2"


def test_reports_on_as_one(img3):
    assert _para(run_getstatus(img3, vol=110, mute=False, src=2, power=True, sleep_flags=0x40)) == b"110,0,2," + FW + b",1"


def test_an_amp_that_is_on_is_never_reported_asleep(img3):
    assert _para(run_getstatus(img3, power=True, sleep_flags=0xff)).endswith(b",1")


def test_sleep_ignores_the_other_flag_bits(img3):
    assert _para(run_getstatus(img3, power=False, sleep_flags=0xfd)).endswith(b",0")
    assert _para(run_getstatus(img3, power=False, sleep_flags=0x02)).endswith(b",2")


def test_without_powerstate_sleep_and_off_both_read_zero(img):
    for flags in (0x01, 0x03):
        assert _para(run_getstatus(img, power=False, sleep_flags=flags)).endswith(b",0")


def test_power_field_ignores_the_other_flag_bits(img):
    assert _para(run_getstatus(img, power=False, other_flags=0xfd)).endswith(b",0")
    assert _para(run_getstatus(img, power=True, other_flags=0x00)).endswith(b",1")


def test_powerstate_needs_getstatus():
    with pytest.raises(ValueError):
        build_patch1(patchlib.load_stock(), features={"powerstate"})


@pytest.mark.parametrize("vol,mute,src", [(0, False, 0), (180, True, 17), (7, True, 9), (99, False, 13)])
def test_first_four_fields_unchanged(img, vol, mute, src):
    para = _para(run_getstatus(img, vol=vol, mute=mute, src=src))
    assert para.split(b",")[:4] == [str(vol).encode(), b"1" if mute else b"0", str(src).encode(), FW]


def test_longest_reply_fits_and_returns_cleanly(img):
    # 180,1,17,<version>,1 : la plus longue réponse ne doit ni déborder ni corrompre la pile
    para = _para(run_getstatus(img, vol=180, mute=True, src=17, power=True))
    assert para == b"180,1,17," + FW + b",1"


def test_emit_status_stays_in_its_slot():
    import build_patch1 as B
    for power_state in (False, True):
        src = B._emit_status_src(surround=True, power_state=power_state)
        assert len(patchlib.asm_thumb(src, EMIT_STATUS)) <= CAVE_DISPATCH - EMIT_STATUS


def test_set_volume_still_works_next_to_it(img):
    r = run_cmd(img, b"set-volume", b"82", master=110)
    assert r["clean"] and r["master"] == 82
