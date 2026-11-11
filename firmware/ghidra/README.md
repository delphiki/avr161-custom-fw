# Kit Ghidra — firmware AVR 161/1610 V002.20

Objectif : reprendre la RE dans Ghidra pour **épingler la fonction exacte de bascule Bluetooth**
(et plus largement finaliser get-status / set-volume). Le gros du mapping est déjà fait
(cf. `../re/NOTES.md`) ; ce kit l'importe automatiquement comme labels + commentaires.

## Le projet est DÉJÀ prêt

Un projet Ghidra importé + analysé + **annoté** a été généré en mode headless :
`AVR161.gpr` (+ `AVR161.rep/`) dans ce dossier.

Pour l'ouvrir :
1. Lancer l'interface : commande `ghidraRun` dans le terminal.
2. *File ▸ Open Project* → `firmware/ghidra/AVR161.gpr`.
3. Double-cliquer sur le programme `AVR1610_USB(V002_20).fw` dans l'arbre.

Il contient déjà : les fonctions réseau (`build_reply`, `cmd_dispatch`, `source_selection_handler`,
`net_send`…), le hook get-status, les 9 `set_src_*` identifiées, les 11 candidates `set_src_UNKNOWN_*`,
les variables d'état (`g_volume`, `g_flags`/mute, `g_src_switch_flag`…) et les chaînes/tables clés.

Paramètres d'import utilisés (si tu veux ré-importer) : Raw Binary, Language `ARM:LE:32:Cortex`,
Base Address `0x08000000`. Repère : `0x08000000` = table de vecteurs (pile `0x20009188`, reset `0x0800d36c`).

## Re-lancer l'annotation (optionnel)

Ghidra 12.x a retiré Jython : les scripts sont désormais **Java** ou **PyGhidra**.
L'annotation est en `AnnotateAVR.java` (déjà appliquée). Pour la rejouer dans l'interface :
*Window ▸ Script Manager* → ajouter ce dossier → exécuter `AnnotateAVR.java`.
(`annotate_avr.py` est l'ancienne version Jython, conservée pour référence mais non exécutable sans l'extension Jython.)

## 3. Trouver la fonction Bluetooth (la tâche restante)

Le cluster `0x8019000`–`0x801a500` contient ~15 fonctions `set_src_*` auto-suffisantes
(prologue : garde sur `src_switch_flag` 0x2000e1ab → `strb #0x19` → `bl <routage>`).
**9 sont déjà nommées.** La BT est l'une des non nommées. Méthodes, par ordre d'efficacité :

**A. Via le menu Source Select (le plus sûr).**
   - Aller à la chaîne `"BLUETOOTH"` d'affichage : `0x080d98f0` (label `str_disp_BLUETOOTH`).
   - *References ▸ Show References to Address* → tomber sur la/les routine(s) d'affichage du menu.
   - Dans la fonction du menu qui gère la sélection, suivre le `case`/branche qui affiche BLUETOOTH :
     l'appel `bl set_src_??` adjacent (ou dans le même bloc d'action) est la fonction Bluetooth.
   - Candidats média probables (cluster où vivent iPod/vTuner/HomeNetwork) :
     `0x8019528, 0x80195d8, 0x8019690, 0x8019704, 0x80197a8, 0x8019824, 0x8019868, 0x8019980, 0x801947c, 0x80194c8`.

**B. Par l'enum de source.**
   - La table d'affichage `0x08053684` (label `tbl_source_display`) mappe enum→nom (…TV, BLUETOOTH, USB…).
   - Décompiler une `set_src_*` nommée (ex. `set_src_Disc`) pour voir **quelle variable** reçoit l'enum
     et **quelle valeur** (via sa routine de routage). En déduire la variable d'enum source.
   - La fonction BT est celle qui écrit la valeur d'enum correspondant au slot BLUETOOTH (`0x080536b0`).

**C. Par signature BT.**
   - La bascule BT active le module réseau pour l'A2DP : décompiler les candidates et repérer celle qui
     référence le sous-système réseau/Venice (différent des sources analogiques TV/AUX/etc.).

## 4. Pour les patchs (phase 2, après identification)

- **get-status** : hook en `0x0804f348` (branche heart-alive) ou nouvelle branche strcmp "get-status"
  en tête du dispatcheur `0x0804f328` → code cave (flash `0xFF`) lisant volume/mute/source et appelant
  `BUILD_REPLY` (`0x0804fe7c`) + `NET_SEND` (`0x08087e0c`). Détails : `../re/NOTES.md`.
- **source-selection Bluetooth** : une fois la fonction BT trouvée, ajouter une branche
  `strcmp(para,"Bluetooth")==0 → bl set_src_Bluetooth` dans le handler `0x0804f44a`,
  exactement comme les branches existantes.

Tout le contexte détaillé (offsets, variables, primitives) est dans `../re/NOTES.md`.
