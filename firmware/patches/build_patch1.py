"""Build du firmware patché #1 (rempli task par task). cf. ../patches/DESIGN-patch1.md."""
import patchlib

CAVE_VA = 0x080E0000  # base du code-cave (zone réécrite, 128 Ko de 0xFF)

# --- Test A : patch cosmétique d'un nom de source OSD (preuve de récupération USB) ---
SRCNAME_OFF = 0xd9904            # flash 0x080d9904 : "USB" dans la table d'affichage source (0x8053684)
SRCNAME_LEN = 16                 # largeur fixe OSD
_STOCK_SRCNAME = b"USB             "
TESTA_STRING = b"USB [PATCH1]    "  # 16 octets, largeur préservée, visible via `ampli.py source USB`


def build_testA(img):
    """Change UNIQUEMENT le nom OSD de la source USB (changement cosmétique observable)."""
    assert len(TESTA_STRING) == SRCNAME_LEN
    cur = bytes(img[SRCNAME_OFF:SRCNAME_OFF + SRCNAME_LEN])
    assert cur == _STOCK_SRCNAME, f"chaîne source inattendue à {SRCNAME_OFF:#x}: {cur!r}"
    patchlib.write_bytes(img, SRCNAME_OFF, TESTA_STRING)
    return img


# --- Test B : témoin RÉSEAU (User-Agent dans la réponse heart-alive, 100% MCU) ---
# Prouve sans ambiguïté que le flash MCU écrit nos octets (lisible via ampli.py).
UA_KARDON_OFF = 0xd4752          # "Kardon" dans "Harman Kardon AVR161/AVR1610" (UA heart-alive)
_STOCK_KARDON = b"Kardon"
TESTB_TOKEN = b"PATCH1"          # même longueur ; préserve les tokens modèle AVR161/AVR1610


def build_testB(img):
    """Change 'Kardon' -> 'PATCH1' dans le User-Agent émis à chaque heart-alive."""
    assert len(TESTB_TOKEN) == len(_STOCK_KARDON)
    cur = bytes(img[UA_KARDON_OFF:UA_KARDON_OFF + len(_STOCK_KARDON)])
    assert cur == _STOCK_KARDON, f"attendu 'Kardon' à {UA_KARDON_OFF:#x}, obtenu {cur!r}"
    patchlib.write_bytes(img, UA_KARDON_OFF, TESTB_TOKEN)
    return img


# =========================================================================
# PATCH #1 — détour + code-cave (get-status ; set-volume T4 ; Bluetooth T5)
# =========================================================================
from patchlib import va_to_off

# --- adresses firmware (verbatim NOTES/DESIGN) ---
CMD_DISPATCH = 0x0804f328          # tête du dispatcheur réseau ; prologue 4o (push{r3-r7,lr};movs r4,r0)
F_STRCMP     = 0x0809534c
F_STRLEN     = 0x080953d0
F_STRCAT     = 0x08095408          # strcat_at(dest_end, src) = strcpy(dest, src)
F_MEMSET     = 0x080953b8
F_INT2DEC    = 0x0804fdd4          # int2dec(r0=uint 0..999) -> r0=ptr décimal (buf fixe 0x2000dee4)
F_BUILDREPLY = 0x0804fe7c          # build_reply(r0=name, r1=zone, r2=para) -> net_response_buf
F_NETSEND    = 0x08087e0c          # net_send(r0=buf)
A_STATUSNAME = 0x080defc0          # "status_name" (ctx à armer pour émettre zone/para)
A_CTX        = 0x2000cb1c          # buffer ctx comparé par strcmp à "status_name"
A_NETBUF     = 0x2000a0b4          # buffer HTTP sortant
A_VOL        = 0x2000e1b8          # volume live (u8 0..180)
A_MUTE       = 0x2000de40          # flags ; mute = bit1
A_SRC        = 0x2000e1ae          # source enum (u8)
F_VOLUP      = 0x0801b568          # vol_up()  (incrémente+applique 0x2000e1b8)
F_VOLDOWN    = 0x0801b8f0          # vol_down()
VOL_MAX      = 180                 # 0..0xB4

# --- layout du cave (zone réécrite 0x080E0000) ---
STR_GETSTATUS = CAVE_VA + 0x000    # "get-status\0"
STR_COMMA     = CAVE_VA + 0x010    # ",\0"
STR_SETVOL    = CAVE_VA + 0x018    # "set-volume\0"
EMIT_STATUS   = CAVE_VA + 0x040    # routine emit_status
SET_VOLUME    = CAVE_VA + 0x280    # routine set_volume
CAVE_DISPATCH = CAVE_VA + 0x180    # entrée depuis le trampoline


def _lo(a): return a & 0xffff
def _hi(a): return (a >> 16) & 0xffff
def _mw(reg, a): return f"movw {reg}, #{_lo(a):#x}\nmovt {reg}, #{_hi(a):#x}\n"


def _emit_status_src():
    # append la valeur décimale (déjà en r0) à PARA_BUF (r5) ; r6 = sauvegarde src
    def app_dec():
        return (f"bl #{F_INT2DEC}\nmov r6, r0\n"
                f"mov r0, r5\nbl #{F_STRLEN}\nadd r0, r5, r0\n"
                f"mov r1, r6\nbl #{F_STRCAT}\n")
    def app_str(a):
        return (f"mov r0, r5\nbl #{F_STRLEN}\nadd r0, r5, r0\n"
                + _mw("r1", a) + f"bl #{F_STRCAT}\n")
    return (
        "push {r4,r5,r6,lr}\n"
        "mov r4, r0\n"                       # r4 = struct (name@0, zone@0x20, para@0x40)
        "sub sp, #16\n"
        "mov r5, sp\n"                       # r5 = PARA_BUF (pile)
        # ctx = "status_name"  (memset puis strcat depuis 0x80defc0)
        + _mw("r0", A_CTX) + "movs r1, #0\nmovs r2, #12\n" + f"bl #{F_MEMSET}\n"
        + _mw("r0", A_CTX) + _mw("r1", A_STATUSNAME) + f"bl #{F_STRCAT}\n"
        # PARA_BUF = ""
        + "mov r0, r5\nmovs r1, #0\nmovs r2, #16\n" + f"bl #{F_MEMSET}\n"
        # vol
        + _mw("r0", A_VOL) + "ldrb r0, [r0]\n" + app_dec() + app_str(STR_COMMA)
        # mute = (*flags >> 1) & 1
        + _mw("r0", A_MUTE) + "ldrb r0, [r0]\nlsrs r0, r0, #1\nand r0, r0, #1\n" + app_dec()
        + app_str(STR_COMMA)
        # src
        + _mw("r0", A_SRC) + "ldrb r0, [r0]\n" + app_dec()
        # build_reply(name=get-status, zone=struct+0x20, para=PARA_BUF)
        + _mw("r0", STR_GETSTATUS) + "add r1, r4, #0x20\nmov r2, r5\n" + f"bl #{F_BUILDREPLY}\n"
        # net_send(net_response_buf)
        + _mw("r0", A_NETBUF) + f"bl #{F_NETSEND}\n"
        # restaurer ctx : 0x2000cb1c[0] = 0  (chaîne vide != "status_name" -> heart-alive intact)
        + _mw("r0", A_CTX) + "movs r1, #0\nstrb r1, [r0]\n"
        + "add sp, #16\n"
        "pop {r4,r5,r6,pc}\n"
    )


def _set_volume_src():
    # r0 = struct (para @ +0x40). Règle 0x2000e1b8 vers la cible en réutilisant vol_up/vol_down.
    return (
        "push {r4,r5,r6,r7,lr}\n"
        "add r4, r0, #0x40\n"                # r4 = para (chaîne décimale)
        # --- atoi(para) -> r5 ---
        "movs r5, #0\n"
        "atoi_loop:\n"
        "ldrb r6, [r4]\n"
        "subs r6, r6, #0x30\n"               # c - '0'
        "cmp r6, #9\n"
        "bhi atoi_done\n"                    # non-chiffre (unsigned > 9) -> fin
        "movs r7, #10\n"
        "muls r5, r7, r5\n"                  # r5 = r5*10
        "adds r5, r5, r6\n"
        "adds r4, r4, #1\n"
        "b atoi_loop\n"
        "atoi_done:\n"
        # --- clamp r5 à [0, VOL_MAX] ---
        f"cmp r5, #{VOL_MAX}\n"
        "bls clamp_ok\n"
        f"movs r5, #{VOL_MAX}\n"
        "clamp_ok:\n"
        # --- boucle d'ajustement (bornée 128) ---
        "movs r7, #0\n"                      # r7 = compteur
        "sv_loop:\n"
        "cmp r7, #128\n"
        "bhs sv_end\n"
        + _mw("r0", A_VOL) + "ldrb r6, [r0]\n"   # r6 = cur
        "cmp r6, r5\n"
        "beq sv_end\n"                       # cible atteinte
        "bhi go_down\n"                      # cur > cible -> down
        f"bl #{F_VOLUP}\n"
        "b after_step\n"
        "go_down:\n"
        f"bl #{F_VOLDOWN}\n"
        "after_step:\n"
        + _mw("r0", A_VOL) + "ldrb r0, [r0]\n"   # r0 = nouv
        "cmp r0, r6\n"
        "beq sv_end\n"                       # pas de progrès (garde bloquante) -> stop
        # croisement : was_below(r6<r5) != now_below(r0<r5) -> stop
        "movs r1, #0\n"
        "cmp r6, r5\n"
        "bhs wb0\n"
        "movs r1, #1\n"
        "wb0:\n"
        "movs r2, #0\n"
        "cmp r0, r5\n"
        "bhs nb0\n"
        "movs r2, #1\n"
        "nb0:\n"
        "cmp r1, r2\n"
        "bne sv_end\n"                       # croisement/overshoot -> stop
        "adds r7, r7, #1\n"
        "b sv_loop\n"
        "sv_end:\n"
        "pop {r4,r5,r6,r7,pc}\n"
    )


def _cave_dispatch_part1(features):
    # r0 = param_1 (name ptr) ; lr = retour vers l'appelant de cmd_dispatch (détour avant son push)
    s = "push {r0, r4, lr}\nmov r4, r0\n"
    if "getstatus" in features:
        s += ("mov r0, r4\n" + _mw("r1", STR_GETSTATUS) + f"bl #{F_STRCMP}\n"
              "cmp r0, #0\nbne not_gs\n"
              f"mov r0, r4\nbl #{EMIT_STATUS}\npop {{r0, r4, pc}}\n"
              "not_gs:\n")
    if "setvolume" in features:
        s += ("mov r0, r4\n" + _mw("r1", STR_SETVOL) + f"bl #{F_STRCMP}\n"
              "cmp r0, #0\nbne not_sv\n"
              f"mov r0, r4\nbl #{SET_VOLUME}\npop {{r0, r4, pc}}\n"
              "not_sv:\n")
    s += "pop {r0, r4, lr}\n"                 # pas pour nous -> restaurer, exécuter prologue déplacé
    return s


def build_patch1(img, features=frozenset()):
    """Construit l'image patchée pour les `features` demandées."""
    features = set(features)
    needs_dispatch = bool(features & {"getstatus", "setvolume"})
    if "getstatus" in features:
        patchlib.write_bytes(img, va_to_off(STR_GETSTATUS), b"get-status\x00")
        patchlib.write_bytes(img, va_to_off(STR_COMMA), b",\x00")
        emit = patchlib.asm_thumb(_emit_status_src(), EMIT_STATUS)
        patchlib.write_bytes(img, va_to_off(EMIT_STATUS), emit)
    if "setvolume" in features:
        patchlib.write_bytes(img, va_to_off(STR_SETVOL), b"set-volume\x00")
        sv = patchlib.asm_thumb(_set_volume_src(), SET_VOLUME)
        patchlib.write_bytes(img, va_to_off(SET_VOLUME), sv)
    if needs_dispatch:
        displaced = patchlib.detour(img, CMD_DISPATCH, CAVE_DISPATCH)
        part1 = patchlib.asm_thumb(_cave_dispatch_part1(features), CAVE_DISPATCH)
        cont_va = CAVE_DISPATCH + len(part1) + len(displaced)
        bw = patchlib.asm_thumb(f"b.w #{CMD_DISPATCH + len(displaced)}", cont_va)
        blob = part1 + displaced + bw
        patchlib.write_bytes(img, va_to_off(CAVE_DISPATCH), blob)
    return img
