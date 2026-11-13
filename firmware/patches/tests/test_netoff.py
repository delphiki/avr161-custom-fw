"""netoff : le module réseau reste alimenté quand l'ampli est complètement éteint.
Le convertisseur du module est sur le rail de veille ST+5V ; seule la sortie NET_PWR_SW (PD9)
le coupe, et BCO_RST (PD8) le maintient en reset. La séquence d'extinction FUN_0801396c fait,
quand l'extinction complète est demandée (bit 7 de 0x2000dddc) :
  pas 0xc6 : PD9 = 0 puis PD8 = 0   (en sleep : PD9 = 1)
  pas 0xaf : PD9 = 0 parmi une cinquantaine de sorties.
Patch : au pas 0xc6 on prend toujours la branche « sleep » pour ces deux sorties (PD9 = 1) ;
au pas 0xaf, 23 pas plus tard, la mise à 0 de PD9 devient une mise à 1 de PD8 (sortie de reset).
Ce second point compte au rebranchement secteur : l'ampli démarre en veille en déroulant cette
même séquence, avec PD8 encore bas ; sans lui le module serait alimenté mais figé en reset.
Rien d'autre ne change dans la séquence.
Tests COMPORTEMENTAUX : on exécute la vraie séquence et on compare ses écritures GPIO."""
import pytest
import patchlib
import verifylib
from build_patch1 import build_patch1
from emu import run_power_step

NET_PWR = ("D", 0x200)        # PD9
NET_RST = ("D", 0x100)        # PD8
BASE = {"getstatus", "setvolume", "bluetooth", "keepsleep"}


@pytest.fixture(scope="module")
def stock():
    return patchlib.load_stock()


@pytest.fixture(scope="module")
def img():
    return build_patch1(patchlib.load_stock(), features=BASE | {"netoff"})


def _on(writes, pin):
    return [kind for port, kind, mask in writes if (port, mask) == pin]


def test_stock_full_off_cuts_and_resets_the_network_module(stock):
    # garde-fou du modèle : c'est bien ce que fait le firmware d'origine
    w = run_power_step(stock, 0xc6, full_off=True)
    assert _on(w, NET_PWR) == ["clr"] and _on(w, NET_RST) == ["clr"]
    assert _on(run_power_step(stock, 0xaf, full_off=True), NET_PWR) == ["clr"]


def test_stock_sleep_keeps_the_network_module_powered(stock):
    w = run_power_step(stock, 0xc6, full_off=False)
    assert _on(w, NET_PWR) == ["set"] and _on(w, NET_RST) == []
    assert _on(run_power_step(stock, 0xaf, full_off=False), NET_PWR) == []


def test_full_off_powers_the_module_then_releases_its_reset(img):
    w = run_power_step(img, 0xc6, full_off=True)
    assert _on(w, NET_PWR) == ["set"] and _on(w, NET_RST) == []      # alimenté, reset pas encore touché
    w = run_power_step(img, 0xaf, full_off=True)
    assert _on(w, NET_PWR) == [] and _on(w, NET_RST) == ["set"]      # 23 pas plus tard : sortie de reset


def test_reset_release_keeps_its_place_in_the_step(stock, img):
    # la mise à 1 de PD8 remplace exactement la mise à 0 de PD9, au même rang
    before = run_power_step(stock, 0xaf, full_off=True)
    after = run_power_step(img, 0xaf, full_off=True)
    i = before.index(("D", "clr", 0x200))
    assert after[i] == ("D", "set", 0x100) and after[:i] == before[:i] and after[i + 1:] == before[i + 1:]


@pytest.mark.parametrize("step", [0xc6, 0xaf])
@pytest.mark.parametrize("de40", [0x00, 0x01])
def test_full_off_changes_nothing_else_in_the_sequence(stock, img, step, de40):
    before = [w for w in run_power_step(stock, step, True, de40) if (w[0], w[2]) not in (NET_PWR, NET_RST)]
    after = [w for w in run_power_step(img, step, True, de40) if (w[0], w[2]) not in (NET_PWR, NET_RST)]
    assert after == before and len(before) >= 1


@pytest.mark.parametrize("step", [0xc6, 0xaf])
def test_sleep_sequence_is_unchanged(stock, img, step):
    assert run_power_step(img, step, full_off=False) == run_power_step(stock, step, full_off=False)


def test_without_the_feature_the_sequence_is_stock(stock):
    out = build_patch1(patchlib.load_stock(), features=BASE)
    assert bytes(out[0x1410c:0x1410e]) == bytes(stock[0x1410c:0x1410e])
    assert bytes(out[0x14312:0x1431e]) == bytes(stock[0x14312:0x1431e])


def test_only_six_bytes_change(stock):
    out = build_patch1(patchlib.load_stock(), features={"netoff"})
    # hors du cave et du détour du dispatch (pour la commande power-full-off)
    allowed = (set(range(0x1410c, 0x1410e)) | set(range(0x14312, 0x1431e))
               | set(range(0x4f328, 0x4f32c)) | set(range(0xe0000, 0xe0700)))
    changed = verifylib.assert_only_changed(bytes(out), bytes(stock), allowed)
    assert 1 <= len([o for o in changed if o < 0x4f328]) <= 10


# --- commande power-full-off : extinction complète immédiate (comme l'ordre de veille HDMI-CEC)

from emu import run_fulloff


def test_power_full_off_requests_the_full_power_down_like_cec_standby(img):
    r = run_fulloff(img, power=True, dddc=0x21, dde0=0xff)
    assert r["clean"], r["err"]
    assert r["dddc"] == 0xa1           # bit 7 posé, autres bits intacts
    assert r["dde0"] == 0xfd           # bit 1 baissé
    assert r["delay"] == 100           # action différée armée


def test_power_full_off_also_works_from_sleep(img):
    r = run_fulloff(img, power=False, sleep_timer=3600)
    assert r["clean"] and r["dddc"] & 0x80 and r["delay"] == 100


def test_power_full_off_does_nothing_when_already_fully_off(img):
    r = run_fulloff(img, power=False, sleep_timer=0, dddc=0x00)
    assert r["clean"] and r["dddc"] == 0x00 and r["delay"] == 0 and r["dde0"] == 0xff


def test_power_full_off_is_not_passed_to_the_stock_dispatcher(img):
    assert run_fulloff(img)["stock"] == 0


def test_without_the_feature_power_full_off_falls_through_to_stock():
    out = build_patch1(patchlib.load_stock(), features=BASE)
    r = run_fulloff(out)
    assert r["stock"] == 1 and r["delay"] == 0


def test_all_features_build_together():
    build_patch1(patchlib.load_stock(), version="1.2.0-test",
                 features=BASE | {"push", "osdgreen", "surround", "netoff"})
