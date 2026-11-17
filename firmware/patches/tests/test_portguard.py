"""portguard : écrire le numéro de port (nœud 08090100) dans le module pendant qu'un client est
connecté coupe ce client et laisse le port fermé (constaté le 2026-11-16 : connexion perdue
8 tics après un décompte lu à 158, port refusé ensuite). La routine d'origine FUN_08087d9c
écrit sans rien vérifier ; la feature la court-circuite tant qu'un client est connecté.
L'état du client (0x2000e2a8, notification 08090200) vaut 1 à l'initialisation (0x0804812e,
0x08048362) et 0 quand un client est connecté."""
import struct
import pytest
import patchlib
from build_patch1 import build_patch1

BASE = {"getstatus", "setvolume", "bluetooth", "keepsleep", "push", "netoff", "sleeptimer"}
WRITE_PORT = 0x08087d9c        # routine d'origine : écrit 0x2729 (10025) dans 08090100
NODE_WRITE = 0x08093f3e        # écriture d'un nœud (r0 = nœud, r1 = longueur, r2 = données)
CLIENT = 0x2000e2a8            # 1 = personne (valeur initiale), 0 = client connecté
RET = 0x080ffff0
COOL = 0x2001ff10              # « port configuré » : mot magique OK_MAGIC, toute autre valeur = non
OK_MAGIC = 0x324b4f50
DEC8, DECC = 0x2000dec8, 0x2000decc    # tempos qui mènent à la reconfiguration réseau à l'allumage
NETSTBY = 0x2001ff08


def _run(img, client, entry=WRITE_PORT, arg=0, report=None, ok=0, ram=None):
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
    from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R4,
                                   UC_ARM_REG_SP, UC_ARM_REG_PC, UC_ARM_REG_LR)
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    mu.mem_map(0x08000000, 0x100000)
    mu.mem_write(0x08000000, bytes(img[:0x100000]))
    mu.mem_write(NODE_WRITE, patchlib.asm_thumb("bx lr", NODE_WRITE))   # le module n'est pas émulé
    mu.mem_map(0x20000000, 0x20000)
    mu.mem_write(CLIENT, bytes([client]))
    mu.mem_write(COOL, struct.pack("<I", ok))
    for a, b in (ram or {}).items():
        mu.mem_write(a, b)
    writes = []

    def on_code(mu, addr, size, _):
        if addr == NODE_WRITE:
            data = mu.reg_read(UC_ARM_REG_R2)
            writes.append((mu.reg_read(UC_ARM_REG_R0), bytes(mu.mem_read(data, mu.reg_read(UC_ARM_REG_R1)))))
    mu.hook_add(UC_HOOK_CODE, on_code)
    mu.reg_write(UC_ARM_REG_R0, arg)
    mu.reg_write(UC_ARM_REG_R4, 0x44444444)
    mu.reg_write(UC_ARM_REG_SP, 0x2001b000)
    mu.reg_write(UC_ARM_REG_LR, RET | 1)
    mu.emu_start(entry | 1, RET, count=10_000)
    assert mu.reg_read(UC_ARM_REG_PC) == RET
    assert mu.reg_read(UC_ARM_REG_SP) == 0x2001b000
    assert mu.reg_read(UC_ARM_REG_R4) == 0x44444444
    if report is not None:
        report["client"] = mu.mem_read(CLIENT, 1)[0]
        report["ok"] = struct.unpack("<I", bytes(mu.mem_read(COOL, 4)))[0]
    return writes


@pytest.fixture(scope="module")
def img():
    return build_patch1(patchlib.load_stock(), features=BASE | {"portguard"})


def test_stock_writes_the_port_even_with_a_client_connected():
    assert _run(patchlib.load_stock(), client=0) == [(0x08090100, b"\x27\x29")]


@pytest.mark.parametrize("client", [1, 2, 0xff])
def test_the_port_is_written_when_nobody_is_connected(img, client):
    assert _run(img, client=client) == [(0x08090100, b"\x27\x29")]


def test_the_port_is_not_rewritten_under_a_connected_client(img):
    assert _run(img, client=0) == []


def test_the_firmware_starts_with_nobody_connected():
    stock = patchlib.load_stock()
    for at in (0x0804812e, 0x08048362):          # ldr r0, =0x2000e2a8 ; movs r1, #1 ; strb r1, [r0]
        tail = bytes(stock[at - 0x08000000 + (4 if at == 0x0804812e else 2):][:4])
        assert tail == patchlib.asm_thumb("movs r1, #1\nstrb r1, [r0]", at)


# Couper ou relancer l'interface réseau du module (nœud 08010000, FUN_08087304) fait tomber le
# client sans notification 08090200 : l'état resterait à 0 et l'écriture du port qui suit serait
# court-circuitée, port fermé pour de bon (constaté à 17:45 : Home Assistant connecté, ampli
# rallumé depuis l'éteint, port refusé ensuite).
NET_IFACE = 0x08087304


@pytest.mark.parametrize("value", [0, 1])
def test_restarting_the_network_interface_forgets_the_client(img, value):
    report = {}
    assert _run(img, client=0, entry=NET_IFACE, arg=value, report=report) == [(0x08010000, bytes([value]))]
    assert report["client"] == 1


def test_stock_keeps_a_stale_client_across_an_interface_restart():
    report = {}
    _run(patchlib.load_stock(), client=0, entry=NET_IFACE, arg=1, report=report)
    assert report["client"] == 0


def test_only_the_two_routine_heads_and_the_tick_call_change_in_stock_code():
    base = build_patch1(patchlib.load_stock(), features=BASE)
    with_guard = build_patch1(patchlib.load_stock(), features=BASE | {"portguard"})
    diff = [i for i in range(0xE0000) if base[i] != with_guard[i]]
    assert diff and all(0x87d9c <= i < 0x87da0 or 0x87304 <= i < 0x87308 or 0x10af6 <= i < 0x10afa
                        for i in diff)


def test_without_the_feature_the_routine_is_untouched():
    stock, plain = patchlib.load_stock(), build_patch1(patchlib.load_stock(), features=BASE)
    assert plain[0x87d9c:0x87dc0] == stock[0x87d9c:0x87dc0]


# À l'allumage depuis l'éteint, le firmware d'origine reconfigure le réseau du module (coupure de
# l'interface, relance, réécriture du port) parce qu'il le croit tout juste redémarré. Avec netoff
# le module est resté allumé et configuré : cette relance coupe le client une trentaine de
# secondes et laisse parfois le port fermé (17:45, 20:33 et 00:02 ; une seule écriture acquittée
# a suffi à 00:02). Essai du 2026-11-17 à 00:10 : en remettant à zéro les deux tempos qui
# mènent à la reconfiguration (0x2000dec8, 0x2000decc), l'allumage se fait sans aucune coupure.
# Le firmware le fait donc lui-même tant que le port a été configuré depuis la dernière mise
# sous tension du module.
def _tick(img, ok, flag=0x12345678, dec8=0x2cd, decc=0x313, client=1, **kw):
    import emu
    out = emu.run_tick(img, flag=flag, ram={COOL: struct.pack("<I", ok), DEC8: struct.pack("<I", dec8),
                                           DECC: struct.pack("<I", decc), CLIENT: bytes([client])}, **kw)
    assert out["clean"]
    word = lambda a: struct.unpack("<I", out["read"](a, 4))[0]
    return word(DEC8), word(DECC), word(COOL)


def test_a_configured_module_is_not_reconfigured_at_power_on(img):
    assert _tick(img, OK_MAGIC) == (0, 0, OK_MAGIC)


@pytest.mark.parametrize("ok", [0, 0xffffffff])
def test_a_connected_client_proves_the_module_is_configured(img, ok):
    assert _tick(img, ok, client=0) == (0, 0, OK_MAGIC)


# 0x4b4f5450 : marque de la v1.2.15-diag, posée trop tôt, qui survit à un reflash
@pytest.mark.parametrize("ok", [0, 0xffffffff, 0x88fd2612, 0x4b4f5450])
def test_an_unconfigured_module_is_still_reconfigured(img, ok):
    assert _tick(img, ok)[:2] == (0x2cd, 0x313)


@pytest.mark.parametrize("flag", [0x44454550, 0x44454551])        # extinction profonde armée / en cours
def test_a_deep_off_forgets_the_configuration(img, flag):
    assert _tick(img, OK_MAGIC, flag=flag, power=False) == (0x2cd, 0x313, 0)
    assert _tick(img, OK_MAGIC, flag=flag, power=False, client=0) == (0x2cd, 0x313, 0)


def test_the_port_is_written_whatever_the_configured_mark(img):
    assert _run(img, client=1, ok=OK_MAGIC) == [(0x08090100, b"\x27\x29")]


def test_portguard_needs_the_one_second_tick():
    with pytest.raises(ValueError):
        build_patch1(patchlib.load_stock(), features={"getstatus", "portguard"})
