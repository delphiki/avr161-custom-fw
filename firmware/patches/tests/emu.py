"""Émulation (Unicorn) du dispatch patché : exécute le VRAI code du cave contre l'image
construite, avec le corps du dispatch stock remplacé par un modèle (pas volume +/-step,
ou pas refusé). Sert à tester le COMPORTEMENT, pas seulement le désassemblage."""
import struct
from unicorn import Uc, UcError, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS, UC_HOOK_CODE
from unicorn.arm_const import (UC_ARM_REG_R0, UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6,
                               UC_ARM_REG_R7, UC_ARM_REG_SP, UC_ARM_REG_LR, UC_ARM_REG_PC)

CMD_DISPATCH = 0x0804f328
STOCK_BODY = CMD_DISPATCH + 4      # 1re instruction stock après le prologue déplacé
MASTER = 0x2000e1b8
STEP_TMR = 0x2000e1cd              # < 0xd -> pas de 2, sinon pas de 4 (cf. vol_up/vol_down)
STRUCT = 0x20010000
SP0 = 0x2001f000
RET = 0x080ffff0
SENTINELS = (0x44444444, 0x55555555, 0x66666666, 0x77777777)
CALLEE = (UC_ARM_REG_R4, UC_ARM_REG_R5, UC_ARM_REG_R6, UC_ARM_REG_R7)


def run_cmd(img, name, para=b"", master=110, tmr=0, refuse=False, zone=b"Main Zone"):
    """Envoie la commande (name, zone, para) à cmd_dispatch. Retourne un dict :
    stock_calls = [(name, zone, para, master_vu)] reçus par le dispatch STOCK,
    Le modèle de pas reproduit vol_down (0x801b8f0) / vol_up (0x801b568) : pas de 2 si
    *STEP_TMR < 0xd (ou, en montée, si master > 0x8b), sinon 4 ; butées 0 et 180.
    master = valeur finale, clean = retour propre (pc, sp, r4-r7 intacts)."""
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    mu.mem_map(0x08000000, 0x100000)
    mu.mem_write(0x08000000, bytes(img[:0x100000]))
    mu.mem_map(0x20000000, 0x20000)
    mu.mem_write(MASTER, bytes([master]))
    mu.mem_write(STEP_TMR, bytes([tmr]))
    mu.mem_write(STRUCT, name + b"\0")
    mu.mem_write(STRUCT + 0x20, zone + b"\0")
    mu.mem_write(STRUCT + 0x40, para + b"\0")
    mu.reg_write(UC_ARM_REG_SP, SP0)
    mu.reg_write(UC_ARM_REG_R0, STRUCT)
    mu.reg_write(UC_ARM_REG_LR, RET | 1)
    for r, v in zip(CALLEE, SENTINELS):
        mu.reg_write(r, v)
    calls = []

    def cstr(a):
        return bytes(mu.mem_read(a, 0x20)).split(b"\0")[0]

    def stock_body(mu, addr, size, ud):
        p = mu.reg_read(UC_ARM_REG_R4)
        n = cstr(p)
        m = mu.mem_read(MASTER, 1)[0]
        calls.append((n, cstr(p + 0x20), cstr(p + 0x40), m))
        t = mu.mem_read(STEP_TMR, 1)[0]
        if not refuse:
            if n == b"volume-down" and m != 0:
                st = 2 if t < 0xd else 4
                mu.mem_write(MASTER, bytes([0 if m < st + 1 else m - st]))
            elif n == b"volume-up" and m < 180:
                st = 2 if (t < 0xd or m > 0x8b) else 4
                mu.mem_write(MASTER, bytes([min(180, m + st)]))
        sp = mu.reg_read(UC_ARM_REG_SP)          # épilogue stock : pop {r0,r4-r7,pc}
        w = struct.unpack("<6I", bytes(mu.mem_read(sp, 24)))
        for r, v in zip((UC_ARM_REG_R0,) + CALLEE, w[:5]):
            mu.reg_write(r, v)
        mu.reg_write(UC_ARM_REG_SP, sp + 24)
        mu.reg_write(UC_ARM_REG_PC, w[5] | 1)

    mu.hook_add(UC_HOOK_CODE, stock_body, begin=STOCK_BODY, end=STOCK_BODY)
    err = None
    try:
        mu.emu_start(CMD_DISPATCH | 1, RET, count=1_000_000)
    except UcError as e:
        err = e
    clean = (err is None and mu.reg_read(UC_ARM_REG_PC) == RET
             and mu.reg_read(UC_ARM_REG_SP) == SP0
             and tuple(mu.reg_read(r) for r in CALLEE) == SENTINELS)
    return {"stock_calls": calls, "master": mu.mem_read(MASTER, 1)[0], "clean": clean,
            "err": err}
