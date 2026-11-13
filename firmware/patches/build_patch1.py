"""Build du firmware patché #1 (rempli task par task). cf. ../patches/DESIGN-patch1.md."""
import patchlib

CAVE_VA = 0x080E0000  # base du code-cave (zone réécrite, 128 Ko de 0xFF)

# Version du firmware CUSTOM (indépendante du stock V002.20). Source unique de vérité :
# embarquée dans le firmware (4e champ de get-status) + nom de l'artefact + tag de release.
FW_VERSION = "1.1.0"

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
A_MUTE       = 0x2000dddc          # bit 4 = son coupé (bascule FUN_0801b030). Jusqu'à la
                                   # v1.1.0-test on lisait à tort le bit 1 de 0x2000de40.
MUTE_SHIFT   = 4
A_MUTE_LEGACY = 0x2000de40         # feature `legacymute` : ancien indicateur (bit 1), TOUJOURS faux.
LEGACY_MUTE_SHIFT = 1              # Ne sert qu'à reconstruire à l'identique les images publiées
                                   # jusqu'à la v1.1.0, qui lisaient cet octet.
A_STR_MUTEON  = 0x080df504         # "mute-on" (flash stock)
A_STR_MUTEOFF = 0x080def78         # "mute-off"
A_SRC        = 0x2000e1ae          # source enum (u8)
F_VOLUP      = 0x0801b568          # vol_up()  (incrémente+applique 0x2000e1b8)
F_VOLDOWN    = 0x0801b8f0          # vol_down()
VOL_MAX      = 180                 # 0..0xB4
# keepsleep : tick 1 s du compteur sleep -> extinction complète (3600 s, 0x2000dd7c).
# Stock : `beq 0x08010b40` (saute le décompte si compteur nul) ; patch : `b` inconditionnel.
SLEEP_TICK_BEQ   = 0x08010afe
SLEEP_TICK_AFTER = 0x08010b40
# push : le bloc du décompte (mort avec keepsleep) appelle push_tick une fois par seconde.
SLEEP_TICK_BLOCK = 0x08010af6      # 1re instruction du bloc (ldr.w r0,=timer ; ldr r0,[r0])
A_MAINZONE   = 0x080def00          # "Main Zone\0" (flash stock)
PUSH_RAM     = 0x2001ff00          # RAM inutilisée (au-dessus de CSTACK, fin 0x2000f2e0 ; non
                                   # initialisée au démarrage) : [0]=vol [1]=mute|pwr<<1 [2]=src
                                   # [3]=0xA5 (état valide) [4]=compteur « client vivant » (s)
PUSH_MAGIC   = 0xA5
PUSH_ALIVE_SECS = 90               # un client muet depuis plus longtemps ne reçoit plus de push
A_STEPTMR    = 0x2000e1cd          # < 0xd -> vol_up/down font un pas de 2, sinon 4 (posé à 0x14 après un pas)
F_SETSRCBT   = 0x0801af34          # set_src_Bluetooth() (auto-suffisant)
F_SRCCOMMIT  = 0x08018944          # post-step source (comme la branche HomeNetwork)
A_SWFLAG     = 0x2000e1ab          # g_src_switch_flag (=0x19 pendant un switch)
A_PWRZONE    = 0x2000ddd4          # flags power/zone (bit1 -> condition post-step)

# --- layout du cave (zone réécrite 0x080E0000) ---
STR_GETSTATUS = CAVE_VA + 0x000    # "get-status\0"
STR_COMMA     = CAVE_VA + 0x010    # ",\0"
STR_SETVOL    = CAVE_VA + 0x018    # "set-volume\0"
STR_SOURCESEL = CAVE_VA + 0x024    # "source-selection\0" (17 o ; APRÈS "set-volume\0" qui finit à +0x22)
STR_BLUETOOTH = CAVE_VA + 0x035    # "Bluetooth\0" (10 o, finit à +0x3e < EMIT_STATUS)
STR_FWVER     = CAVE_VA + 0x3c0    # version custom (ex. "1.0.0\0") — 4e champ de get-status
EMIT_STATUS   = CAVE_VA + 0x040    # routine emit_status
SET_VOLUME    = CAVE_VA + 0x280    # routine set_volume
BT_HANDLER    = CAVE_VA + 0x340    # routine bascule Bluetooth
CAVE_DISPATCH = CAVE_VA + 0x180    # entrée depuis le trampoline
PUSH_TICK     = CAVE_VA + 0x440    # routine push_tick (appelée par le tick 1 s)
STR_SETSUR    = CAVE_VA + 0x3d0    # "set-surround\0" (la version à +0x3c0 fait au plus 11 o)
SET_SURROUND  = CAVE_VA + 0x500    # routine set_surround

# surround : mode surround courant et sélection directe.
A_AUDIOPTR   = 0x2000dbf0          # -> structure audio de la source courante ; +0x11 = mode appliqué
SUR_MODE_OFF = 0x11
F_SURSET     = 0x0803a434          # (mode) : si le mode est possible avec le signal courant,
                                   # le mémorise pour la source courante et l'applique
F_SURAUTO    = 0x0803b120          # (1) -> mode que « Auto Select » choisirait maintenant
F_SURAPPLY   = 0x0803b038          # (mode, 1) : passe la source en Auto Select et applique
                                   # u16 à +0 de la structure : 3 bits bas = catégorie mémorisée
                                   # (0 Auto Select, 1 virtuel, 2 stéréo, 3 NSP, 4 film, 5 musique, 6 jeu)
SUR_MAX      = 0x2d                # dernier mode nommé de la table 0x080d2fe0 (HARMAN NSP)
A_PWRSEQ     = 0x2000dd5c          # u32 : != 0 pendant une séquence d'allumage/extinction
A_FLAGS_DDCC = 0x2000ddcc          # bit 7 : garde de la commande stock surround-mode
SUR_BUSY     = 10                  # valeur posée dans A_SWFLAG par la commande stock
OSD_RECOLOR   = CAVE_VA + 0x400    # routine osd_recolor + sa table (osdgreen)

# osdgreen : le bleu du menu à l'écran devient vert (repère visuel « firmware custom »).
# Couleurs OSD du SiI9575 : 6 bits RRGGBB. FUN_08096598 recopie les 8 couleurs de la ressource
# de fenêtre dans la structure (sl+0x32..+0x39), puis appelle memcpy : on détourne ce `bl`.
OSD_COPY_BL   = 0x080967dc         # bl memcpy (stock), juste après la copie des couleurs
F_MEMCPY      = 0x080a7e14
OSD_COLOR_OFF = 0x32               # 1re couleur dans la structure de fenêtre (sl)
OSD_COLOR_CNT = 8
OSD_GREEN_MAP = (                  # (bleu stock, vert)
    (0x07, 0x08),                  # barre de sélection des menus
    (0x0b, 0x0c),                  # titres (lignes « désactivées » des fenêtres de titre)
    (0x03, 0x08),                  # fond des fenêtres d'état locales
    (0x1b, 0x1d),                  # bordures
    (0x16, 0x19),
)
OSD_MSGBOX_BLUE = (0x0809761e, 0x08097644)   # movs r2,#3 : titre et bordure des boîtes de message
OSD_MSGBOX_GREEN = 0x08

# netoff : le module réseau reste alimenté ampli éteint. Son convertisseur est sur le rail de
# veille ST+5V ; NET_PWR_SW = PD9 le coupe, BCO_RST = PD8 le tient en reset (schéma p. 169/171).
# Séquence d'extinction FUN_0801396c, extinction complète demandée (bit 7 de 0x2000dddc) :
NETOFF_C6_BPL  = 0x0801410c        # pas 0xc6 : `bpl` vers la branche sleep (PD9 = 1, PD8 intact)
NETOFF_C6_KEEP = 0x08014128        # ... qu'on prend toujours
NETOFF_AF_MOV  = 0x08014312        # pas 0xaf : `mov.w r1,#0x200 ; ldr r0,=GPIOD ; bl gpio_clear`
NETOFF_AF_BL   = 0x0801431a        # -> `mov.w r1,#0x100 ; ... ; bl gpio_set` : PD8 = 1 (sortie de
                                   # reset), 23 pas après la mise sous tension. Nécessaire au
                                   # démarrage en veille (rebranchement secteur), où PD8 est bas.
F_GPIO_CLEAR   = 0x08040a88
F_GPIO_SET     = 0x08040a84
STR_FULLOFF    = CAVE_VA + 0x3e0   # "power-full-off\0"
FULL_OFF       = CAVE_VA + 0x600   # routine power-full-off
A_OFFFLAGS     = 0x2000dddc        # bit 7 = extinction complète demandée
A_FLAGS_DDE0   = 0x2000dde0
A_PWRDELAY     = 0x2000e1dd        # action d'alimentation différée (tics)
A_SLEEPTIMER   = 0x2000dd7c        # != 0 : ampli en sleep, temporisation armée


def _lo(a): return a & 0xffff
def _hi(a): return (a >> 16) & 0xffff
def _mw(reg, a): return f"movw {reg}, #{_lo(a):#x}\nmovt {reg}, #{_hi(a):#x}\n"


PARA_BUF_SIZE = 32                 # "180,1,17,1.1.0-test,1,45,6\0" : 27 o au plus


def _emit_status_src(surround=False, legacy_mute=False):
    """get-status -> para "vol,mute,src,<version>,pwr" (pwr : 1 = allumé, 0 = sleep).
    r4 = struct commande, r5 = PARA_BUF (pile). Trois sous-routines locales évitent de
    répéter les séquences d'ajout (la routine doit tenir dans son créneau du cave)."""
    return (
        "push {r4,r5,r6,lr}\n"
        "mov r4, r0\n"                       # r4 = struct (name@0, zone@0x20, para@0x40)
        f"sub sp, #{PARA_BUF_SIZE}\n"
        "mov r5, sp\n"                       # r5 = PARA_BUF (pile)
        # ctx = "status_name"  (memset puis strcpy depuis 0x80defc0)
        + _mw("r0", A_CTX) + "movs r1, #0\nmovs r2, #12\n" + f"bl #{F_MEMSET}\n"
        + _mw("r0", A_CTX) + _mw("r1", A_STATUSNAME) + f"bl #{F_STRCAT}\n"
        # PARA_BUF = ""
        + f"mov r0, r5\nmovs r1, #0\nmovs r2, #{PARA_BUF_SIZE}\n" + f"bl #{F_MEMSET}\n"
        # vol,
        + _mw("r0", A_VOL) + "ldrb r0, [r0]\nbl app_dec\nbl app_comma\n"
        # mute = (*flags >> 1) & 1 ,
        + (_mw("r0", A_MUTE_LEGACY) + "ldrb r0, [r0]\nbl app_bit1\nbl app_comma\n" if legacy_mute else
           _mw("r0", A_MUTE) + f"ldrb r0, [r0]\nlsrs r0, r0, #{MUTE_SHIFT - 1}\nbl app_bit1\nbl app_comma\n")
        # src,
        + _mw("r0", A_SRC) + "ldrb r0, [r0]\nbl app_dec\nbl app_comma\n"
        # <version firmware custom>,
        + _mw("r1", STR_FWVER) + "bl app_str\nbl app_comma\n"
        # pwr = (*power_flags >> 1) & 1   (5e champ, v1.0.5)
        + _mw("r0", A_PWRZONE) + "ldrb r0, [r0]\nbl app_bit1\n"
        # mode surround appliqué (6e champ) et catégorie mémorisée (7e) — feature surround
        + ("bl app_comma\n" + _mw("r0", A_AUDIOPTR)
           + f"ldr r0, [r0]\nldrb r0, [r0, #{SUR_MODE_OFF}]\nbl app_dec\nbl app_comma\n"
           + _mw("r0", A_AUDIOPTR) + "ldr r0, [r0]\nldrb r0, [r0]\nand r0, r0, #7\nbl app_dec\n"
           if surround else "")
        # build_reply(name=get-status, zone=struct+0x20, para=PARA_BUF)
        + _mw("r0", STR_GETSTATUS) + "add r1, r4, #0x20\nmov r2, r5\n" + f"bl #{F_BUILDREPLY}\n"
        # net_send(net_response_buf)
        + _mw("r0", A_NETBUF) + f"bl #{F_NETSEND}\n"
        # restaurer ctx : 0x2000cb1c[0] = 0  (chaîne vide != "status_name" -> heart-alive intact)
        + _mw("r0", A_CTX) + "movs r1, #0\nstrb r1, [r0]\n"
        + f"add sp, #{PARA_BUF_SIZE}\n"
        "pop {r4,r5,r6,pc}\n"
        # --- sous-routines locales (r5 = PARA_BUF) ---
        "app_bit1:\n"                        # ajoute le bit 1 de r0 en décimal
        "lsrs r0, r0, #1\nand r0, r0, #1\n"
        "app_dec:\n"                         # ajoute r0 en décimal
        "push {r6,lr}\n"
        f"bl #{F_INT2DEC}\nmov r1, r0\nbl app_str\n"
        "pop {r6,pc}\n"
        "app_comma:\n"                       # ajoute ","
        + _mw("r1", STR_COMMA) +
        "app_str:\n"                         # ajoute la chaîne r1
        "push {r6,lr}\nmov r6, r1\n"
        f"mov r0, r5\nbl #{F_STRLEN}\nadd r0, r5, r0\n"
        f"mov r1, r6\nbl #{F_STRCAT}\n"
        "pop {r6,pc}\n"
    )


def _set_volume_src():
    # r0 = struct commande entrante (name@0, zone@0x20, para@0x40).
    # Règle le volume à la valeur absolue de `para`, en UN coup et PILE sur la cible :
    #   1. cur = master (0x2000e1b8) ; si cur == cible -> rien à faire.
    #   2. pas = celui que fera le firmware (cf. vol_down 0x801b8f0 / vol_up 0x801b568) :
    #        descente : 2 si *0x2000e1cd < 0xd, sinon 4
    #        montée   : 2 si *0x2000e1cd < 0xd OU master pré-jumpé > 0x8b, sinon 4
    #                   (=> 4 seulement si timer >= 0xd et cible <= 143)
    #   3. pré-jump : master = cible+pas (descente) ou cible-pas (montée), clampé 0..180.
    #   4. UN pas volume-down/volume-up synthétisé via cmd_dispatch (chemin stock complet :
    #      gardes, application matériel, OSD) -> master == cible.
    #   5. si le pas a été REFUSÉ (gardes vol_up/down, cooldown 0x2000e2a6 du dispatch) le
    #      master vaut encore la valeur pré-jumpée -> on RESTAURE cur (jamais de variable
    #      master désynchronisée du matériel).
    # Aux butées (cible+pas > 180 ou cible-pas < 0) le pré-jump est clampé : on atterrit à
    # un pas de la cible au pire.
    # Compact (<= 0xa0 octets) : l'empreinte du cave ne doit pas dépasser celle de v1.0.2
    # (cf. test_set_volume_footprint_stays_within_proven_region).
    assert A_STEPTMR - A_VOL == 0x15
    return (
        "push {r4,r5,r6,r7,lr}\n"
        "mov r7, r0\n"                       # r7 = struct entrant (puis valeur pré-jump)
        "sub sp, #0x50\n"                    # 0x48 struct synthétisé + [sp,#0x48] = &master
        "mov r4, sp\n"                       # r4 = struct synthétisé
        # --- atoi(struct+0x40) -> r5, clamp 0..180 ---
        "add r1, r7, #0x40\n"
        "movs r5, #0\n"
        "atoi_loop:\n"
        "ldrb r2, [r1]\n"
        "subs r2, r2, #0x30\n"
        "cmp r2, #9\n"
        "bhi atoi_done\n"
        "movs r0, #10\n"
        "muls r5, r0, r5\n"
        "adds r5, r5, r2\n"
        f"cmp r5, #{VOL_MAX}\n"              # clamp à chaque chiffre (pas de débordement)
        "bls atoi_next\n"
        f"movs r5, #{VOL_MAX}\n"
        "atoi_next:\n"
        "adds r1, r1, #1\n"
        "b atoi_loop\n"
        "atoi_done:\n"
        # --- &master gardé en pile ; cur -> r6 ; déjà à la cible ? ---
        + _mw("r0", A_VOL) + "str r0, [sp, #0x48]\n"
        "ldrb r6, [r0]\n"
        "cmp r6, r5\n"
        "beq sv_end\n"
        # --- struct synthétisé : zone recopiée, para = "" (le nom est posé plus bas) ---
        "add r0, r4, #0x20\nadd r1, r7, #0x20\n" + f"bl #{F_STRCAT}\n"
        "movs r1, #0\nstr r1, [sp, #0x40]\n"
        # --- r0 = &master (conservé jusqu'au strb), r2 = timer de pas, r3 = pas, r1 = nom ---
        "ldr r0, [sp, #0x48]\n"
        "ldrb r2, [r0, #0x15]\n"             # *0x2000e1cd
        "movs r3, #2\n"
        + _mw("r1", 0x080def60) +            # "volume-up"
        "cmp r6, r5\n"
        "bhi sv_down\n"
        # montée : pas de 4 seulement si timer >= 0xd ET cible <= 143
        "cmp r2, #0xd\n"
        "blo sv_up_s\n"
        "cmp r5, #143\n"
        "bhi sv_up_s\n"
        "movs r3, #4\n"
        "sv_up_s:\n"
        "subs r7, r5, r3\n"                  # pré-jump = cible - pas (>= 0)
        "bpl sv_go\n"
        "movs r7, #0\n"
        "b sv_go\n"
        "sv_down:\n"
        "adds r1, #0xc\n"                    # "volume-down" = "volume-up" + 0xc (0x080def6c)
        "cmp r2, #0xd\n"                     # descente : pas de 4 si timer >= 0xd
        "blo sv_dn_s\n"
        "movs r3, #4\n"
        "sv_dn_s:\n"
        "adds r7, r5, r3\n"                  # pré-jump = cible + pas (<= 180)
        f"cmp r7, #{VOL_MAX}\n"
        "bls sv_go\n"
        f"movs r7, #{VOL_MAX}\n"
        "sv_go:\n"
        "strb r7, [r0]\n"                    # *master = pré-jump
        "mov r0, r4\n" + f"bl #{F_STRCAT}\n"     # strcpy(synth, name)
        "mov r0, r4\n" + f"bl #{CMD_DISPATCH}\n"  # UN pas par le chemin stock
        # --- pas refusé ? (master toujours == pré-jump) -> restaurer cur ---
        "ldr r0, [sp, #0x48]\n"
        "ldrb r3, [r0]\n"
        "cmp r3, r7\n"
        "bne sv_end\n"
        "strb r6, [r0]\n"
        "sv_end:\n"
        "add sp, #0x50\n"
        "pop {r4,r5,r6,r7,pc}\n"
    )


def _bt_handler_src():
    # Bascule Bluetooth — réplique la branche réseau HomeNetwork (review #4).
    return (
        "push {lr}\n"
        + _mw("r0", A_SWFLAG) + "movs r1, #0x19\nstrb r1, [r0]\n"   # g_src_switch_flag = 0x19
        + f"bl #{F_SETSRCBT}\n"                                     # set_src_Bluetooth()
        # post-step conditionnel : si bit1 de *0x2000ddd4 == 0 -> FUN_08018944()
        + _mw("r0", A_PWRZONE) + "ldrb r0, [r0]\nlsrs r0, r0, #1\nand r0, r0, #1\n"
        "cmp r0, #0\nbne bt_skip\n"
        + f"bl #{F_SRCCOMMIT}\n"
        "bt_skip:\n"
        "pop {pc}\n"
    )


def _push_tick_src(surround=False, legacy_mute=False):
    """Appelée une fois par seconde (boucle principale). Compare l'état courant au dernier
    état envoyé et, s'il a changé et qu'un client s'est manifesté récemment, émet le même
    message que la réponse à get-status. r4 = PUSH_RAM, r5 = état courant empaqueté."""
    return (
        "push {r4,r5,r6,lr}\n"
        + _mw("r4", PUSH_RAM)
        + _mw("r0", A_VOL) + "ldrb r5, [r0]\n"
        + (_mw("r0", A_MUTE_LEGACY) + f"ldrb r0, [r0]\nlsrs r0, r0, #{LEGACY_MUTE_SHIFT}\nand r0, r0, #1\n"
           if legacy_mute else
           _mw("r0", A_MUTE) + f"ldrb r0, [r0]\nlsrs r0, r0, #{MUTE_SHIFT}\nand r0, r0, #1\n") +
        "orr r5, r5, r0, lsl #8\n"
        + _mw("r0", A_PWRZONE) + "ldrb r0, [r0]\nand r0, r0, #2\n"
        "orr r5, r5, r0, lsl #8\n"
        + _mw("r0", A_SRC) + "ldrb r0, [r0]\n"
        "orr r5, r5, r0, lsl #16\n"
        f"orr r5, r5, #{PUSH_MAGIC << 24:#x}\n"
        + (_mw("r0", A_AUDIOPTR) + f"ldr r0, [r0]\nldrb r6, [r0, #{SUR_MODE_OFF}]\n"
           "ldrb r0, [r0]\nand r0, r0, #7\norr r6, r6, r0, lsl #8\n" if surround else "") +
        "ldr r0, [r4]\n"
        f"lsrs r1, r0, #24\ncmp r1, #{PUSH_MAGIC:#x}\nbne pt_init\n"   # RAM jamais initialisée
        "ldrb r1, [r4, #4]\ncmp r1, #0\nbeq pt_resync\n"              # aucun client récent
        "subs r1, r1, #1\nstrb r1, [r4, #4]\n"
        "cmp r0, r5\nbne pt_changed\n"
        + ("ldrh.w r1, [r4, #5]\ncmp r1, r6\n" if surround else "") +
        "beq pt_done\n"
        "pt_changed:\n"
        "str r5, [r4]\n"
        + ("strh.w r6, [r4, #5]\n" if surround else "")
        + _mw("r0", A_MAINZONE - 0x20) + f"bl #{EMIT_STATUS}\n"         # zone lue à r0+0x20
        "pt_done:\n"
        "pop {r4,r5,r6,pc}\n"
        "pt_init:\n"
        "movs r1, #0\nstrb r1, [r4, #4]\n"
        "pt_resync:\n"
        "str r5, [r4]\n"
        + ("strh.w r6, [r4, #5]\n" if surround else "") +
        "pop {r4,r5,r6,pc}\n"
    )


def _set_surround_src():
    """set-surround <code décimal 0..SUR_MAX> : sélection directe d'un mode surround.
    set-surround auto : retour à Auto Select (ce que fait le défilement stock pour la
    catégorie 0 : FUN_0803b038(FUN_0803b120(1), 1)) ; rien si la source y est déjà.
    r0 = struct commande (para@0x40). Mêmes gardes que la commande stock surround-mode
    (FUN_0801fe9c) ; sans chiffre, hors plage ou déjà appliqué : rien."""
    return (
        "push {r4,r5,lr}\n"
        "mov r4, r0\n"
        # allumé (bit 1) et bit 3 nul
        + _mw("r0", A_PWRZONE) + "ldrb r0, [r0]\nand r0, r0, #0x0a\ncmp r0, #2\nbne ss_end\n"
        + _mw("r0", A_PWRSEQ) + "ldr r0, [r0]\ncmp r0, #0\nbne ss_end\n"
        + _mw("r0", A_SWFLAG) + "ldrb r0, [r0]\ncmp r0, #0\nbne ss_end\n"
        + _mw("r0", A_FLAGS_DDCC) + "ldrb r0, [r0]\ntst r0, #0x80\nbne ss_end\n"
        "add r1, r4, #0x40\n"
        "ldr r2, [r1]\n" + _mw("r0", 0x6f747561) + "cmp r2, r0\nbne ss_number\n"   # "auto"
        "ldrb r2, [r1, #4]\ncmp r2, #0\nbeq ss_auto\n"
        "ss_number:\n"
        # atoi(para) -> r5 ; r3 = nombre de chiffres ; hors plage -> rien
        "movs r5, #0\nmovs r3, #0\n"
        "ss_digit:\n"
        "ldrb r2, [r1], #1\nsubs r2, r2, #0x30\ncmp r2, #9\nbhi ss_parsed\n"
        "movs r0, #10\nmuls r5, r0, r5\nadds r5, r5, r2\nadds r3, r3, #1\n"
        f"cmp r5, #{SUR_MAX}\nbhi ss_end\n"
        "b ss_digit\n"
        "ss_parsed:\n"
        "cmp r3, #0\nbeq ss_end\n"
        # déjà appliqué ?
        + _mw("r0", A_AUDIOPTR) + f"ldr r0, [r0]\nldrb r0, [r0, #{SUR_MODE_OFF}]\n"
        "cmp r0, r5\nbeq ss_end\n"
        + _mw("r0", A_SWFLAG) + f"movs r1, #{SUR_BUSY}\nstrb r1, [r0]\n"
        f"mov r0, r5\nbl #{F_SURSET}\n"
        "ss_end:\n"
        "pop {r4,r5,pc}\n"
        "ss_auto:\n"
        + _mw("r0", A_AUDIOPTR) + "ldr r0, [r0]\nldrb r0, [r0]\ntst r0, #7\nbeq ss_end\n"
        + _mw("r0", A_SWFLAG) + f"movs r1, #{SUR_BUSY}\nstrb r1, [r0]\n"
        f"movs r0, #1\nbl #{F_SURAUTO}\n"
        f"movs r1, #1\nbl #{F_SURAPPLY}\n"
        "pop {r4,r5,pc}\n"
    )


def _cave_dispatch_part1(features):
    # r0 = param_1 (name ptr) ; lr = retour vers l'appelant de cmd_dispatch (détour avant son push)
    s = "push {r0, r4, lr}\nmov r4, r0\n"
    if "push" in features:                    # toute commande reçue = un client est là
        s += _mw("r0", PUSH_RAM + 4) + f"movs r1, #{PUSH_ALIVE_SECS}\nstrb r1, [r0]\n"
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
    if "surround" in features:
        s += ("mov r0, r4\n" + _mw("r1", STR_SETSUR) + f"bl #{F_STRCMP}\n"
              "cmp r0, #0\nbne not_ss\n"
              f"mov r0, r4\nbl #{SET_SURROUND}\npop {{r0, r4, pc}}\n"
              "not_ss:\n")
    if "netoff" in features:
        s += ("mov r0, r4\n" + _mw("r1", STR_FULLOFF) + f"bl #{F_STRCMP}\n"
              "cmp r0, #0\nbne not_fo\n"
              f"bl #{FULL_OFF}\npop {{r0, r4, pc}}\n"
              "not_fo:\n")
    if "mute" in features:
        # mute-on / mute-off : le firmware d'origine BASCULE dans les deux cas. On avale la
        # commande si l'état est déjà le bon ; sinon elle poursuit jusqu'à la bascule stock.
        s += ("mov r0, r4\n" + _mw("r1", A_STR_MUTEON) + f"bl #{F_STRCMP}\n"
              "cmp r0, #0\nbne not_mon\n"
              + _mw("r0", A_MUTE) + f"ldrb r0, [r0]\ntst r0, #{1 << MUTE_SHIFT}\nbeq mute_pass\n"
              "pop {r0, r4, pc}\n"
              "not_mon:\n"
              "mov r0, r4\n" + _mw("r1", A_STR_MUTEOFF) + f"bl #{F_STRCMP}\n"
              "cmp r0, #0\nbne mute_pass\n"
              + _mw("r0", A_MUTE) + f"ldrb r0, [r0]\ntst r0, #{1 << MUTE_SHIFT}\nbne mute_pass\n"
              "pop {r0, r4, pc}\n"
              "mute_pass:\n")
    if "bluetooth" in features:
        # source-selection + para==Bluetooth -> bascule BT
        s += ("mov r0, r4\n" + _mw("r1", STR_SOURCESEL) + f"bl #{F_STRCMP}\n"
              "cmp r0, #0\nbne not_bt\n"
              "add r0, r4, #0x40\n" + _mw("r1", STR_BLUETOOTH) + f"bl #{F_STRCMP}\n"
              "cmp r0, #0\nbne not_bt\n"
              f"bl #{BT_HANDLER}\npop {{r0, r4, pc}}\n"
              "not_bt:\n")
    s += "pop {r0, r4, lr}\n"                 # pas pour nous -> restaurer, exécuter prologue déplacé
    return s


def _full_off_src():
    """power-full-off : extinction complète immédiate, par les trois écritures que fait le
    firmware à la réception de l'ordre de veille HDMI-CEC ou à la fin de la temporisation de
    sleep. Seulement si l'ampli est allumé ou en sleep (temporisation armée)."""
    return (
        _mw("r0", A_PWRZONE) + "ldrb r0, [r0]\ntst r0, #2\nbne fo_go\n"
        + _mw("r0", A_SLEEPTIMER) + "ldr r0, [r0]\ncmp r0, #0\nbeq fo_end\n"
        "fo_go:\n"
        + _mw("r0", A_OFFFLAGS) + "ldrb r1, [r0]\norr r1, r1, #0x80\nstrb r1, [r0]\n"
        + _mw("r0", A_FLAGS_DDE0) + "ldrb r1, [r0]\nbic r1, r1, #2\nstrb r1, [r0]\n"
        + _mw("r0", A_PWRDELAY) + "movs r1, #100\nstrb r1, [r0]\n"
        "fo_end:\n"
        "bx lr\n"
    )


def _osd_recolor_src():
    """Remplace les bleus connus des 8 couleurs de la fenêtre (sl) puis enchaîne sur memcpy
    avec ses arguments (r0-r2) et son adresse de retour (lr) intacts."""
    return (
        "push {r0-r4}\n"
        f"add r0, sl, #{OSD_COLOR_OFF}\n"
        f"movs r1, #{OSD_COLOR_CNT}\n"
        "next_colour:\n"
        "ldrb r2, [r0]\n"
        "adr r3, colour_map\n"
        "next_pair:\n"
        "ldrb r4, [r3], #2\n"
        "cmp r4, #0xff\n"
        "beq store\n"
        "cmp r4, r2\n"
        "bne next_pair\n"
        "ldrb r2, [r3, #-1]\n"
        "store:\n"
        "strb r2, [r0], #1\n"
        "subs r1, #1\n"
        "bne next_colour\n"
        "pop {r0-r4}\n"
        f"b.w #{F_MEMCPY}\n"
        ".align 2\n"
        "colour_map:\n"
        + "".join(f".byte {a:#x}, {b:#x}\n" for a, b in OSD_GREEN_MAP)
        + ".byte 0xff, 0xff\n"
    )


def build_patch1(img, features=frozenset(), version=None):
    """Construit l'image patchée pour les `features` demandées. `version` remplace
    FW_VERSION dans l'image (builds de test)."""
    features = set(features)
    if "push" in features and not {"getstatus", "keepsleep"} <= features:
        raise ValueError("push nécessite getstatus et keepsleep")
    if "surround" in features and "getstatus" not in features:
        raise ValueError("surround nécessite getstatus")
    needs_dispatch = bool(features & {"getstatus", "setvolume", "bluetooth", "netoff", "mute"})
    sur = "surround" in features
    legacy = "legacymute" in features
    if legacy and "mute" in features:
        raise ValueError("legacymute et mute sont incompatibles")
    claimed = []                              # plages [début, fin) déjà écrites dans le cave

    def put(va, data):
        """Écrit dans le cave en REFUSANT tout chevauchement avec une écriture précédente
        (un chevauchement de chaînes a rendu set-volume inopérant de v1.0.0 à v1.0.1)."""
        lo, hi = va, va + len(data)
        for clo, chi in claimed:
            if lo < chi and clo < hi:
                raise ValueError(f"chevauchement cave: [{lo:#x},{hi:#x}) vs [{clo:#x},{chi:#x})")
        claimed.append((lo, hi))
        patchlib.write_bytes(img, va_to_off(va), data)
    if "getstatus" in features:
        put(STR_GETSTATUS, b"get-status\x00")
        put(STR_COMMA, b",\x00")
        put(STR_FWVER, (version or FW_VERSION).encode() + b"\x00")
        emit = patchlib.asm_thumb(_emit_status_src(sur, legacy), EMIT_STATUS)
        put(EMIT_STATUS, emit)
    if "setvolume" in features:
        put(STR_SETVOL, b"set-volume\x00")
        sv = patchlib.asm_thumb(_set_volume_src(), SET_VOLUME)
        put(SET_VOLUME, sv)
    if "bluetooth" in features:
        put(STR_SOURCESEL, b"source-selection\x00")
        put(STR_BLUETOOTH, b"Bluetooth\x00")
        bt = patchlib.asm_thumb(_bt_handler_src(), BT_HANDLER)
        put(BT_HANDLER, bt)
    if sur:
        put(STR_SETSUR, b"set-surround\x00")
        put(SET_SURROUND, patchlib.asm_thumb(_set_surround_src(), SET_SURROUND))
    if "keepsleep" in features:
        stock_beq = patchlib.asm_thumb(f"beq #{SLEEP_TICK_AFTER}", SLEEP_TICK_BEQ)
        off = va_to_off(SLEEP_TICK_BEQ)
        if bytes(img[off:off + 2]) != stock_beq:
            raise ValueError("keepsleep: instruction inattendue au site du patch")
        patchlib.write_bytes(img, off, patchlib.asm_thumb(f"b #{SLEEP_TICK_AFTER}", SLEEP_TICK_BEQ))
    if "push" in features:
        put(PUSH_TICK, patchlib.asm_thumb(_push_tick_src(sur, legacy), PUSH_TICK))
        off = va_to_off(SLEEP_TICK_BLOCK)
        stock_head = patchlib.asm_thumb("ldr r0, [r0]", SLEEP_TICK_BLOCK + 4)
        if bytes(img[off + 4:off + 6]) != stock_head:
            raise ValueError("push: instructions inattendues au site du tick")
        hook = patchlib.asm_thumb(f"bl #{PUSH_TICK}\nb #{SLEEP_TICK_AFTER}", SLEEP_TICK_BLOCK)
        assert len(hook) == 6
        patchlib.write_bytes(img, off, hook)
    if "osdgreen" in features:
        off = va_to_off(OSD_COPY_BL)
        if bytes(img[off:off + 4]) != patchlib.asm_thumb(f"bl #{F_MEMCPY}", OSD_COPY_BL):
            raise ValueError("osdgreen: instruction inattendue au site de la copie des couleurs")
        put(OSD_RECOLOR, patchlib.asm_thumb(_osd_recolor_src(), OSD_RECOLOR))
        patchlib.write_bytes(img, off, patchlib.asm_thumb(f"bl #{OSD_RECOLOR}", OSD_COPY_BL))
        for va in OSD_MSGBOX_BLUE:
            off = va_to_off(va)
            if bytes(img[off:off + 2]) != patchlib.asm_thumb("movs r2, #3", va):
                raise ValueError("osdgreen: instruction inattendue dans la boîte de message")
            patchlib.write_bytes(img, off, patchlib.asm_thumb(f"movs r2, #{OSD_MSGBOX_GREEN}", va))
    if "netoff" in features:
        off = va_to_off(NETOFF_C6_BPL)
        if bytes(img[off:off + 2]) != patchlib.asm_thumb(f"bpl #{NETOFF_C6_KEEP}", NETOFF_C6_BPL):
            raise ValueError("netoff: instruction inattendue au pas 0xc6")
        patchlib.write_bytes(img, off, patchlib.asm_thumb(f"b #{NETOFF_C6_KEEP}", NETOFF_C6_BPL))
        off = va_to_off(NETOFF_AF_BL)
        if bytes(img[off:off + 4]) != patchlib.asm_thumb(f"bl #{F_GPIO_CLEAR}", NETOFF_AF_BL):
            raise ValueError("netoff: instruction inattendue au pas 0xaf")
        mov = va_to_off(NETOFF_AF_MOV)
        if bytes(img[mov:mov + 4]) != patchlib.asm_thumb("mov.w r1, #0x200", NETOFF_AF_MOV):
            raise ValueError("netoff: masque inattendu au pas 0xaf")
        patchlib.write_bytes(img, mov, patchlib.asm_thumb("mov.w r1, #0x100", NETOFF_AF_MOV))
        patchlib.write_bytes(img, off, patchlib.asm_thumb(f"bl #{F_GPIO_SET}", NETOFF_AF_BL))
        put(STR_FULLOFF, b"power-full-off\x00")
        put(FULL_OFF, patchlib.asm_thumb(_full_off_src(), FULL_OFF))
    if needs_dispatch:
        displaced = patchlib.detour(img, CMD_DISPATCH, CAVE_DISPATCH)
        part1 = patchlib.asm_thumb(_cave_dispatch_part1(features), CAVE_DISPATCH)
        cont_va = CAVE_DISPATCH + len(part1) + len(displaced)
        bw = patchlib.asm_thumb(f"b.w #{CMD_DISPATCH + len(displaced)}", cont_va)
        blob = part1 + displaced + bw
        put(CAVE_DISPATCH, blob)
    return img
