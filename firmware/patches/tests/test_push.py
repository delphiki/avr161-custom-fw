"""push : l'ampli envoie de lui-même son état (même message que la réponse à get-status)
quand volume, mute, source ou alimentation changent, tant qu'un client s'est manifesté
récemment. Mécanisme : le bloc « tick 1 s » de la boucle principale appelle push_tick, qui
compare l'état courant au dernier état envoyé (mémorisé à PUSH_RAM, RAM inutilisée
au-dessus de la pile) ; chaque commande reçue réarme un compteur « client vivant ».
Tests COMPORTEMENTAUX par émulation du vrai code (cf. emu.run_tick)."""
import pytest
import patchlib
import verifylib
import build_patch1 as B
from build_patch1 import build_patch1
from emu import run_tick, run_cmd, run_getstatus

ALL = {"getstatus", "setvolume", "bluetooth", "keepsleep", "push"}
VER = "9.9.9"
MAGIC = 0xA5


def snap(vol=110, mute=False, src=2, power=True, alive=B.PUSH_ALIVE_SECS):
    return bytes([vol, (1 if mute else 0) | (2 if power else 0), src, MAGIC, alive])


@pytest.fixture(scope="module")
def img():
    return build_patch1(patchlib.load_stock(), features=ALL, version=VER)


def test_no_push_when_nothing_changed(img):
    r = run_tick(img, push_ram=snap())
    assert r["clean"] and r["sent"] == 0 and r["replies"] == []


@pytest.mark.parametrize("change,para", [
    (dict(vol=82), b"82,0,2,9.9.9,1"),
    (dict(mute=True), b"110,1,2,9.9.9,1"),
    (dict(src=17), b"110,0,17,9.9.9,1"),
    (dict(power=False), b"110,0,2,9.9.9,0"),
])
def test_one_push_per_state_change(img, change, para):
    r = run_tick(img, push_ram=snap(), **change)
    assert r["clean"], r["err"]
    assert r["sent"] == 1
    assert r["replies"] == [(b"get-status", b"Main Zone", para)]


def test_snapshot_updated_so_the_next_tick_is_silent(img):
    r1 = run_tick(img, push_ram=snap(), vol=82)
    assert r1["push_ram"][:4] == snap(vol=82)[:4]
    r2 = run_tick(img, push_ram=r1["push_ram"], vol=82)
    assert r2["clean"] and r2["sent"] == 0


def test_alive_counter_counts_down_each_tick(img):
    r = run_tick(img, push_ram=snap(alive=5))
    assert r["push_ram"][4] == 4


def test_no_push_without_a_recent_client(img):
    r = run_tick(img, push_ram=snap(alive=0), vol=82)
    assert r["clean"] and r["sent"] == 0
    assert r["push_ram"] == snap(vol=82, alive=0)      # état resynchronisé, compteur à 0


def test_uninitialised_ram_is_initialised_without_pushing(img):
    r = run_tick(img, push_ram=None, vol=82, mute=True, src=17, power=False)
    assert r["clean"] and r["sent"] == 0
    assert r["push_ram"] == snap(vol=82, mute=True, src=17, power=False, alive=0)


def test_last_alive_second_still_pushes_then_stops(img):
    r = run_tick(img, push_ram=snap(alive=1), vol=82)
    assert r["sent"] == 1 and r["push_ram"][4] == 0


def test_any_incoming_command_rearms_the_alive_counter(img):
    assert run_cmd(img, b"volume-up", master=100)["alive"] == B.PUSH_ALIVE_SECS
    assert run_cmd(img, b"heart-alive")["alive"] == B.PUSH_ALIVE_SECS
    assert run_getstatus(img)["alive"] == B.PUSH_ALIVE_SECS


def test_commands_still_behave_with_push_enabled(img):
    r = run_cmd(img, b"set-volume", b"82", master=110)
    assert r["clean"] and r["master"] == 82
    g = run_getstatus(img, vol=110, mute=False, src=2, power=True)
    assert g["clean"] and g["replies"] == [(b"get-status", b"Main Zone", b"110,0,2,9.9.9,1")]


def test_sleep_timer_still_never_expires(img):
    for timer in (1, 3600):
        r = run_tick(img, push_ram=snap(), timer=timer)
        assert r["clean"] and r["timer"] == timer and not r["off_flag"]


def test_only_expected_regions_change():
    stock = patchlib.load_stock()
    out = build_patch1(bytearray(stock), features=ALL, version=VER)
    allowed = (set(range(0x10af6, 0x10b00)) | set(range(0x4f328, 0x4f32c))
               | set(range(0xE0000, 0xE0400)))
    verifylib.assert_only_changed(bytes(out), bytes(stock), allowed)


def test_push_requires_keepsleep_and_getstatus():
    with pytest.raises(ValueError):
        build_patch1(patchlib.load_stock(), features={"getstatus", "push"})
    with pytest.raises(ValueError):
        build_patch1(patchlib.load_stock(), features={"keepsleep", "push"})
