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
from emu import run_power_step, DEEP_ARMED, DEEP_ACTIVE

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


ANY_RAM = (0, 0xffffffff, 0x12345678, 0x4e455453)   # RAM quelconque après une mise sous tension
DEEP = (DEEP_ARMED, DEEP_ACTIVE)


@pytest.mark.parametrize("flag", ANY_RAM)
def test_full_off_powers_the_module_then_releases_its_reset(img, flag):
    # comportement PAR DÉFAUT (y compris au rebranchement secteur, RAM quelconque)
    w = run_power_step(img, 0xc6, full_off=True, flag=flag)
    assert _on(w, NET_PWR) == ["set"] and _on(w, NET_RST) == []      # alimenté, reset pas encore touché
    w = run_power_step(img, 0xaf, full_off=True, flag=flag)
    assert _on(w, NET_PWR) == [] and _on(w, NET_RST) == ["set"]      # 23 pas plus tard : sortie de reset


@pytest.mark.parametrize("step", [0xc6, 0xaf])
@pytest.mark.parametrize("flag", DEEP)
def test_deep_off_is_exactly_stock(stock, img, step, flag):
    # Constat sur matériel (2026-11-14) : module laissé alimenté pendant que le MCU dort ->
    # au rallumage le port de commande ne répond plus. L'extinction profonde coupe donc le
    # module ET laisse dormir le MCU, exactement comme le firmware d'origine.
    assert run_power_step(img, step, full_off=True, flag=flag) == run_power_step(stock, step, full_off=True)


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
@pytest.mark.parametrize("flag", [0x12345678, DEEP_ARMED, DEEP_ACTIVE])
def test_sleep_sequence_is_unchanged(stock, img, step, flag):
    assert run_power_step(img, step, full_off=False, flag=flag) == run_power_step(stock, step, full_off=False)


def test_without_the_feature_the_sequence_is_stock(stock):
    out = build_patch1(patchlib.load_stock(), features=BASE)
    assert bytes(out[0x1410c:0x14126]) == bytes(stock[0x1410c:0x14126])
    assert bytes(out[0x14312:0x1431e]) == bytes(stock[0x14312:0x1431e])


def test_only_six_bytes_change(stock):
    out = build_patch1(patchlib.load_stock(), features={"netoff"})
    # hors du cave et du détour du dispatch (pour la commande power-full-off)
    allowed = (set(range(0x14116, 0x14126)) | set(range(0x1431a, 0x1431e)) | set(range(0x146b4, 0x146b8))
               | set(range(0x4f328, 0x4f32c)) | set(range(0x74ef2, 0x74ef6))   # entrée de la reconfiguration réseau
               | set(range(0xe0000, 0xe0900)))
    changed = verifylib.assert_only_changed(bytes(out), bytes(stock), allowed)
    assert 1 <= len([o for o in changed if o < 0x4f328]) <= 16


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


# --- le MCU reste éveillé une fois éteint, pour répondre au réseau -----------------------------
# Constats sur matériel (2026-11-14) : une fois l'extinction finie, FUN_080146b4 met le MCU en
# mode STOP (réveil par interruption externe) et il ne répond plus au module réseau. Mise en
# sommeil sautée : 8 h éteint, 480 pings et 32 lectures d'état sans une perte, rallumage par le
# réseau. C'est donc le comportement par défaut. `power-full-off deep` redonne l'extinction
# d'origine (module coupé, MCU en STOP) jusqu'au prochain allumage.

from emu import run_stop_entry, run_tick


def test_stock_stop_entry_reaches_the_stop_call(stock):
    r = run_stop_entry(stock, 0)                      # garde-fou du modèle
    assert r["stopped"] and r["clean"]


@pytest.mark.parametrize("flag", ANY_RAM)
def test_by_default_the_mcu_stays_awake_and_touches_nothing(img, flag):
    r = run_stop_entry(img, flag)
    assert r["clean"] and not r["stopped"] and r["gpio"] == [] and r["flag"] == flag


@pytest.mark.parametrize("flag", DEEP)
def test_deep_off_goes_to_stop_as_stock(stock, img, flag):
    r = run_stop_entry(img, flag)
    assert r["stopped"] and r["clean"]
    assert r["gpio"] == run_stop_entry(stock, 0)["gpio"] != []
    assert r["flag"] == DEEP_ACTIVE                   # reste profond aux réveils sans allumage


def test_power_full_off_deep_arms_the_deep_off(img):
    r = run_fulloff(img, para=b"deep")
    assert r["clean"] and r["flag"] == DEEP_ARMED and r["delay"] == 100


@pytest.mark.parametrize("para", [b"", b"net", b"0", b"x", b"Deep", b"deeper", b"dee"])
@pytest.mark.parametrize("flag", [0x12345678, DEEP_ARMED, DEEP_ACTIVE])
def test_plain_power_full_off_stays_reachable(img, para, flag):
    r = run_fulloff(img, para=para, flag=flag)
    assert r["clean"] and r["flag"] == 0 and r["delay"] == 100


def test_the_flag_is_untouched_when_the_command_is_refused(img):
    r = run_fulloff(img, power=False, sleep_timer=0, para=b"deep", flag=0)
    assert r["flag"] == 0 and r["delay"] == 0


def test_power_full_off_from_sleep_cancels_the_sleep_timer(img):
    # sinon le décompte, en arrivant à zéro, relancerait une extinction sur un ampli déjà éteint
    assert run_fulloff(img, power=False, sleep_timer=1234)["timer"] == 0


# --- fin de l'extinction profonde : au premier allumage ------------------------------------------

FULL = BASE | {"push", "surround", "netoff", "sleeptimer", "mute"}


@pytest.fixture(scope="module")
def full():
    return build_patch1(patchlib.load_stock(), features=FULL)


def test_deep_off_ends_once_the_amp_is_on_again(full):
    r = run_tick(full, power=True, flag=DEEP_ACTIVE)
    assert r["clean"] and r["flag"] == 0


def test_deep_off_survives_wake_ups_that_do_not_turn_the_amp_on(full):
    r = run_tick(full, power=False, flag=DEEP_ACTIVE)
    assert r["clean"] and r["flag"] == DEEP_ACTIVE


def test_a_pending_deep_off_is_not_cancelled_before_it_happens(full):
    # entre la commande et l'extinction (1 s plus tard), l'ampli est encore allumé
    r = run_tick(full, power=True, flag=DEEP_ARMED)
    assert r["clean"] and r["flag"] == DEEP_ARMED


@pytest.mark.parametrize("power", [False, True])
def test_the_tick_leaves_any_other_ram_value_alone(full, power):
    assert run_tick(full, power=power, flag=0x12345678)["flag"] == 0x12345678


# --- sleeptimer : la temporisation d'origine veille -> éteint est rétablie -----------------------
# (keepsleep l'avait neutralisée pour garder le réseau ; éteint, l'ampli reste désormais joignable)

from emu import run_tick as _tick


def test_sleep_timer_counts_down_again(full):
    r = _tick(full, power=False, timer=3600)
    assert r["clean"] and r["timer"] == 3599 and not r["off_flag"] and r["delay"] == 0 and r["dde0"] == 0xff


def test_sleep_timer_expiry_requests_the_full_power_down_like_stock(full):
    r = _tick(full, power=False, timer=1, dde0=0xff)
    assert r["clean"] and r["timer"] == 0
    assert r["dddc"] == 0xc1 and r["dde0"] == 0xfd and r["delay"] == 100   # autres bits intacts


def test_idle_sleep_timer_does_nothing(full):
    r = _tick(full, power=True, timer=0)
    assert r["clean"] and r["timer"] == 0 and not r["off_flag"] and r["delay"] == 0 and r["dde0"] == 0xff


def test_sleep_timer_expiry_is_a_reachable_off(full):
    # la fin de temporisation ne doit pas hériter d'une extinction profonde
    assert _tick(full, power=False, timer=1, flag=0x12345678)["flag"] == 0x12345678


def test_push_still_works_with_the_sleep_timer(full):
    snap = bytes([110, 0x02, 2, 0xA5, 60, 5, 2])      # vol, mute|pwr<<1, src, magic, vivant, sur, cat
    r = _tick(full, vol=120, power=True, push_ram=snap + b"\xff", surround=5, sur_cat=2)
    assert r["clean"] and r["sent"] == 1 and len(r["replies"]) == 1


def test_sleeptimer_needs_push():
    with pytest.raises(ValueError):
        build_patch1(patchlib.load_stock(), features=BASE | {"sleeptimer"})


# --- reconfiguration réseau du module (FUN_08074ef2) : jamais ampli éteint, sauf extinction profonde ---
# Constaté sur matériel le 2026-11-15 (journal des requêtes) : à l'allumage depuis l'éteint, le
# firmware programme « couper l'interface réseau (08010000 <- 0), régler, la rallumer ». Si l'ampli
# est éteint avant, la séquence part au début de l'extinction complète et s'arrête après la coupure :
# module alimenté mais absent du réseau.
NET_SETUP = 0x08074ef2


def _net_setup(image, power, flag=0, arg=1):
    import struct
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
    from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R4, UC_ARM_REG_SP, UC_ARM_REG_PC, UC_ARM_REG_LR
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    mu.mem_map(0x08000000, 0x100000)
    mu.mem_write(0x08000000, bytes(image[:0x100000]))
    mu.mem_map(0x20000000, 0x20000)
    mu.mem_write(0x2000ddd4, bytes([0x80 | (2 if power else 0)]))
    mu.mem_write(0x2001ff08, struct.pack("<I", flag))
    started = []

    def stub(mu, addr, size, ud):
        started.append(addr)
        mu.reg_write(UC_ARM_REG_PC, mu.reg_read(UC_ARM_REG_LR) | 1)

    for f in (0x080753f8, 0x08075368):
        mu.hook_add(UC_HOOK_CODE, stub, begin=f, end=f)
    mu.reg_write(UC_ARM_REG_R0, arg)
    mu.reg_write(UC_ARM_REG_R4, 0x44444444)
    mu.reg_write(UC_ARM_REG_SP, 0x2001b000)
    mu.reg_write(UC_ARM_REG_LR, 0x080ffff1)
    mu.emu_start(NET_SETUP | 1, 0x080ffff0, count=10_000)
    assert mu.reg_read(UC_ARM_REG_PC) == 0x080ffff0
    assert mu.reg_read(UC_ARM_REG_SP) == 0x2001b000
    assert mu.reg_read(UC_ARM_REG_R4) == 0x44444444
    return started == [0x080753f8, 0x08075368]


def test_stock_starts_the_network_setup_even_when_off(stock):
    assert _net_setup(stock, power=False)


def test_network_setup_is_not_started_while_the_amp_is_off(img):
    assert not _net_setup(img, power=False)
    assert not _net_setup(img, power=False, flag=0x3dcd56aa)      # RAM non initialisée


def test_network_setup_still_runs_while_the_amp_is_on(img):
    assert _net_setup(img, power=True)


@pytest.mark.parametrize("flag", [DEEP_ARMED, DEEP_ACTIVE])
def test_network_setup_is_stock_during_a_deep_off(img, flag):
    assert _net_setup(img, power=False, flag=flag)


def test_network_setup_gate_keeps_the_no_op_argument(img):
    assert not _net_setup(img, power=True, arg=0)
