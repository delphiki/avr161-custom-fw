"""set-volume (absolu) : tests COMPORTEMENTAUX par émulation du cave (cf. emu.py).
Design : un seul coup. On écrit le master à cible±pas (pas = 2 ou 4, prédit comme le fait
le firmware) puis UN pas volume-up/down via le dispatch stock -> atterrit PILE sur la cible. Si le pas est refusé
(gardes/cooldown), on restaure le master d'origine (pas de désync variable/matériel)."""
import pytest
import patchlib
import verifylib
from build_patch1 import build_patch1, STR_SETVOL
from patchlib import va_to_off
from emu import run_cmd

ALL = {"getstatus", "setvolume", "bluetooth"}


@pytest.fixture(scope="module")
def img():
    return build_patch1(patchlib.load_stock(), features=ALL)


def test_setvolume_string_intact_with_all_features(img):
    # Régression : "source-selection" écrasait la fin de "set-volume" -> jamais de match.
    o = va_to_off(STR_SETVOL)
    assert bytes(img[o:o + 11]) == b"set-volume\x00"


def test_set_volume_is_handled_by_cave_not_passed_to_stock(img):
    r = run_cmd(img, b"set-volume", b"82", master=110)
    assert r["clean"]
    assert [c[0] for c in r["stock_calls"]] == [b"volume-down"]   # pas b"set-volume"


def _reachable(cur, target, tmr):
    """Cible atteignable EXACTEMENT en un pas (hors butées 0/180)."""
    if cur > target:
        return target + (2 if tmr < 0xd else 4) <= 180
    st = 4 if (tmr >= 0xd and target <= 143) else 2
    return target - st >= 0


CASES = [(c, t, tmr) for tmr in (0, 0x0c, 0x0d, 0x14)
         for c in range(0, 181, 17) for t in range(0, 181, 7) if c != t]


def test_lands_exactly_on_target_in_a_single_step(img):
    bad = []
    for cur, target, tmr in CASES:
        r = run_cmd(img, b"set-volume", str(target).encode(), master=cur, tmr=tmr)
        ok = r["clean"] and len(r["stock_calls"]) == 1
        if _reachable(cur, target, tmr):
            ok = ok and r["master"] == target
        else:                                   # butée : au pire à un pas de la cible
            ok = ok and abs(r["master"] - target) <= 4
        if not ok:
            bad.append((cur, target, tmr, r["master"], r["clean"]))
    assert not bad, bad[:10]


@pytest.mark.parametrize("cur,target,tmr", [
    (110, 82, 0), (110, 82, 0x14), (82, 110, 0), (82, 110, 0x14), (83, 82, 0), (81, 82, 0x14),
    (100, 142, 0x14), (100, 143, 0x14), (100, 144, 0x14), (150, 160, 0x14), (180, 100, 0x14),
])
def test_exact_examples(img, cur, target, tmr):
    r = run_cmd(img, b"set-volume", str(target).encode(), master=cur, tmr=tmr)
    assert r["clean"] and r["master"] == target


def test_synth_command_carries_main_zone(img):
    r = run_cmd(img, b"set-volume", b"82", master=110)
    assert r["stock_calls"][0][1] == b"Main Zone"


def test_already_at_target_does_nothing(img):
    r = run_cmd(img, b"set-volume", b"82", master=82)
    assert r["clean"] and r["stock_calls"] == [] and r["master"] == 82


def test_refused_step_restores_original_master(img):
    # gardes/cooldown : le pas stock ne s'applique pas -> le master ne doit PAS rester pré-jumpé
    for cur, target in ((110, 82), (82, 110), (84, 82), (80, 82)):
        r = run_cmd(img, b"set-volume", str(target).encode(), master=cur, refuse=True)
        assert r["clean"]
        assert r["master"] == cur


def test_target_is_clamped_to_180(img):
    r = run_cmd(img, b"set-volume", b"999", master=100)
    assert r["clean"] and r["master"] == 180


def test_other_commands_still_reach_stock_untouched(img):
    r = run_cmd(img, b"volume-up", master=100)
    assert r["clean"] and r["stock_calls"] == [(b"volume-up", b"Main Zone", b"", 100)]


def test_no_collateral_changes():
    stock = patchlib.load_stock()
    out = build_patch1(bytearray(stock), features={"getstatus", "setvolume"})
    detour = set(range(0x4f328, 0x4f32c))
    cave = set(range(0xE0000, 0xE0400))
    verifylib.assert_only_changed(bytes(out), bytes(stock), detour | cave)


def test_set_volume_footprint_stays_within_proven_region():
    # Constat matériel (2026-11-13) : v1.0.3, premier build à occuper le cave entre +0x320 et
    # +0x333, a donné un service réseau mort au démarrage ; v1.0.2 (set_volume <= 0xa0 octets,
    # donc rien au-delà de +0x31f) fonctionne. Cause non élucidée -> on reste dans l'empreinte
    # prouvée tant que ce n'est pas compris.
    import build_patch1 as B
    sv = patchlib.asm_thumb(B._set_volume_src(), B.SET_VOLUME)
    assert len(sv) <= 0xa0, hex(len(sv))
