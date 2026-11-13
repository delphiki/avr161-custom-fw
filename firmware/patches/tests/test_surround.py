"""surround : lecture du mode surround (6e champ de get-status = mode appliqué, 7e = catégorie
mémorisée pour la source : 0 Auto Select, 1 virtuel, 2 stéréo, 3 NSP, 4 film, 5 musique,
6 jeu) et sélection directe par `set-surround <code>` (0..45, codes internes du firmware,
cf. NOTES.md) ou `set-surround auto` (retour à Auto Select).
La sélection passe par la fonction stock qui sert déjà au défilement des modes
(0x0803a434 : vérifie que le mode est possible avec le signal courant, le mémorise pour la
source courante, l'applique) ; le handler reprend les gardes de la commande stock
`surround-mode` (FUN_0801fe9c).
Tests COMPORTEMENTAUX par émulation du vrai code du cave."""
import pytest
import patchlib
import build_patch1 as B
from build_patch1 import build_patch1
from emu import run_getstatus, run_setsurround, run_tick, run_cmd

BASE = {"getstatus", "setvolume", "bluetooth", "keepsleep"}
ALL = BASE | {"surround"}
VER = "1.1.0-test"                     # la plus longue version prévue


@pytest.fixture(scope="module")
def img():
    return build_patch1(patchlib.load_stock(), features=ALL, version=VER)


@pytest.fixture(scope="module")
def img_push():
    return build_patch1(patchlib.load_stock(), features=ALL | {"push"}, version=VER)


def _para(r):
    assert r["clean"], r["err"]
    assert r["sent"] == 1 and len(r["replies"]) == 1
    return r["replies"][0][2]


# --- lecture ---

@pytest.mark.parametrize("mode", [0, 6, 22, 45])
def test_get_status_reports_the_applied_mode_as_sixth_field(img, mode):
    para = _para(run_getstatus(img, surround=mode, sur_cat=4))
    assert para == b"110,0,2,1.1.0-test,1," + str(mode).encode() + b",4"


@pytest.mark.parametrize("cat", [0, 1, 2, 6])
def test_get_status_reports_the_category_as_seventh_field(img, cat):
    assert _para(run_getstatus(img, surround=6, sur_cat=cat)).endswith(b",6," + str(cat).encode())


def test_longest_reply_fits(img):
    para = _para(run_getstatus(img, vol=180, mute=True, src=17, power=True, surround=45, sur_cat=6))
    assert para == b"180,1,17,1.1.0-test,1,45,6"
    assert len(para) + 1 <= B.PARA_BUF_SIZE


def test_without_the_feature_get_status_keeps_five_fields():
    out = build_patch1(patchlib.load_stock(), features=BASE, version=VER)
    assert _para(run_getstatus(out, surround=22)) == b"110,0,2,1.1.0-test,1"


# --- sélection directe ---

@pytest.mark.parametrize("para,mode", [(b"0", 0), (b"9", 9), (b"22", 22), (b"45", 45)])
def test_set_surround_asks_the_stock_selector_for_that_mode(img, para, mode):
    r = run_setsurround(img, para, current=6)
    assert r["clean"], r["err"]
    assert r["calls"] == [mode]
    assert r["busy"] == 10             # comme la commande stock : verrou anti-rebond armé


def test_a_refused_mode_still_returns_cleanly(img):
    r = run_setsurround(img, b"22", accept=False)
    assert r["clean"] and r["calls"] == [22]


def test_nothing_happens_when_the_mode_is_already_applied(img):
    r = run_setsurround(img, b"22", current=22)
    assert r["clean"] and r["calls"] == [] and r["busy"] == 0


@pytest.mark.parametrize("para", [b"46", b"47", b"255", b"256", b"99999999999", b"", b"abc", b"-1", b"a", b"aut", b"autos", b"Auto"])
def test_invalid_mode_is_ignored(img, para):
    r = run_setsurround(img, para)
    assert r["clean"], r["err"]
    assert r["calls"] == [] and r["busy"] == 0


@pytest.mark.parametrize("state", [
    dict(power=False),                 # ampli en sleep
    dict(pwr_bit3=True),               # bit 3 de 0x2000ddd4
    dict(transition=5),                # séquence d'allumage/extinction en cours
    dict(busy=3),                      # changement de source en cours
    dict(ddcc=0x80),                   # bit 7 de 0x2000ddcc
])
def test_stock_guards_block_the_change(img, state):
    r = run_setsurround(img, b"22", **state)
    assert r["clean"], r["err"]
    assert r["calls"] == []
    assert r["busy"] == state.get("busy", 0)


def test_set_surround_is_not_passed_to_the_stock_dispatcher(img):
    assert run_setsurround(img, b"22")["stock"] == 0


def test_without_the_feature_set_surround_falls_through_to_stock():
    out = build_patch1(patchlib.load_stock(), features=BASE, version=VER)
    r = run_setsurround(out, b"22")
    assert r["calls"] == [] and r["stock"] == 1


def test_other_commands_still_work(img):
    r = run_cmd(img, b"set-volume", b"82", master=110)
    assert r["clean"] and r["master"] == 82


# --- retour à Auto Select ---

def test_set_surround_auto_applies_the_mode_auto_select_would_pick(img):
    r = run_setsurround(img, b"auto", current=22, cat=5, auto_mode=6)
    assert r["clean"], r["err"]
    assert r["auto"] == [("pick", 1), ("apply", 6, 1)]
    assert r["calls"] == [] and r["busy"] == 10


def test_set_surround_auto_does_nothing_when_already_in_auto_select(img):
    r = run_setsurround(img, b"auto", current=6, cat=0)
    assert r["clean"] and r["auto"] == [] and r["busy"] == 0


@pytest.mark.parametrize("state", [dict(power=False), dict(transition=5), dict(busy=3)])
def test_stock_guards_also_block_auto(img, state):
    r = run_setsurround(img, b"auto", cat=5, **state)
    assert r["clean"] and r["auto"] == []


def test_a_numeric_mode_never_takes_the_auto_path(img):
    assert run_setsurround(img, b"22", cat=5)["auto"] == []


# --- push ---

def _snap(vol=110, flags=2, src=2, alive=B.PUSH_ALIVE_SECS, sur=6, cat=0):
    return bytes([vol, flags, src, 0xA5, alive, sur, cat, 0xff])


def test_push_when_the_surround_mode_changes(img_push):
    r = run_tick(img_push, push_ram=_snap(sur=6), surround=22)
    assert r["clean"], r["err"]
    assert [p for _, _, p in r["replies"]] == [b"110,0,2,1.1.0-test,1,22,0"]
    assert r["push_sur"] == 22


def test_no_push_when_the_surround_mode_is_unchanged(img_push):
    r = run_tick(img_push, push_ram=_snap(sur=22), surround=22)
    assert r["clean"] and r["sent"] == 0


def test_no_push_without_a_recent_client_but_state_is_resynced(img_push):
    r = run_tick(img_push, push_ram=_snap(sur=6, alive=0), surround=22)
    assert r["clean"] and r["sent"] == 0 and r["push_sur"] == 22


def test_volume_change_is_still_pushed_with_the_mode(img_push):
    r = run_tick(img_push, push_ram=_snap(sur=22), surround=22, vol=82)
    assert [p for _, _, p in r["replies"]] == [b"82,0,2,1.1.0-test,1,22,0"]


def test_push_when_only_the_category_changes(img_push):
    r = run_tick(img_push, push_ram=_snap(sur=22), surround=22, sur_cat=5)
    assert [p for _, _, p in r["replies"]] == [b"110,0,2,1.1.0-test,1,22,5"]
    assert r["push_cat"] == 5


def test_surround_routine_does_not_overlap_anything():
    # put() refuse tout chevauchement : construire toutes les features ensemble doit passer
    build_patch1(patchlib.load_stock(), features=ALL | {"push", "osdgreen"}, version=VER)
