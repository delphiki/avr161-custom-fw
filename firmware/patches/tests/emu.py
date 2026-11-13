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
PUSH_RAM = 0x2001ff00              # état du push : vol, flags, src, magie 0xA5, compteur "client vivant"
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
            "err": err, "alive": mu.mem_read(PUSH_RAM + 4, 1)[0]}


F_BUILDREPLY = 0x0804fe7c
F_NETSEND = 0x08087e0c
A_MUTE = 0x2000de40
A_SRC = 0x2000e1ae
A_PWR = 0x2000ddd4                 # bit 1 = ampli allumé (0 en sleep)
A_CTX = 0x2000cb1c


def run_getstatus(img, vol=110, mute=False, src=2, power=True, other_flags=0):
    """Envoie get-status à cmd_dispatch en exécutant le VRAI cave et les VRAIES fonctions
    utilitaires du firmware (strlen, strcpy, memset, int2dec). build_reply et net_send sont
    interceptés. Retourne dict : replies = [(name, zone, para)], sent = nb d'appels net_send,
    ctx_cleared, clean (retour propre : pc, sp, r4-r7 intacts)."""
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    mu.mem_map(0x08000000, 0x100000)
    mu.mem_write(0x08000000, bytes(img[:0x100000]))
    mu.mem_map(0x20000000, 0x20000)
    mu.mem_write(MASTER, bytes([vol]))
    mu.mem_write(A_MUTE, bytes([(other_flags & ~2 & 0xff) | (2 if mute else 0)]))
    mu.mem_write(A_SRC, bytes([src]))
    mu.mem_write(A_PWR, bytes([(other_flags & ~2 & 0xff) | (2 if power else 0)]))
    mu.mem_write(STRUCT, b"get-status\0")
    mu.mem_write(STRUCT + 0x20, b"Main Zone\0")
    mu.reg_write(UC_ARM_REG_SP, SP0)
    mu.reg_write(UC_ARM_REG_R0, STRUCT)
    mu.reg_write(UC_ARM_REG_LR, RET | 1)
    for r, v in zip(CALLEE, SENTINELS):
        mu.reg_write(r, v)
    replies, sent, stock = [], [0], [0]

    def cstr(a):
        return bytes(mu.mem_read(a, 0x40)).split(b"\0")[0]

    def ret(mu):
        mu.reg_write(UC_ARM_REG_PC, mu.reg_read(UC_ARM_REG_LR) | 1)

    def on_build(mu, addr, size, ud):
        from unicorn.arm_const import UC_ARM_REG_R1, UC_ARM_REG_R2
        replies.append((cstr(mu.reg_read(UC_ARM_REG_R0)), cstr(mu.reg_read(UC_ARM_REG_R1)),
                        cstr(mu.reg_read(UC_ARM_REG_R2))))
        ret(mu)

    def on_send(mu, addr, size, ud):
        sent[0] += 1
        ret(mu)

    def on_stock(mu, addr, size, ud):            # ne doit pas arriver pour get-status
        stock[0] += 1
        mu.emu_stop()

    mu.hook_add(UC_HOOK_CODE, on_build, begin=F_BUILDREPLY, end=F_BUILDREPLY)
    mu.hook_add(UC_HOOK_CODE, on_send, begin=F_NETSEND, end=F_NETSEND)
    mu.hook_add(UC_HOOK_CODE, on_stock, begin=STOCK_BODY, end=STOCK_BODY)
    err = None
    try:
        mu.emu_start(CMD_DISPATCH | 1, RET, count=1_000_000)
    except UcError as e:
        err = e
    clean = (err is None and stock[0] == 0 and mu.reg_read(UC_ARM_REG_PC) == RET
             and mu.reg_read(UC_ARM_REG_SP) == SP0
             and tuple(mu.reg_read(r) for r in CALLEE) == SENTINELS)
    return {"replies": replies, "sent": sent[0], "clean": clean, "err": err,
            "ctx_cleared": mu.mem_read(A_CTX, 1)[0] == 0,
            "alive": mu.mem_read(PUSH_RAM + 4, 1)[0]}


TICK_BEGIN = 0x08010af6            # bloc exécuté une fois par seconde par la boucle principale
TICK_END = 0x08010b40


def run_tick(img, vol=110, mute=False, src=2, power=True, push_ram=None, timer=0):
    """Exécute le bloc « tick 1 s » (0x08010af6 -> 0x08010b40) de l'image, avec le vrai cave
    et les vraies fonctions utilitaires ; build_reply et net_send sont interceptés.
    push_ram = 5 octets initiaux à PUSH_RAM (None = RAM non initialisée, 0xFF).
    Retourne dict : replies, sent, push_ram (5 octets après), timer, off_flag, clean."""
    from unicorn.arm_const import UC_ARM_REG_R1, UC_ARM_REG_R2
    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
    mu.mem_map(0x08000000, 0x100000)
    mu.mem_write(0x08000000, bytes(img[:0x100000]))
    mu.mem_map(0x20000000, 0x20000)
    mu.mem_write(MASTER, bytes([vol]))
    mu.mem_write(A_MUTE, bytes([0x51 | (2 if mute else 0)]))      # autres bits quelconques
    mu.mem_write(A_SRC, bytes([src]))
    mu.mem_write(A_PWR, bytes([0x0d | (2 if power else 0)]))
    mu.mem_write(0x2000dd7c, struct.pack("<I", timer))
    mu.mem_write(PUSH_RAM, bytes(push_ram) if push_ram is not None else b"\xff" * 8)
    mu.reg_write(UC_ARM_REG_SP, SP0)
    mu.reg_write(UC_ARM_REG_LR, 0xdeadbeef)
    for r, v in zip(CALLEE, SENTINELS):
        mu.reg_write(r, v)
    replies, sent = [], [0]

    def cstr(a):
        return bytes(mu.mem_read(a, 0x40)).split(b"\0")[0]

    def ret(mu):
        mu.reg_write(UC_ARM_REG_PC, mu.reg_read(UC_ARM_REG_LR) | 1)

    def on_build(mu, addr, size, ud):
        replies.append((cstr(mu.reg_read(UC_ARM_REG_R0)), cstr(mu.reg_read(UC_ARM_REG_R1)),
                        cstr(mu.reg_read(UC_ARM_REG_R2))))
        ret(mu)

    def on_send(mu, addr, size, ud):
        sent[0] += 1
        ret(mu)

    mu.hook_add(UC_HOOK_CODE, on_build, begin=F_BUILDREPLY, end=F_BUILDREPLY)
    mu.hook_add(UC_HOOK_CODE, on_send, begin=F_NETSEND, end=F_NETSEND)
    err = None
    try:
        mu.emu_start(TICK_BEGIN | 1, TICK_END, count=1_000_000)
    except UcError as e:
        err = e
    clean = (err is None and mu.reg_read(UC_ARM_REG_PC) == TICK_END
             and mu.reg_read(UC_ARM_REG_SP) == SP0
             and tuple(mu.reg_read(r) for r in CALLEE) == SENTINELS)
    return {"replies": replies, "sent": sent[0], "clean": clean, "err": err,
            "push_ram": bytes(mu.mem_read(PUSH_RAM, 5)),
            "timer": struct.unpack("<I", bytes(mu.mem_read(0x2000dd7c, 4)))[0],
            "off_flag": bool(mu.mem_read(0x2000dddc, 1)[0] & 0x80)}
