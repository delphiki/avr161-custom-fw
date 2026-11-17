"""diag : lecture / écriture de la RAM par le réseau, pour les images de TEST uniquement
(recherche de la perte du module à la fin de la temporisation de veille, 2026-11-15).
  debug-peek <adresse décimale> : mémorise l'adresse, répond les 4 octets qui s'y trouvent.
  debug-poke <valeur décimale>  : écrit le mot de 32 bits à l'adresse mémorisée (RAM seulement),
                                  puis répond comme debug-peek."""
import struct
import pytest
import patchlib
from build_patch1 import build_patch1
from emu import run_diag

BASE = {"getstatus", "setvolume", "bluetooth", "keepsleep", "push", "netoff", "sleeptimer"}
TIMER = 0x2000dd7c


@pytest.fixture(scope="module")
def img():
    return build_patch1(patchlib.load_stock(), features=BASE | {"diag"})


def test_peek_replies_the_four_bytes_at_the_address(img):
    r = run_diag(img, b"debug-peek", str(TIMER).encode(), mem={TIMER: struct.pack("<I", 0x0e10)})
    assert r["clean"], r["err"]
    assert r["replies"] == [(b"debug-peek", b"Main Zone", b"16,14,0,0")]
    assert r["sent"] == 1
    assert r["addr"] == TIMER


def test_peek_reads_a_peripheral_sized_address(img):
    # 0x08000000 = 134217728 : vérifie le décodage d'une adresse de plus de 16 bits hors RAM
    r = run_diag(img, b"debug-peek", b"134217728")
    assert r["clean"], r["err"]
    want = ",".join(str(b) for b in bytes(img[:4])).encode()
    assert r["replies"][0][2] == want


def test_poke_writes_the_word_at_the_remembered_address(img):
    r = run_diag(img, b"debug-poke", b"20", mem={TIMER: struct.pack("<I", 3600)}, diag_addr=TIMER)
    assert r["clean"], r["err"]
    assert r["read"](TIMER, 4) == struct.pack("<I", 20)
    assert r["replies"] == [(b"debug-poke", b"Main Zone", b"20,0,0,0")]


def test_poke_refuses_an_address_outside_ram(img):
    r = run_diag(img, b"debug-poke", b"0", diag_addr=0x08001000)
    assert r["clean"], r["err"]
    assert r["read"](0x08001000, 4) == bytes(img[0x1000:0x1004])


def test_without_diag_the_commands_reach_the_stock_dispatch():
    out = build_patch1(patchlib.load_stock(), features=BASE)
    assert run_diag(out, b"debug-peek", b"0")["stock"] == 1
    assert run_diag(out, b"debug-poke", b"0", diag_addr=TIMER)["stock"] == 1


# --- trace : l'ampli note lui-même ses sorties chaque seconde tant qu'il n'est pas allumé ---
TRACE = 0x2001fc00
GPIOD, GPIOG = 0x40020c00, 0x40021800
PERIPH = {GPIOD: struct.pack("<I", 0x55555144), GPIOD + 0x14: struct.pack("<I", 0x9300),
          GPIOG + 0x14: struct.pack("<I", 0x0078)}


def _tick(img, **kw):
    from emu import run_tick
    return run_tick(img, periph=PERIPH, **kw)


def test_trace_records_the_outputs_each_second_while_off(img):
    r = _tick(img, power=False, timer=5, ram={TRACE: struct.pack("<I", 6), 0x2000dd5c: struct.pack("<I", 0x12c),
                                              0x2000dddc: b"\x80"})
    assert r["clean"], r["err"]
    assert struct.unpack("<I", r["read"](TRACE, 4))[0] == 7
    pd, mid, seq, pg = struct.unpack("<4H", r["read"](TRACE + 8 + 7 * 8, 8))
    assert (pd, seq, pg) == (0x9300, 0x12c, 0x0078)
    assert mid == 0x8055            # dddc dans l'octet haut, mode des broches PD8..PD11 dans le bas
    assert r["timer"] == 4          # le décompte de veille tourne toujours


def test_trace_index_wraps_and_survives_uninitialised_ram(img):
    r = _tick(img, power=False, ram={TRACE: struct.pack("<I", 0xffffffff)})
    assert r["clean"], r["err"]
    assert struct.unpack("<I", r["read"](TRACE, 4))[0] == 0


def test_trace_is_frozen_while_the_amp_is_on(img):
    r = _tick(img, power=True, ram={TRACE: struct.pack("<I", 6)})
    assert r["clean"], r["err"]
    assert struct.unpack("<I", r["read"](TRACE, 4))[0] == 6
    assert r["read"](TRACE + 8, 64 * 8) == bytes(64 * 8)


# --- journal des requêtes envoyées au module (détour de FUN_08073984) ---
NODE_SEND = 0x08073984
NODE_IDX, NODE_SECS, NODE_RING = 0x2001bff8, 0x2001bffc, 0x2001c000


def _send(img, op, node, length=0, data=b"", idx=5, seq=0xc6, secs=77, pwr=0x80, dddc=0x80):
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS
    from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                                   UC_ARM_REG_SP, UC_ARM_REG_PC, UC_ARM_REG_LR)
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    mu.mem_map(0x08000000, 0x100000)
    mu.mem_write(0x08000000, bytes(img[:0x100000]))
    mu.mem_map(0x20000000, 0x20000)
    req, buf = 0x20010000, 0x20010100
    mu.mem_write(req, struct.pack("<IHHI", node, length, 0, buf))
    mu.mem_write(buf, data)
    mu.mem_write(NODE_IDX, struct.pack("<II", idx, secs))
    mu.mem_write(0x2000dd5c, struct.pack("<I", seq))
    mu.mem_write(0x2000ddd4, bytes([pwr]))
    mu.mem_write(0x2000dddc, bytes([dddc]))
    regs = {UC_ARM_REG_R0: op, UC_ARM_REG_R1: req, UC_ARM_REG_R2: 0x08012345, UC_ARM_REG_R3: 0xcafe}
    for r, v in regs.items():
        mu.reg_write(r, v)
    mu.reg_write(UC_ARM_REG_SP, 0x2001b000)
    mu.reg_write(UC_ARM_REG_LR, 0x080ffff1)
    mu.emu_start(NODE_SEND | 1, NODE_SEND + 4, count=10_000)
    assert mu.reg_read(UC_ARM_REG_PC) == NODE_SEND + 4
    assert mu.reg_read(UC_ARM_REG_SP) == 0x2001b000 - 32          # le push.w d'origine a eu lieu
    assert {r: mu.reg_read(r) for r in regs} == regs               # arguments intacts
    new = struct.unpack("<I", bytes(mu.mem_read(NODE_IDX, 4)))[0]
    return new, struct.unpack("<IBBHIHBB", bytes(mu.mem_read(NODE_RING + new * 16, 16)))


def test_node_log_records_a_write_with_its_first_data_bytes(img):
    new, e = _send(img, 4, 0x08090100, length=2, data=b"\x27\x29\x00\x00")
    assert new == 6
    assert e == (0x08090100, 4, 2, 0xc6, 0x2927, 77, 0x80, 0x80)


def test_node_log_records_a_read_without_touching_the_data_pointer(img):
    new, e = _send(img, 0, 0x08040901, idx=511)
    assert new == 0                                                # l'anneau reboucle à 512
    assert e == (0x08040901, 0, 0, 0xc6, 0, 77, 0x80, 0x80)


def test_without_diag_the_send_function_is_untouched():
    out = build_patch1(patchlib.load_stock(), features=BASE)
    stock = patchlib.load_stock()
    assert bytes(out[0x73984:0x73988]) == bytes(stock[0x73984:0x73988])


def test_trace_counts_seconds_even_while_on_and_snapshots_all_ports_while_off(img):
    periph = dict(PERIPH)
    for i in range(7):
        periph[0x40020014 + i * 0x400] = struct.pack("<I", 0x1100 + i)
    from emu import run_tick
    r = run_tick(img, power=True, periph=periph, ram={NODE_SECS: struct.pack("<I", 9)})
    assert r["clean"], r["err"]
    assert struct.unpack("<I", r["read"](NODE_SECS, 4))[0] == 10
    r = run_tick(img, power=False, periph=periph, ram={NODE_SECS: struct.pack("<I", 9)})
    assert r["clean"], r["err"]
    assert struct.unpack("<7I", r["read"](TRACE + 0x210, 28)) == tuple(0x1100 + i for i in range(7))


@pytest.mark.parametrize("node", [0x08090300, 0x08090400])
def test_node_log_skips_control_port_traffic(img, node):
    # sinon la lecture du journal par le réseau l'écrase (constaté sur matériel le 2026-11-15)
    new, _ = _send(img, 4, node, length=1, data=b"POST")
    assert new == 5


def test_node_log_keeps_the_port_opening_write(img):
    new, e = _send(img, 4, 0x08090100, length=2, data=b"\x27\x29\x00\x00")
    assert new == 6


# --- journal de ce que le module renvoie : notifications et accusés d'écriture ---
NOTIF_CB = 0x0808671c           # rappel des notifications : r0 -> {nœud, ?, pointeur données}
WRITE_CB = 0x080866d0           # rappel des écritures : r0 -> {nœud, ..., +0xc état}


def _callback(img, entry, node, data=b"\x00", status=0, idx=5, pushed=24):
    from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS
    from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
                                   UC_ARM_REG_R4, UC_ARM_REG_SP, UC_ARM_REG_PC, UC_ARM_REG_LR)
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    mu.mem_map(0x08000000, 0x100000)
    mu.mem_write(0x08000000, bytes(img[:0x100000]))
    mu.mem_map(0x20000000, 0x20000)
    arg, buf = 0x20010000, 0x20010100
    mu.mem_write(arg, struct.pack("<IIIB", node, 0, buf, status))
    mu.mem_write(buf, data)
    mu.mem_write(NODE_IDX, struct.pack("<II", idx, 77))
    mu.mem_write(0x2000dd5c, struct.pack("<I", 0xc6))
    mu.mem_write(0x2000ddd4, b"\x0f")
    mu.mem_write(0x2000dddc, b"\x80")
    regs = {UC_ARM_REG_R0: arg, UC_ARM_REG_R1: 0x1111, UC_ARM_REG_R2: 0x2222, UC_ARM_REG_R3: 0x3333,
            UC_ARM_REG_LR: 0x080ffff1}
    for r, v in regs.items():
        mu.reg_write(r, v)
    mu.reg_write(UC_ARM_REG_SP, 0x2001b000)
    mu.emu_start(entry | 1, entry + 4, count=10_000)
    assert mu.reg_read(UC_ARM_REG_PC) == entry + 4
    assert mu.reg_read(UC_ARM_REG_SP) == 0x2001b000 - pushed       # le push d'origine a eu lieu
    assert mu.reg_read(UC_ARM_REG_R4) == arg                       # ... et le `movs r4, r0`
    assert {r: mu.reg_read(r) for r in regs} == regs
    new = struct.unpack("<I", bytes(mu.mem_read(NODE_IDX, 4)))[0]
    return new, struct.unpack("<IBBHIHBB", bytes(mu.mem_read(NODE_RING + new * 16, 16)))


def test_log_records_a_notification_with_its_value(img):
    new, e = _callback(img, NOTIF_CB, 0x08040b00, data=b"\x02\xaa\xbb\xcc")
    assert new == 6
    assert e == (0x08040b00, 0xc6, 0, 0xc6, 2, 77, 0x0f, 0x80)


def test_log_skips_the_received_data_notification(img):
    # une par commande reçue : la lecture du journal l'écraserait
    new, _ = _callback(img, NOTIF_CB, 0x08090300)
    assert new == 5


def test_log_records_a_write_acknowledgement_with_its_status(img):
    new, e = _callback(img, WRITE_CB, 0x08090100, status=3, pushed=16)
    assert new == 6
    assert e == (0x08090100, 0x84, 0, 0xc6, 3, 77, 0x0f, 0x80)


def test_log_skips_the_acknowledgement_of_sent_data(img):
    new, _ = _callback(img, WRITE_CB, 0x08090400, pushed=16)
    assert new == 5


def test_without_diag_the_callbacks_are_untouched():
    out = build_patch1(patchlib.load_stock(), features=BASE)
    stock = patchlib.load_stock()
    for va in (NOTIF_CB, WRITE_CB):
        assert bytes(out[va - 0x08000000:va - 0x08000000 + 4]) == bytes(stock[va - 0x08000000:va - 0x08000000 + 4])
