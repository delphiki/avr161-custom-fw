// AnnotateAVR.java - annotations firmware AVR161 V002.20 (genere)
// Ghidra 12.2 : scripts Jython retires -> version Java.
// @category AVR161
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;

public class AnnotateAVR extends GhidraScript {
    int nf=0, nd=0, ns=0;
    public void run() throws Exception {
        annFunc(0x0809534cL, "strcmp", "");
        annFunc(0x080953d0L, "strlen", "");
        annFunc(0x08095408L, "strcat_at", "strcat sur (buf+len)");
        annFunc(0x080953b8L, "memset", "");
        annFunc(0x0805975eL, "osd_print", "affiche une chaine (display)");
        annFunc(0x0804f328L, "cmd_dispatch", "chaine de strcmp ; r0 = nom de commande recu");
        annFunc(0x0804f44aL, "source_selection_handler", "branche source-selection (dispatch par para)");
        annData(0x0804f348L, "HOOK_get_status", "<- bl build_reply branche heart-alive : point d'injection get-status");
        annFunc(0x0804fe7cL, "build_reply", "build_reply(name,zone,para) -> reponse HTTP+XML dans net_response_buf");
        annFunc(0x0804fdd4L, "int2dec", "entier 0..999 -> decimal dans int2dec_buf (Content-Length)");
        annFunc(0x08087e0cL, "net_send", "envoie net_response_buf (0x2000a0b4)");
        annFunc(0x080718d8L, "net_bye_bye_push", "envoie un <status> 'bye-bye'");
        annData(0x2000e213L, "g_volume", "octet : volume courant (lu par OSD VOLUME:)");
        annData(0x2000de40L, "g_flags", "flags ; bit1 = MUTE");
        annData(0x2000e1abL, "g_src_switch_flag", "mis a 0x19 pendant un changement de source");
        annData(0x2000a0b4L, "net_response_buf", "buffer HTTP sortant");
        annData(0x2000d7c8L, "g_host_ip_str", "chaine IP (Host:)");
        annData(0x2000cb1cL, "g_status_ctx", "compare a 'status_name' dans build_reply");
        annData(0x2000dee4L, "int2dec_buf", "buffer du convertisseur int->dec");
        annFunc(0x080190d0L, "set_src_CableSat", "");
        annFunc(0x080191bcL, "set_src_Disc", "");
        annFunc(0x08019238L, "set_src_MediaServer", "aussi 'Server'");
        annFunc(0x08019308L, "set_src_Game", "");
        annFunc(0x080193d8L, "set_src_Audio", "");
        annFunc(0x0801942cL, "set_src_Radio", "");
        annFunc(0x0801963cL, "set_src_iPod", "");
        annFunc(0x0801a9c6L, "set_src_vTuner_InetRadio", "");
        annFunc(0x0801abd2L, "set_src_HomeNetwork", "");
        annFunc(0x0801899cL, "set_src_UNKNOWN_1", "candidate (TV/USB/STB/AUX/FM/AM/BT/SourceA-D)");
        annFunc(0x08019148L, "set_src_UNKNOWN_2", "candidate");
        annFunc(0x080192a0L, "set_src_UNKNOWN_3", "candidate");
        annFunc(0x0801936aL, "set_src_UNKNOWN_4", "candidate");
        annFunc(0x0801947cL, "set_src_UNKNOWN_5", "candidate media");
        annFunc(0x080194c8L, "set_src_UNKNOWN_6", "candidate media");
        annFunc(0x08019528L, "set_src_UNKNOWN_7", "candidate media");
        annFunc(0x080195d8L, "set_src_UNKNOWN_8", "candidate media");
        annFunc(0x08019690L, "set_src_UNKNOWN_9", "candidate media");
        annFunc(0x08019704L, "set_src_UNKNOWN_10", "candidate media");
        annFunc(0x080197a8L, "set_src_UNKNOWN_11", "candidate media");
        annFunc(0x08031080L, "src_dispatch_av_inputs", "switch entrees AV (HDMI/analog)");
        annFunc(0x0802bb00L, "src_dispatch_media_menu", "zone menu sources media (iPod...)");
        annData(0x08053684L, "tbl_source_display", "table enum->nom affiche");
        annData(0x080536b0L, "tbl_src_disp_BLUETOOTH", "slot BLUETOOTH de la table d'affichage");
        annData(0x080d98f0L, "str_disp_BLUETOOTH", "'BLUETOOTH' (suivre xrefs pour le menu BT)");
        annData(0x080d4478L, "str_reply_prefix", "prefixe gabarit XML");
        annData(0x080d5b38L, "str_reply_suffix", "suffixe gabarit XML");
        annData(0x080dd2fcL, "str_source_selection", "'source-selection'");
        annData(0x080deef4L, "str_heart_alive", "'heart-alive'");
        println("Annotation AVR161 : "+nf+" fonctions, "+nd+" labels, "+ns+" ignores.");
        println("Etape suivante : xrefs de str_disp_BLUETOOTH (0x080d98f0) -> fonction set_src_Bluetooth. Voir README.md");
    }
    void annFunc(long addr, String name, String cmt) {
        try {
            Address a = toAddr(addr);
            Function f = getFunctionAt(a);
            if (f == null) { try { disassemble(a); } catch (Exception e) {} f = createFunction(a, name); }
            if (f != null) f.setName(name, SourceType.USER_DEFINED);
            else createLabel(a, name, true);
            if (!cmt.isEmpty()) setPlateComment(a, cmt);
            nf++;
        } catch (Exception e) { ns++; println("skip "+Long.toHexString(addr)+" "+name+": "+e); }
    }
    void annData(long addr, String name, String cmt) {
        try {
            Address a = toAddr(addr);
            createLabel(a, name, true);
            if (!cmt.isEmpty()) setPlateComment(a, cmt);
            nd++;
        } catch (Exception e) { ns++; println("skip "+Long.toHexString(addr)+" "+name+": "+e); }
    }
}
