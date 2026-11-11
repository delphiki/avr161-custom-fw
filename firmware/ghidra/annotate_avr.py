# Ghidra annotation script — AVR 161/1610 firmware V002.20
# Pose labels + commentaires des fonctions/variables trouvées en RE (voir ../re/NOTES.md).
# Import du .fw : Raw Binary, ARM:LE:32:Cortex, base 0x08000000.
# @category AVR161
# @runtime Jython

fpapi = None
try:
    # FlatProgramAPI est dispo globalement dans un GhidraScript
    createFunction  # noqa
    _flat = True
except NameError:
    _flat = False


def A(x):
    return toAddr(x)


# (adresse, type, nom, commentaire)
#  type: "func" = fonction (Thumb), "var"/"ptr"/"data" = label de donnée
ENTRIES = [
    # --- primitives libc ---
    (0x809534c, "func", "strcmp", ""),
    (0x80953d0, "func", "strlen", ""),
    (0x8095408, "func", "strcat_at", "strcat sur (buf+len)"),
    (0x80953b8, "func", "memset", ""),
    (0x805975e, "func", "osd_print", "affiche une chaine (display)"),

    # --- reseau / protocole port 10025 ---
    (0x804f328, "func", "cmd_dispatch", "chaine de strcmp ; r0 = nom de commande recu"),
    (0x804f44a, "func", "source_selection_handler", "branche source-selection (dispatch par para)"),
    (0x804f348, "data", "HOOK_get_status", "<-- bl BUILD_REPLY de la branche heart-alive : point d'injection get-status"),
    (0x804fe7c, "func", "build_reply", "build_reply(name,zone,para) -> reponse HTTP+XML dans net_response_buf"),
    (0x804fdd4, "func", "int2dec", "entier 0..999 -> chaine decimale dans int2dec_buf (Content-Length)"),
    (0x8087e0c, "func", "net_send", "envoie net_response_buf (0x2000a0b4)"),
    (0x80718d8, "func", "net_bye_bye_push", "envoie un <status> 'bye-bye' (push a la deconnexion)"),

    # --- variables d'etat (RAM) ---
    (0x2000e213, "var", "g_volume", "octet : volume courant (lu par l'OSD VOLUME:)"),
    (0x2000de40, "var", "g_flags", "octet de flags ; bit1 = MUTE (ubfx #1,#1)"),
    (0x2000e1ab, "var", "g_src_switch_flag", "mis a 0x19 pendant un changement de source"),
    (0x2000a0b4, "var", "net_response_buf", "buffer HTTP sortant"),
    (0x2000d7c8, "var", "g_host_ip_str", "chaine IP (Host:)"),
    (0x2000cb1c, "var", "g_status_ctx", "compare a 'status_name' dans build_reply (mode valeurs)"),
    (0x2000dee4, "var", "int2dec_buf", "buffer du convertisseur int->dec"),

    # --- fonctions de bascule de source (9 identifiees) ---
    (0x80190d0, "func", "set_src_CableSat", ""),
    (0x80191bc, "func", "set_src_Disc", ""),
    (0x8019238, "func", "set_src_MediaServer", "aussi 'Server'"),
    (0x8019308, "func", "set_src_Game", ""),
    (0x80193d8, "func", "set_src_Audio", ""),
    (0x801942c, "func", "set_src_Radio", ""),
    (0x801963c, "func", "set_src_iPod", ""),
    (0x801a9c6, "func", "set_src_vTuner_InetRadio", ""),
    (0x801abd2, "func", "set_src_HomeNetwork", ""),

    # --- candidates NON identifiees (dont Bluetooth) : a nommer dans Ghidra ---
    (0x801899c, "func", "set_src_UNKNOWN_1", "candidate (TV/USB/STB/AUX/FM/AM/BT/SourceA-D)"),
    (0x8019148, "func", "set_src_UNKNOWN_2", "candidate"),
    (0x80192a0, "func", "set_src_UNKNOWN_3", "candidate"),
    (0x801936a, "func", "set_src_UNKNOWN_4", "candidate"),
    (0x801947c, "func", "set_src_UNKNOWN_5", "candidate (cluster media)"),
    (0x80194c8, "func", "set_src_UNKNOWN_6", "candidate (cluster media)"),
    (0x8019528, "func", "set_src_UNKNOWN_7", "candidate (cluster media)"),
    (0x80195d8, "func", "set_src_UNKNOWN_8", "candidate (cluster media)"),
    (0x8019690, "func", "set_src_UNKNOWN_9", "candidate (cluster media)"),
    (0x8019704, "func", "set_src_UNKNOWN_10", "candidate (cluster media)"),
    (0x80197a8, "func", "set_src_UNKNOWN_11", "candidate (cluster media)"),

    # --- dispatchers appelant les set_src_* (menus / facade / telecommande) ---
    (0x8031080, "func", "src_dispatch_av_inputs", "switch entrees AV (HDMI/analog)"),
    (0x802bb00, "func", "src_dispatch_media_menu", "zone menu sources media (contient iPod, etc.)"),

    # --- tables / chaines ---
    (0x8053684, "data", "tbl_source_display", "table enum->nom affiche (…TV, BLUETOOTH@+0x2c, USB…)"),
    (0x80536b0, "data", "tbl_src_disp_BLUETOOTH", "slot BLUETOOTH de la table d'affichage"),
    (0x80d98f0, "data", "str_disp_BLUETOOTH", "'BLUETOOTH       ' (suivre les xrefs pour le menu BT)"),
    (0x80d4478, "data", "str_reply_prefix", "<?xml ...><harman><avr><common><status><name>"),
    (0x80d5b38, "data", "str_reply_suffix", "</para></status></common></avr></harman>"),
    (0x80dd2fc, "data", "str_source_selection", "'source-selection'"),
    (0x80deef4, "data", "str_heart_alive", "'heart-alive'"),
]


def run():
    nfunc = nlabel = 0
    for addr, kind, name, cmt in ENTRIES:
        try:
            a = A(addr)
            if kind == "func":
                f = getFunctionAt(a)
                if f is None:
                    try:
                        disassemble(a)
                    except Exception:
                        pass
                    f = createFunction(a, name)
                if f is not None:
                    f.setName(name, ghidra.program.model.symbol.SourceType.USER_DEFINED)
                    nfunc += 1
                else:
                    createLabel(a, name, True)
                    nlabel += 1
            else:
                createLabel(a, name, True)
                nlabel += 1
            if cmt:
                setPlateComment(a, cmt)
        except Exception as e:
            print("skip %08x %s : %s" % (addr, name, e))
    print("Annotation terminee : %d fonctions, %d labels." % (nfunc, nlabel))
    print("Prochaine etape : suivre les xrefs de str_disp_BLUETOOTH (0x080d98f0) "
          "pour identifier la fonction set_src_Bluetooth. Voir README.md.")


run()
