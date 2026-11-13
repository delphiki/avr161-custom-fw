# Rétro-ingénierie firmware AVR 161/1610 — V002.20

Image : `../AVR1610_USB(V002_20).fw` (6 Mio), MCU ARM Cortex-M, **base flash `0x08000000`**,
pile initiale `0x20009188` (SRAM). Code en **Thumb-2**. Non chiffré.

Outil : `fwre.py` (capstone). Helpers : `xrefs(va)` (pointeurs literal vers va),
`trace(a,b)` (désassemblage annoté), `scan_litrefs`, `u32`, `rd`.

## Fonctions utilitaires identifiées (libc-like)
- `0x80953d0` : **strlen**
- `0x8095408` : **strcat** à (buf+len) — pattern `len=strlen(buf); strcat(buf+len, src)`
- `0x809534c` : **strcmp**
- `0x80953b8` : **memset**
- `0x804fdd4` : **int→décimal** (0..999) dans buffer RAM `0x2000dee4`, retourne le ptr (sert au Content-Length)

## Constructeur de réponse réseau — `0x804fe7c`  ★ (hook get-status)
Signature effective : `build_reply(name, zone, para)` (args r0/r1/r2, sauvés en sp+0x200/0x204/0x208).
Assemble dans un buffer de pile (0x200), puis emballe dans le **buffer HTTP sortant RAM `0x2000a0b4`** :
```
POST AVR HTTP/1.1\r\nHost:<IP>:10025\r\nUser-Agent:Harman Kardon AVR161/AVR1610\r\nContent-Length:<n>\r\n\r\n
<?xml ...><harman><avr><common><status><name>NAME</name><zone>ZONE</zone><para>PARA</para></status>...</harman>
```
- Tags toujours émis ; **contenu de zone/para ajouté seulement si la variable RAM `0x2000cb1c` == "status_name"**.
  → Le firmware a DÉJÀ un mode de réponse « statut » enrichi. Pour get-status : passer ctx="status_name"
    et zone/para = valeurs d'état, OU ajouter une commande qui appelle ce constructeur avec l'état.
- Strings du gabarit : préfixe `0x80d4478`, `</name><zone>` `0x80de914`, `</zone><para>` `0x80de924`,
  suffixe `0x80d5b38`. Pool du constructeur : `0x8050080`–`0x80500b0`.
- Variables RAM vues ici : `0x2000a0b4` (réponse sortante), `0x2000d7c8` (host/IP), `0x2000cb1c` (ctx "status_name").

## Table des noms de commandes/sources — ~`0x804ffa8`–`0x805000c`
Pointeurs vers : power-on, source-selection, iPod, Disc, Internet Radio, Media Server, Cable Sat, Game,
Audio, Radio, Server, vTuner, Pandora, Sirius Radio, Home Network, Source A-D, volume-up, volume-down, mute-on…
(+ en amont : heart-alive `0x804fe68`, Main Zone, power-off, power-toggle).
Entrées RAM intercalées (`0x2000e1ab`…) = noms de sources **renommables**.
⚠️ **Pas de Bluetooth** dans cette table (cf. conclusion : pas de sélection BT par commande réseau).

## À FINALISER en phase 1b
1. **Dispatcheur** : la table ci-dessus n'est référencée ni par literal PC-relatif ni par pointeur absolu
   trouvable → accès indirect (base calculée / table parente). À localiser (c'est le point d'insertion
   d'une nouvelle commande type `get-status`, et le nœud de la sélection BT).
2. **Variables d'état** (adresses RAM exactes) — ancrages trouvés, à épingler :
   - Volume : handler via logs `"UI COMMAND is volume up/down/mute"` (pool `0x8041b68`) ;
     afficheur OSD `"VOLUME    :     "` `0x80db13c` (ref `0x8058e30`).
   - Mute : afficheur `"MUTE   : ON"` `0x80db7cc` / `"MUTE   : OFF"` `0x80db7e0` (refs `0x805c324/8`).
   - Source : chaînes d'affichage de source (`"SRC: …"`) + table ci-dessus.
   (Attention : zones mixtes code/données, désassembler en s'alignant sur les prologues `push`.)

## Faisabilité (à ce stade)
- **get-status** : faisable — machinerie de sortie + primitives en main, mode "status_name" déjà présent.
- **set-volume (absolu)** : probable — handler volume localisé ; reste à épingler la variable + la routine d'application.
- **sélection Bluetooth directe** : incertain — pas d'entrée BT dans la table ; dépend d'une routine
  « basculer en BT » appelable, non confirmée.

---
# Phase 1b — RÉSULTATS

## Dispatcheur de commandes réseau — `0x804f328` ★★
Fonction `dispatch(char* cmd_name)` (r0 = nom reçu). **Chaîne de strcmp** (pas une table) :
```
0x804f328 push {r3-r7,lr}; mov r4,r0        ; r4 = nom de commande
0x804f332 ldr r1,="heart-alive"; strcmp     ; compare
0x804f33e bne -> commande suivante
0x804f340 r2=0(para) r1=0(zone) r0="heart-alive"
0x804f348 bl BUILD_REPLY (0x804fe7c)        ; <- POINT D'INJECTION get-status
0x804f34c r0=0x2000a0b4; bl NET_SEND (0x8087e0c)
0x804f354 b 0x804fdca (fin)
0x804f358 ... "Main Zone" ... (suite de la chaîne)
```
2e appelant de BUILD_REPLY : `0x8071906` (envoi d'un `<status>` "bye-bye", ex. à la déconnexion
→ le firmware PUSH des messages de statut de lui-même).

## Fonctions réseau
- `0x804fe7c` BUILD_REPLY(name,zone,para)   — cf. phase 1
- `0x8087e0c` NET_SEND(buf)                  — envoie le buffer HTTP sortant

## Variables d'état (RAM) — ÉPINGLÉES
- **Volume** : octet `0x2000e213`  (lu par l'OSD "VOLUME :", écrit par ~10 sites → cible set-volume)
- **Mute**   : bit 1 de l'octet `0x2000de40`  (ubfx #1,#1 ; 1=ON)
- **Source** : enum indexant la table de noms d'affichage `0x8053684`+ :
  CABLE/SAT, DISC, MHL:Roku, MHL/SERVER, AUX, GAME, SET-TOP BOX, AUDIO, TV, BLUETOOTH,
  USB, iPod, HOME NETWORK, vTuner, (Home Network DMR). Adresse exacte de l'octet source : à épingler
  (proche du struct 0x2000e21x) via le handler source-selection.

## Design patch get-status (faisable)
Détour depuis la branche heart-alive (0x804f340) OU nouvelle branche strcmp "get-status" en tête :
→ vers un code cave (flash en 0xFF, abondant) qui :
   1. int2dec(*(u8*)0x2000e213) -> chaîne volume
   2. lit mute = (*(u8*)0x2000de40>>1)&1 ; lit source (enum)
   3. BUILD_REPLY(name, zone, para) avec ces valeurs (ctx="status_name" pour inclure zone/para)
   4. NET_SEND(0x2000a0b4)
Primitives dispo : int2dec 0x804fdd4, strlen/strcat/strcmp/memset (cf. phase 1).

## set-volume (absolu) : APPROCHE RÉVISÉE — réutiliser les pas prouvés (pas de routine raw à trouver)
- **Variable de volume LIVE = 0x2000e1b8** (octet, plage 0..0xB4=180, pas de +2/+4 ≈ 0,5 dB ;
  plage -80…+10 dB du HK). C'est ELLE que lisent/écrivent les pas et qui est appliquée au matériel.
  ⚠️ DISTINCTE de g_volume=0x2000e213 (miroir d'affichage OSD "VOLUME:").
- **vol_up  = FUN_0801b568 (0x0801b568)** / **vol_down = FUN_0801b8f0 (0x0801b8f0)** : pas auto-suffisants
  (appelés sans arg), incrémentent/décrémentent 0x2000e1b8 (+/-2 ou 4, clamp 0..180) ET appliquent HW+OSD.
  Gardes en tête (mute/menu/transition via flags 0x2000ddd4, 0x2000ddb0…) : si non remplies, le pas no-op.
- Chaîne UI : cmd volume -> FUN_08041720(code) -> FUN_0802a340(5=up/6=down/0x21=mute) -> FUN_0801b568/8f0.
- **set-volume absolu = boucle dans un cave** : lire 0x2000e1b8 ; tant que != cible, appeler vol_up/vol_down ;
  BORNER (≤128 iter) + stopper si le pas ne bouge plus (garde bloquante). Réutilise tout le chemin prouvé.

## Bluetooth direct : FONCTION EXACTE = set_src_Bluetooth 0x0801af34 (cf. plus haut, confirmée).

## Structure de la commande réseau (param_1 de cmd_dispatch 0x804f328) ★ (résolu en review)
- **nom @ +0x00**, **zone @ +0x20**, **para @ +0x40** (un seul buffer, pointé par param_1=r0).
  Les branches source comparent `param_1+0x40` (para) aux noms de source. => para DISPO au hook cmd_dispatch.
- Flag de switch **g_src_switch_flag = 0x2000e1ab** (= DAT_0804ffb4, confirmé). DAT_0804ffb8=0x2000ddd4 (flags power/zone),
  DAT_0804ffbc=0x2000e1ae (g_source_enum).
- **set_src_Bluetooth (0x801af34) NE pose PAS 0x2000e1ab lui-même** (il pose g_source_enum=0x11 + bt_module_activate…).
  Les branches réseau (HomeNetwork, vTuner) font `*0x2000e1ab=0x19` AVANT l'appel ; les branches analogiques (iPod…) non.
  => Pour BT : RÉPLIQUER la branche HomeNetwork :
     `*0x2000e1ab=0x19 ; set_src_Bluetooth() ; if ((*0x2000ddd4 & 3)>>1 != 0) FUN_08018944();`
- Pas/guards volume : les pas vol_up/down s'appliquent bien depuis le dispatch réseau — PROUVÉ empiriquement
  (ampli.py vol+ fonctionne sur l'ampli réel). Les gardes (menu/mute/transition) passent en fonctionnement normal.

## CODE CAVE (corrigé après dissection updater)
- ⚠️ l'ancien cave 0x0800d514 est RÉSIDENT (idx 0-3) -> NON réécrit par l'USB -> INUTILISABLE pour un patch USB.
- **CAVE VALIDE = 0x080E0000–0x080FFFFF (128 Ko de 0xFF, idx 11, zone réécrite).** Offset fichier = 0xE0000.

## Push de statut : INEXISTANT (investigué)
- NET_SEND (0x8087e0c) n'a que 2 sites : 0x804f350 (réponse heart-alive, vide) et 0x807190e (bye-bye, vide).
- "status_name" (0x80defc0) et "surround-mode" (0x80de904) : référencés UNIQUEMENT par le constructeur →
  personne n'écrit "status_name" dans le ctx 0x2000cb1c → le chemin « valeurs dans zone/para » est du CODE MORT.
- => Le firmware NE pousse PAS source/volume/mute. Pas d'état gratuit pour HA.
- Corollaire design : enrichir la RÉPONSE heart-alive (0x804f348) est le meilleur hook — le client poll déjà
  heart-alive, donc HA récupère l'état réel via le même poll, sans changer le protocole.

## Bluetooth : VIABILITÉ RÉÉVALUÉE -> probablement VIABLE
- Le changement de source se fait par ~15 fonctions **auto-suffisantes, sans paramètre** dans le cluster
  0x8019000-0x801a000 (prologue type : push {r7,lr}; garde d'état sur flag 0x2000e1ab; strb #0x19; bl <routage>).
  AUCUNE dépendance à l'état du menu.
- Le handler réseau source-selection (0x804f44a) appelle ces fonctions par `bl` pour chaque source connue :
  Cable Sat 0x80190d0, Disc 0x80191bc, Media Server/Server 0x8019238, Game 0x8019308, Audio 0x80193d8,
  Radio 0x801942c, iPod 0x801963c, Internet Radio/vTuner 0x801a9c6, Home Network 0x801abd2 ... (pas de BT).
- L'ampli A une source Bluetooth atteignable par le MENU => une fonction "switch to Bluetooth" existe
  dans ce même cluster, appelable de la même façon.
- => Un patch peut ajouter une branche réseau `source-selection`="Bluetooth" qui `bl` cette fonction,
  structurellement identique aux ~13 branches existantes. FAISABLE.
- RESTE À FAIRE (borné) : épingler l'adresse exacte de la fonction BT (via le dispatch du menu source,
  qui référence la table d'affichage 0x8053684 par base calculée — non encore localisé), et confirmer
  qu'elle est aussi auto-suffisante que les autres.

## Bluetooth : FONCTION EXACTE ÉPINGLÉE (via PyGhidra + décompilateur)  ★★★
- **set_src_Bluetooth = 0x0801af34** — routine de bascule source Bluetooth.
  Décompilé : `if (g_source_enum != 0x11) { ... g_source_enum = 0x11; bt_module_activate(); FUN_080294d6(enum); FUN_08018696(); }`
  Structure identique à set_src_HomeNetwork → auto-suffisante, appelable depuis un patch.
- **bt_module_activate = 0x08049af8** — activation du module BT (équiv. FUN_080495c8 pour Home Network).
- **g_source_enum = 0x2000e1ae** (octet) — source courante. Valeurs : iPod=0x0B, HomeNetwork=0x0C,
  vTuner=0x0D, USB=0x10, **Bluetooth=0x11**. L'OSD rend 0x11 -> "BLUETOOTH" (FUN_08052f80).
- **src_switch_by_index = 0x0802375c** — dispatcheur qui route par index de source pré-sélectionné
  (*DAT_0801a424) ; index 0x0D -> set_src_Bluetooth. (NB : l'index du dispatcheur (0x0D) diffère de
  l'enum d'affichage (0x11).)
- Annotations sauvegardées dans le projet Ghidra (firmware/ghidra/AVR161).

### Patch Bluetooth (phase 2) — maintenant concevable
Ajouter dans source_selection_handler (0x0804f44a) une branche :
  `strcmp(para,"Bluetooth")==0  ->  (poser flag switch 0x2000e1ab=0x19) ; bl set_src_Bluetooth (0x0801af34)`
en calquant exactement une branche média existante (ex. set_src_iPod). => Commande réseau Bluetooth directe.

## VERDICT FINAL FAISABILITÉ
- get-status        : FAISABLE (hook 0x804f348, build_reply, variables g_volume/g_flags/g_source_enum pinées)
- set-volume absolu : FAISABLE (g_volume=0x2000e213 + routine d'application)
- Bluetooth direct  : FAISABLE ET FONCTION EXACTE CONNUE (set_src_Bluetooth=0x0801af34)

---
# Format du paquet .fw & validation (question : flash custom par clé USB sans SWD ?)

## Structure du .fw (6 Mio, offsets fixes, reste en 0xFF)
- **0x000000** : commence DIRECTEMENT par la table de vecteurs STM32 (SP=0x20009188, reset=0x0800d36c).
  Donc PAS d'en-tête préfixe : l'offset 0 est écrit tel quel en 0x08000000.
- Zones de contenu (le reste = padding 0xFF jusqu'à 0x600000) :
  - 0x000000–0x0DFFFF : image MCU STM32 (celle qu'on patche)
  - 0x100000–0x33FFFF : ~2,3 Mio (DSP CS49834 + autres composants ; en-tête DSP à 0x100000)
  - 0x500000–0x511FFF : petit composant (en-tête à 0x500000 = table d'offsets indexée)
- **Pied de fichier : 0xFF jusqu'au bout → AUCUN CRC/signature en footer.**

## Recherche d'intégrité/crypto (binaire entier)
- CRC32 (poly 0xEDB88320 / 0x04C11DB7) : **0 occurrence** (pas de CRC32 table-driven).
- Crypto ASYMÉTRIQUE : **AUCUNE trace** — pas de constante RSA/ECDSA, pas de clé publique/PEM,
  pas de chaîne lib (mbedtls/wolfssl/openssl), pas de SHA-256 (0x6a09e667 absent).
- Blocs "IV MD5" (67452301 efcdab89 98badcfe 10325476) : 4 occurrences, mais
  - 3 dans la zone composants 0x100000+ (données DSP ; suivies de descripteurs dest/len)
  - 1 à 0x080b7420 = **DONNÉE NON RÉFÉRENCÉE par aucun code** (pas un MD5 actif sur l'image).
  → aucun hash n'est calculé sur le firmware pour le vérifier.

## Chaînes & portes
- Cluster update (affiché OSD) : "MCU/DSP/VENICE/OSD UPDATE", "USB Software Upgrade",
  "SYSTEM UPDATE CONTINUE", "UPGRADE SUCCESS", "MCU IAP VERSION", "NO upgrade file".
- "INCORRECT VERSION" (0x80dc834) : UNIQUEMENT un item d'un **logger de debug à champ de bits**
  (FUN_080a281c imprime 1 ligne parmi ~21 via FUN_080695d4). Ce n'est PAS un verrou de flash.
- Doc officielle : update grand public 2015 (dézipper sur clé, insérer, confirmer, ~10 min,
  auto power-cycle, "UPGRADE SUCCESS"). Gate affiché = **modèle ("designed for AVR 1610") + version**.

## Graveur de flash (IAP)
- Clés de déverrouillage STM32F2 FLASH_KEYR (0x45670123 @0x800af44, 0xCDEF89AB @0x800af48) +
  FLASH_CR (0x40023c10) → graveur IAP standard autour de 0x0800af00 (et refs 0x80069d4/0x800808c/0x80a4d64).
  Programmation flash classique, rien d'exotique. (Régions IAP non auto-analysées par Ghidra —
  reste à décompiler si on poursuit la piste USB, pour les champs longueur/checksum éventuels.)

## CONCLUSION (question "signé ou juste checksummé ?")
- **PAS de signature cryptographique** (aucune vérif asymétrique possible sans clé privée → absente).
- Au pire un **checksum/longueur non-secret** (recalculable après patch).
- ⇒ **Flash custom par clé USB VIABLE EN PRINCIPE**, sans SWD ni ouverture.
- RÉSERVES : (1) brick = DÉFINITIF sans filet SWD ; (2) reste à RE le format exact des composants
  + tout champ longueur/checksum pour que l'image reconstruite passe l'updater (phase build).

---
# DISSECTION UPDATER IAP (machine à états de flash MCU) ★★★

## Primitives IAP flash (driver STM32F2 nu, autour de 0x0800ad80-0x0800af60)
- 0x800ada4 unlock (KEYR 0x40023c04 <- 0x45670123 puis 0xCDEF89AB)
- 0x800adba lock (CR bit31)
- 0x800adcc erase_sector(r0=SNB bits)      ; CR: SER|2, SNB, STRT|0x10000, wait_ready
- 0x800ae4a program_word(r0=addr,r1=val)   ; CR PSIZE=2 (0x200), PG|1, str, wait
- 0x800aeaa program_byte(r0=addr,r1=val)   ; CR PSIZE=0, PG|1, strb, wait
- 0x800af06 get_status (SR 0x40023c0c: BSY b15 ; err -> 5/6 ; ok=8)
- 0x800af54 wait_ready(timeout) -> 9 si timeout
=> AUCUN calcul de somme ici. Driver flash standard.

## Orchestrateurs (2) appelant l'IAP
- CLUSTER A 0x8005d56.. (step 0x8005e6c) : **self-flash de la flash MCU interne** (dest=+0x08000000).
- CLUSTER B 0x8007c.. / 0x80080.. : 2e moteur (autres composants). State var commune: seulement 2 refs.
- State var = *0x20007180 (0..7). Index composant = *0x2000717e (part de 4, boucle jusqu'à 0xC).

## Machine à états CLUSTER A (self-flash MCU) — ce qu'elle fait VRAIMENT
- S0 init : dest(*70c4)=tbl_start[idx]+0x08000000 ; len(*70b4)=tbl_len[idx] ; f_lseek(handle, tbl_start[idx]).
- S1 erase : erase_sector(tbl_sector[idx]) ; ok(SR==8) -> S2.
- S2 read  : f_read(buf=*70cc, 1, 4, handle) -> n (*7172) ; src(*70c8)=&buf ; S3.
- S3 write : si n==4 -> program_word(dest, *buf) PUIS **relit flash & compare** (cmp/beq) ;
             si n<4  -> boucle program_byte + relecture/compare pour chaque octet ;
             dest+=n ; compteur(*70bc)+=n ; -> S4.
- S4 next  : si compteur==len -> composant fini (idx++ ; si idx==0xC -> S6 fin) ; sinon lire bloc suivant.
- La "vérif" = **RELECTURE POST-ÉCRITURE (write-verify)** : confirme que la cellule a pris la valeur.
  CE N'EST PAS un contrôle de contenu (pas de CRC, pas de hash, pas de somme accumulée).
=> **LE CONTENU DU FICHIER EST ÉCRIT VERBATIM** à des adresses fixes.

## TABLES DE LAYOUT (flash MCU = 1 Mo -> STM32F205Z**G**, pas ZF 768K)
tbl_start=0x800d0a8, tbl_len=0x800d0dc, tbl_sector=0x800d324 (idx 0..11) :
  idx 0  0x00000 len 0x4000  | idx 1  0x04000 len 0x4000  | idx 2 0x08000 len 0x4000 | idx 3 0x0c000 len 0x4000
  idx 4  0x10000 len 0x10000 | idx 5  0x20000 len 0x20000 | idx 6 0x40000 len 0x20000| idx 7 0x60000 len 0x20000
  idx 8  0x80000 len 0x20000 | idx 9  0xa0000 len 0x20000 | idx10 0xc0000 len 0x20000| idx11 0xe0000 len 0x20000
- **idx 0-3 (0x00000-0x0FFFF, 64 Ko) = bootloader/updater résident + vecteurs : JAMAIS réécrit** (S0 part à idx=4).
- **idx 4-11 (0x10000-0xFFFFF) = application : réécrite depuis le fichier.**
- f_lseek par composant => **offset fichier == offset flash == (adresse - 0x08000000). Image 1:1.**

## Gates avant flash
- Magic/identité "!!ANAM SOFT!!" (0x800d2d8, data firmware ; "ANAM" = ODM carte). Ouverture via FUN 0x800aa9e.
- "INCORRECT VERSION" n'est PAS un verrou (logger debug, cf. plus haut). Modèle "AVR1610" @0x80d4760, "V002.20" @0x80dbbb4.

## RECETTE DE BUILD (image custom acceptée)
1. Patcher les octets voulus dans la zone **0x10000-0xFFFFF** du .fw (offset fichier = adresse-0x08000000).
2. Ne PAS toucher 0x00000-0x0FFFF (bootloader) ni les composants >0x100000 (laisser stock).
3. AUCUN checksum à recalculer, AUCUNE signature à forger. Zipper, clé USB, menu Software Update.

## BRICK / RÉCUPÉRATION (impact sur "sans filet")
- Le bootloader+updater (64 Ko bas) N'EST PAS réécrit -> survit à un flash d'app raté.
- Un patch PRUDENT (petite modif du dispatcheur réseau) laisse le boot+menu OSD fonctionnels
  -> on peut **re-flasher le .fw stock par USB sans SWD** = récupération.
- Un patch qui casse le boot précoce / le menu -> plus d'accès au menu update -> **SWD requis**.

## CHEMIN D'AUTO-UPDATE AU BOOT — CONFIRMÉ (récupération sans SWD) ★★★
Reset 0x800d36c -> startup 0x800d188 -> **bl 0x8005500 = main() RÉSIDENT** (zone <0x10000, jamais réécrite).
- main() 0x8005500 : init + splash timer, puis boucle `while(G&1) FUN_080057b4()`.
- FUN_080057b4 : après splash (timer*5e4c atteint 2000 -> G|=2), poll USB ; appelle **FUN_08005be4**.
- FUN_08005be4 (driver update, AUTONOME) : FUN_0800ad6a()=USB prêt ? si oui, débounce ~1000 ticks
  -> update-state(*069c8)=1 -> **FUN_08005d0a** (dispatch : mount -> FUN_08005d5c -> FUN_08005e64 flash).
- Gate FUN_08005d5c : ouvre "!!ANAM SOFT!!" (handle) ; flashe SSI **handle!=0 && *0x2000717d==1**.
- **Flag 0x2000717d écrit =1 à 0x8003db4** (strb #1) par la couche FAT RÉSIDENTE (0x8003xxx) quand le
  FICHIER D'UPDATE EST DÉTECTÉ sur la clé. Référencé UNIQUEMENT par du résident (0x80043b0, 0x8006934)
  -> **l'app ne participe PAS à la décision de flasher.**
=> La détection + le gate + le flash sont 100% résidents et tournent au boot sur simple présence
   du fichier USB. **Un flash d'app raté est récupérable par clé USB (stock .fw) sans SWD.**
- RÉSERVE : la nécessité/placement d'une confirmation "SYSTEM UPDATE CONTINUE" (la chaîne OSD
  "Press OK to update" est référencée par l'APP 0x8075xxx) n'est pas 100% tranchée. À VALIDER
  empiriquement SANS RISQUE : clé stock + power-cycle sur ampli sain -> si ré-update auto sans menu,
  le filet USB-sans-SWD est prouvé.

## APPROFONDISSEMENT (review builder #1) — le flash résident ne dépend PAS de l'app ★★★
- FUN_08005d5c (résident, armement flash) : `handle=open("!!ANAM SOFT!!"); if (handle && *0x2000717d) {update-state=3; unlock_flash}`.
  => condition = fichier ouvert + flag détection. AUCUN flag de confirmation applicatif.
- `0x2000717d` écrit =1 par la couche FAT RÉSIDENTE (0x8003db4) à la détection du fichier ; référencé
  UNIQUEMENT par du résident (0x80043b0, 0x8006934). L'APP NE L'ÉCRIT JAMAIS.
- FUN_08075000 (app "Press OK to update", 0x8075xxx) = machine à états d'AFFICHAGE OSD (états DAT_080753xx,
  events touches). N'écrit ni 0x2000717d ni l'état résident -> couche de présentation séparée, PAS un verrou.
=> CONCLUSION (confiance haute) : le moteur de flash résident s'arme sur simple détection du fichier,
   indépendamment de l'app. Le "Press OK" est de l'UX, pas une condition dure.
- RÉSIDU non prouvable statiquement : une app cassée pourrait-elle crasher la boucle résidente (FUN_08005500)
  AVANT que le poll USB ne flashe ? Dépend du timing boot (poll update dans la même boucle que l'app).
  Pour un patch réseau (loin du boot/résident), négligeable : boot+menu restent intacts -> récup USB triviale.
  Seul un patch cassant le BOOT PRÉCOCE serait non récupérable par USB -> SWD. Ce patch ne touche pas ça.
- PREUVE EMPIRIQUE (test A) : flasher un défaut OSD cosmétique observable (zone app) ; vérifier boot+défaut ;
  puis clé STOCK + power-cycle -> le défaut disparaît = récup auto prouvée. Couvre le profil de risque du patch.

## set-volume firmware : CAUSE RÉELLE des échecs v1.0.0 → v1.0.2d (2026-11-13) ★
**Le handler set-volume n'a JAMAIS été exécuté sur l'ampli** dans aucun build incluant le Bluetooth.
- Bug de layout du cave : "set-volume\0" (11 o à +0x18, finit à +0x22) était écrasé par
  "source-selection" écrit ensuite à +0x20 -> la chaîne en flash valait "set-volusource-selection",
  le strcmp du cave ne matchait jamais, la commande tombait dans le dispatch stock (inconnue = no-op).
- Prouvé par émulation Unicorn du cave contre les images flashées + dump xxd à 0xE0010.
- Les tests ne le voyaient pas : ils ne vérifiaient que le désassemblage, et le test set-volume
  construisait sans la feature bluetooth.
- CONSÉQUENCE : les diagnostics "garde no-op", "rate-limit" et "crash dû au pré-jump" étaient
  tous FAUX (aucun n'observait le handler). Le test v1.0.2d "sans pré-jump = pas de crash"
  ne prouvait rien : ni v1.0.1 ni v1.0.2d n'exécutaient ce code.
- Le crash observé une fois sur v1.0.1 (port 10025 mort après status/set-volume, récupéré par
  coupure secteur) reste INEXPLIQUÉ : la même séquence réseau rejouée >10 fois sur v1.0.2d
  (code exécuté identique) n'a jamais replanté. n=1, cause inconnue.
- Correctif (v1.0.2) : STR_SOURCESEL -> +0x24, STR_BLUETOOTH -> +0x35 ; garde anti-chevauchement
  `put()` dans build_patch1 ; tests comportementaux par émulation (tests/emu.py).

## Dispatch réseau stock : portes et cooldown (décompilation cmd_dispatch 0x804f328)
- heart-alive traité en premier (réponse), puis portes : zone == "Main Zone" (strncmp 9) ;
  FUN_0802f348() != 0 ; **\*0x2000e2a6 == 0** ; FUN_08071816() == 0 (sinon seules les cmd power passent).
- Après toute commande traitée : **\*0x2000e2a6 = 0x32 (cooldown)** + FUN_0802f194(). Tant qu'il n'est
  pas retombé à 0, les commandes suivantes sont IGNORÉES. Mesuré : 2 volume-up espacés de 0,1 s
  = 1 seul pas ; espacés de 0,6 s = 2 pas. => une boucle de pas ré-entrants ne ferait qu'UN pas.
- vol_down 0x801b8f0 / vol_up 0x801b568 : gardes (0x2000ddd4 bit1, 0x2000dd5c==0, 0x2000e1ab==0,
  0x2000db40 bit13, 0x2000e1d9==0, FUN_0802aa5c()!=1, 0x2000db94 bit6) ; pas = 2 si 0x2000e1cd<0xd
  (ou master>0x8b en montée) sinon 4 ; puis FUN_08018464 (application + OSD) ; 0x2000e1cd=0x14.

## set-volume v1.0.2 : design "un seul coup" (PAS ENCORE VALIDÉ SUR MATÉRIEL)
cur=master ; si |cur-cible|<=1 rien ; master=cible±3 (clamp) ; UN volume-down/up synthétisé via
cmd_dispatch ; si master est resté à la valeur pré-jumpée (pas refusé : gardes/cooldown) -> on
restaure cur. Atterrit à ±1 que le pas vaille 2 ou 4. Premier build où ce code s'exécutera vraiment.

## v1.0.3 : service réseau mort au démarrage — NON ÉLUCIDÉ (2026-11-13)
Faits : v1.0.3 (set-volume « cible exacte », 0xb4 octets) flashé une fois -> port 10025 mort sur 3
démarrages (refusé d'emblée ; puis 1 connexion acceptée et plus rien, 2 fois), sans AUCUNE commande
set-volume envoyée. v1.0.2 reflashé -> sain, y compris sous la même sonde agressive juste après
démarrage à froid (réfute « connexion trop tôt »). Source MHL (= enum 2) hors de cause.
Écarté statiquement : écriture ratée (l'updater relit chaque mot, 3 essais puis boucle infinie :
un flash terminé = flash identique au fichier) ; référence stock vers la zone ; secteur 11 utilisé
comme stockage (seul pilote flash = résident) ; motif d'octets commun v1.0.1/v1.0.3.
Seule différence structurelle : v1.0.3 est le 1er build à occuper +0x320..+0x333 du cave.
Hypothèse NON PROUVÉE : quelque chose lit cette zone. Contournement : v1.0.4 = même algorithme
compacté à 0x96 octets (aucun octet modifié hors empreinte v1.0.2), test de garde ajouté.
Si v1.0.4 échoue aussi : c'est le contenu et non l'empreinte -> revenir à v1.0.2.

## Sleep -> extinction complète, alimentation, push (2026-11-13)

### Mesure matériel (surveillance passive d'une nuit)
- `power-off` à 02:29:32 -> « Device sleep » ; ping + port 10025 + heart-alive OK jusqu'à 03:14.
- 03:29:43 (t+60 min) : ping perdu, port en timeout, plus d'ARP. Plus rien jusqu'à 11:30.
- Des `heart-alive` toutes les 15 min n'empêchent pas l'extinction. Wake-on-LAN (paquets
  magiques UDP 7/9/40000 en diffusion) sans effet. Éteint : voyant allumé, afficheur vide,
  la télécommande rallume.

### Temporisation sleep -> éteint
- Compteur `0x2000dd7c` (u32), armé à `0xe10` (3600) à 5 endroits (`mov.w r1,#0xe10`) :
  0x08018974 (FUN_08018944, power-toggle), 0x080189f0 (FUN_080189b4, power-off),
  0x08012e48, 0x08031d2c, 0x08032cb2 ; remis à 0 dans FUN_08018a3c (power-on).
- Décompte : bloc « tick 1 s » de FUN_08010784 (boucle principale, appelée par FUN_08010184
  <- main FUN_08065676), 0x08010af6..0x08010b3f, gardé par le bit 0 de 0x2000ddd4.
  À zéro : bit 7 de `0x2000dddc` levé (= éteint complètement ; c'est lui qui retire
  « Device sleep » de l'afficheur, cf. FUN_08052258), bit 1 de 0x2000dde0 baissé,
  0x2000e1dd = 100.
- FUN_08012bc8 (extinction auto) peut lever le même bit 7 directement si le bit 2 de
  0x2000ddf4 est posé (réglage non identifié).
- Patch keepsleep (v1.0.5) : `beq` -> `b` à 0x08010afe ; le compteur ne s'écoule plus.
  NON VALIDÉ sur matériel à cette date.

### Alimentation
- Bit 1 de `0x2000ddd4` = allumé (0 en sleep). Exposé en 5e champ de get-status (v1.0.5).

### Table des sources (routine d'affichage FUN_08052f80, variable 0x2000e1ae)
0 CABLE/SAT, 1 DISC, 2 MHL (Roku/Server), 3 AUX, 4 GAME, 5 SET-TOP BOX, 6 AUDIO, 7 TV,
8-9 (FUN_08059a10, radio ?), 10 USB, 11 iPod, 12 HOME NETWORK, 13 vTuner, 16 Home Network
DMR, 17 BLUETOOTH. Vérifié sur matériel : 2 et 17 seulement. (ampli.py dit 0x10 = USB : à
trancher.)

### Réseau : module externe, pas le MAC du STM32
- Aucune référence aux registres ETH du STM32 (0x40028000…) dans le firmware.
- `net_send(buf)` (0x08087e0c) -> FUN_08093f3e(0x08090400, len, buf, …) -> FUN_08073984 :
  construit une trame série vers le module réseau (n° de séquence 2 o, type, 1, identifiant
  4 o `0x08090400`, longueur, données, octet de fin 0xEF ou somme), l'émet (FUN_0802fe46)
  puis attend l'accusé (FUN_080730d4). Le routage vers le(s) client(s) TCP est fait par le
  module : inconnu statiquement.
- Réception : FUN_080864b8 (rappel enregistré par pointeur en 0x08087d90 / 0x08087ec4)
  recopie la requête puis appelle FUN_0804ef94 -> cmd_dispatch.
- Le firmware stock pousse déjà un message non sollicité : `net_bye_bye_push` (0x080718d8,
  appelée par src_switch_by_index) fait build_reply("bye-bye",0,0) + net_send.

### Carte mémoire vive (table d'init IAR 0x080d6c90)
- .data 0x20000000..0x20000f82 ; .bss 0x20000f84..0x2000e2dc ; pile jusqu'à 0x2000f2e0
  (SP initial). Aucune référence réelle au-dessus : 0x2000f2e0..0x2001ffff libre (non
  initialisé au démarrage).

### Push (build de test v1.1.0-test, NON flashé)
- Le bloc du décompte, mort avec keepsleep, est remplacé à 0x08010af6 par
  `bl push_tick ; b 0x08010b40`. push_tick (cave +0x200) compare (vol, mute|pwr<<1, src) à
  l'instantané mémorisé à `0x2001ff00` (+3 = 0xA5 si valide, +4 = compteur « client
  vivant » en secondes) et appelle emit_status si ça a changé et que le compteur est > 0.
- Chaque commande reçue (entrée du dispatch du cave) réarme le compteur à 90 s.
- Occupe pour la première fois le cave entre +0x1f0 et +0x279 (cf. mystère v1.0.3).
- À établir sur matériel : à quel client part un message non sollicité quand plusieurs sont
  connectés ; comportement si le client s'est déconnecté pendant les 90 s.

### Module réseau alimenté quand l'ampli est éteint ? (2026-11-13, statique seulement)
- Manuel de service : module réseau = FS1230A « Chorus 3 / Milan » + PHY KSZ8851SNL, sur son
  propre DC/DC 3,3 V dont la broche EN est le signal `NET_PWR_SW` = broche 78 du MCU =
  **PD9**. (CORRIGÉ le 2026-11-13 après lecture du schéma en image : son entrée est le rail
  de veille `ST+5V`, pas `+7VD` ; voir « Séquence d'alimentation » plus bas.) `BCO_RST` = broche 77 = PD8 ; liaison
  SPI2 (PB12..15), `BCO_REQ` = PD11. Consommation annoncée : < 0,5 W en veille.
- FUN_08040a84(port, masque) = mise à 1 (BSRR), FUN_08040a88 = mise à 0.
- Séquence d'extinction FUN_0801396c (compteur 0x2000dd5c), deux chemins selon le bit 7 de
  0x2000dddc :
  - étape 0xc6 : éteint -> PD9 = 0 et PD8 = 0 ; sleep -> PD9 = 1 ;
  - étape 0xaf : éteint -> une cinquantaine de sorties mises à 0 puis FUN_08011588(1)
    (reconfigure des broches) ; sleep -> liste plus courte. Sorties coupées seulement en
    « éteint » : PA8, PB1, PB9, PC7, PC8, PC9, PD9, PD12, PE1, PE5, PF0..PF3, PF5, PF11, PG3, PG4.
- (Dépassé : le convertisseur du module est sur `ST+5V`, cf. plus bas.) Non établi : ce que
  le MCU fait une fois éteint (boucle normale ou mode basse
  consommation, d'où dépend la réception des commandes du module).
- Idée en attente (demande du propriétaire) : temporisation sleep -> éteint réglable (24 h)
  au lieu de « jamais » ; le 0xe10 est armé à 5 endroits.

### Craquements audio avec la Switch (HDMI) — piste, statique seulement (2026-11-13)
- Symptôme (propriétaire) : craquements seulement avec la Switch (dock), aussi en stéréo,
  notamment à la reprise du son après un silence ; rien en direct sur la télé ; autres
  sources HDMI saines ; indépendant du port HDMI.
- Le pilote audio du récepteur HDMI SiI9575 est dans le MCU (chaînes « SiiDrvRxAudio… »).
  FUN_0809d8f8 (appelée par FUN_080a4b26) = traitement des interruptions audio ; état en
  `*(*0x0809dccc)` : 1 = audio coupé, 2 = audio établi, 3 = attente (temporisation 600).
  - Interruption « exception audio » (bit 6 de l'octet 1 lu en 0x17a2) : état -> 1, appel de
    FUN_0803f91e (prévient l'application : compteur 0x163, FUN_08017a92(1)).
  - Interruption « audio prêt » (bit 2 de l'octet 0) : FUN_0809ef96(0) (registre 0xf51 bit 0
    à 0 = démute), trace « === UNMUTE === », état -> 2, **sans délai**.
- Hypothèse à vérifier sur matériel : la Switch perturbe son flux audio pendant les silences,
  le SiI coupe puis rétablit, et le rétablissement immédiat laisse passer un transitoire.
  Diagnostic envisagé : compter les passages « coupé » / « démute » et les exposer par le
  réseau, pour voir si chaque craquement correspond à un cycle.

### Couleurs du menu à l'écran (OSD) — patch osdgreen (2026-11-13, NON flashé)
- OSD = moteur du SiI9575, piloté par le MCU. Couleurs sur 6 bits RRGGBB (0x03 bleu, 0x0c vert,
  0x3f blanc). Registres par fenêtre w (0..3) : 0xe37+16w bordure, 0xe38 séparateur, 0xe39/0xe3a
  ligne sélectionnée (texte/fond), 0xe3b/0xe3c texte/fond, 0xe3d/0xe3e ligne désactivée,
  0xe70+w transparence.
- FUN_08096598 crée une fenêtre depuis une ressource (type 3) : octets +0x15..+0x1c de la
  ressource = texte, fond, texte sél., fond sél., texte désact., fond désact., bordure,
  séparateur -> structure de fenêtre sl+0x32..+0x39. FUN_08095774(fenêtre, élément, couleur)
  = changement à chaud, appelée seulement par la boîte de message FUN_08097458 (bleu 3).
- Ressources : 4 locales dans le MCU (0x080d2558, identifiants 0x8000..0x8003, 0x1b6 o chacune)
  et 40 dans le composant OSD du fichier (0x500000, table d'offsets à +0x14), chargées dans la
  flash du SiI. Bleus utilisés : 0x07 (fond de la ligne sélectionnée, presque toutes les
  fenêtres), 0x0b (titres : texte « désactivé » des fenêtres 0x04 et 0x26), 0x03 (fenêtre
  locale 0x8003), 0x1b / 0x16 (bordures des fenêtres 0x0b, 0x10..0x13).
- Patch (feature `osdgreen`) : le `bl memcpy` de 0x080967dc passe par osd_recolor (cave
  +0x400, 56 o) qui remplace 0x07->0x08, 0x0b->0x0c, 0x03->0x08, 0x1b->0x1d, 0x16->0x19 ;
  les deux `movs r2,#3` de la boîte de message (0x0809761e, 0x08097644) deviennent #8.
  Le composant OSD (>= 0x100000) n'est pas modifié. Image de test : v1.0.6-test.

### Modes surround — lecture et sélection directe (2026-11-13, NON flashé)
- Table des modes : `0x080d2fe0`, 48 entrées de 12 o : catégorie (0 auto/décodage natif,
  1 virtuel, 2 stéréo, 3 NSP, 4 film, 5 musique, 6 jeu, 8 autres), pointeur vers la fonction
  « ce mode est-il possible maintenant ? » (+4), drapeaux (+8).
- Codes -> nom affiché (FUN_0805b02c) : 0 Virtual Surround, 1 Virtual Surr.2, 2..5 2CH Stereo,
  6 Dolby Digital, 7 DTS, 8 DTS 96/24, 9 5CH Stereo, 10 Dolby Digital EX, 11 DTS-ES Mtrx,
  12 DTS-ES Dscrt, 13/17/20 DTS Neo:6 Cinema, 14 7CH Stereo, 15/18 Logic 7 Movie,
  16 PLII Movie, 19 PLIIx Movie, 21/24 Logic 7 Music, 22 PLII Music, 23/26 Neo:6 Music,
  25 PLIIx Music, 27/29 Logic 7 Game, 28 PLII Game, 30 PLIIx Game, 31..33 PLIIz,
  37 TrueHD, 38 Dolby Digital +, 39 DTS-HD MSTR, 40 DTS-HD HI RES, 41 DTS-HD LBR,
  42 Headphone Bypass, 43 Harman Headphone, 44 Multi-CH PCM, 45 Harman NSP.
- État : `*0x2000dbf0` pointe la structure audio de la source courante ; +0x11 = mode
  appliqué, u16 à +0 = réglages mémorisés (3 bits bas = catégorie). Réglages par source :
  tableau `0x2000abe8`, 0x12 o par source, écrit en mémoire non volatile par FUN_08063e04.
  Le firmware d'origine mémorise donc déjà un mode par source.
- FUN_0803a434(mode) : si le validateur du mode répond oui -> FUN_0803b038(mode, 0) :
  FUN_0803b744 (mémorise pour la source courante) puis FUN_0803394a (pose +0x11 et
  `0x2000dbec` = entrée de table). C'est la brique qu'utilise le défilement stock
  (FUN_0803a456 -> FUN_0803abb4).
- Commande stock `surround-mode` -> FUN_0801fe9c ; gardes : bit 1 de 0x2000ddd4 (allumé),
  `*0x2000dd5c == 0`, `*0x2000e1ab == 0`, bit 3 de 0x2000ddd4 nul, bit 7 de 0x2000ddcc nul ;
  puis `*0x2000e1ab = 10`.
- Patch (feature `surround`) : get-status gagne un 6e champ (mode appliqué) ; nouvelle
  commande `set-surround <code 0..45>` (cave +0x500, 0x8a o) avec les mêmes gardes, qui
  appelle FUN_0803a434 ; le push compare aussi le mode (octet +5 de PUSH_RAM).
  push_tick déplacée à +0x440. Tampon du para porté à 32 o.
- À établir sur matériel : l'afficheur et l'OSD suivent-ils sans appel explicite à la routine
  d'affichage (FUN_0801ff88) ; quels codes l'ampli accepte selon la source et le signal.

### Modes surround réellement proposés (lecture du défilement, 2026-11-13)
- Le défilement (FUN_0803a456) parcourt les catégories 0..6 ; dans une catégorie, la fonction
  « mode suivant » donne les candidats : a690 virtuel (toujours 0), a696 stéréo (2 -> 3 -> 5 ->
  9 ou 14), a72e film, a858 musique, a922 jeu. `FUN_0803ca70() != 0` = variantes 7.1 (18..20,
  24..26, 29..30, 14) ; `FUN_0803fa54() != 0` = PLIIz (31..33).
- Sur un 5.1 : Auto Select (catégorie 0, mode choisi par FUN_0803b120 selon le signal),
  Virtual Surround 0, 2CH Stereo 2/3/5, 5CH Stereo 9, Harman NSP 45, film 15/16/17,
  musique 21/22/23, jeu 27/28. Soit 12 modes + Auto Select.
- Les formats natifs (6..8, 10..12, 37..41, 44) ne se choisissent pas : c'est Auto Select qui
  les applique. D'où `set-surround auto` = FUN_0803b038(FUN_0803b120(1), 1), et le 7e champ
  de get-status (catégorie, 3 bits bas du u16 en tête de la structure audio).

### Dialogue MCU <-> module réseau (statique, 2026-11-13)
**Transport.** Trames délimitées par 0xC0 (réception octet par octet : FUN_0802ff7c, tampon
0x2000a2b8, 512 o ; émission : FUN_0802fe46). Contenu d'une requête (FUN_08073984) :
n° de séquence (2 o, gros-boutiste, 0x2000df82), commande, 1, nœud (4 o), [longueur 2 o +
données], octet de fin 0xEF (ou somme FUN_08073960 dans un cas de mise à jour).

**Modèle : des « nœuds » 32 bits qu'on lit, écrit, ou auxquels on s'abonne.**
- 0x00 LIRE -> réponse 0x80 (état, longueur, données) ; 0x04 ÉCRIRE -> 0x84 ; 0x06 activer les
  notifications -> 0x86 ; 0x01..0x03 / 0x05 listes -> 0x81 / 0x85 ; 0xC6 = notification
  spontanée (nœud + données) ; 0x87 = annulation.
- Enveloppes : FUN_08093f0c(nœud, rappel) lire ; FUN_08093f3e(nœud, len, données, rappel)
  écrire ; FUN_08093f78(nœud, 1, rappel) activer les notifications ; FUN_08073b10(nœud,
  rappel) enregistrer le rappel de notification (24 abonnements, table 0x2000b490).
- Requêtes en attente : 20 entrées de 0x18 o à 0x2000a6a8 (compteur 0x2000e0de). À 20, tout
  nouvel envoi échoue ; FUN_080732b8 vide la table au-delà de 16.
- Familles vues (138 sites d'appel) : 01xx état/démarrage du module, 05xx, 06xx, 0803xx Wi-Fi,
  0804xx réseau filaire/IP (08040800 MAC, 08040901..906 adresses), 09xx lecture média
  (Home Network, vTuner, USB), 0dxx, et **0809xx = port de commande**.

**Port de commande (c'est le MCU qui le fait ouvrir).**
- 08090100 <- 0x27 0x29 (= 10025) : FUN_08087d9c. Le port n'existe que si cette écriture aboutit.
- 08090200 : état du client (notification -> `*0x2000e2a8` ; 0 = plus de client, et
  réactivation des notifications de 08090300 dix tics plus tard). net_bye_bye_push le consulte.
- 08090300 : données reçues. Une notification arme `*0x2000e2a9 = 10` ; à zéro, si aucune
  transaction n'est en cours (`*0x2000e2a5 == 0`), LIRE 08090300 (FUN_08087de4) -> rappel
  FUN_080864b8 -> recopie dans 0x20009eb0 -> FUN_0804ef94 -> cmd_dispatch.
- 08090400 : données à envoyer (net_send). Aucun identifiant de client : le MCU ne peut pas
  choisir le destinataire, c'est le module qui décide.

**Séquence d'ouverture : une seule passe, minutée, sans vérification.**
- FUN_08091698 (compte à rebours `0x2000dfd2`) lit la configuration IP nœud par nœud, puis
  pose `*0x2000e2a7 = 200`.
- FUN_08087bd4 (appelée par FUN_08044eb4) décompte `0x2000e2a7` : à 150 écrit le port, à 100
  active les notifications de 08090200, à 50 celles de 08090300, puis s'arrête. Un accusé
  (bit 2 de 0x2000de64) fait seulement sauter l'attente.
- Le rappel d'écriture (0x080866d0) ignore le résultat pour 0809xxxx : aucun nouvel essai.
  Si l'écriture du port est perdue ou refusée, le port reste fermé jusqu'au prochain
  redémarrage de la chaîne. Cadence des tics non établie.
- HYPOTHÈSE pour le « port refusé après flash » (non prouvée, le module est une boîte noire) :
  un client qui se connecte pendant cette fenêtre, avant que les notifications soient
  actives, laisse le module et le MCU désaccordés. Cohérent avec les faits : port sain après
  2,5 min sans y toucher ; port mort quand une connexion a été tentée tôt.

### Wi-Fi : code présent, matériel absent (2026-11-13)
- Manuel de service (liste de pièces) : carte réseau = FS1230A + contrôleur Ethernet
  KSZ8851SNL ; seules antennes : Bluetooth (AN1101, module BM840) et AM/FM. Aucune pièce radio
  Wi-Fi. La notice ne mentionne que la prise réseau filaire.
- Firmware : assistant réseau complet et relié au reste (FUN_080929e0, état `0x2000e147` ;
  sous-assistant FUN_08070d00 / FUN_08070fda / FUN_080713e8, état `0x2000e155`) : région WLAN,
  recherche, liste terminée par [WPS PBC] [Rescan] [Wired] [Manual config], saisie du SSID,
  type de sécurité, clé, WPS bouton / PIN, filaire ou sans fil, DHCP ou adresses manuelles.
- Nœuds : 0803xxxx = sans fil (08030401 liste des réseaux, 08030403 connexion, 08030406
  sécurité, 08030603 DHCP, 08030a00 activation, 08030b00 état) ; 0804xxxx = filaire (08040603
  DHCP, 08040a00, 08040b00, 08040800 MAC, 08040901..906 adresses) ; 08010000 choix d'interface.
- Aucun test de modèle vu dans ces fonctions (lecture non exhaustive). Menu visible ou non sur
  l'AVR 161 : non établi.
- Vu sur le réseau (ampli allumé) : ports 8080 (rendu DLNA « HK AVR 161 », services
  AVTransport / ConnectionManager / RenderingControl, pile Intel MicroStack) et 10025 ; port 80
  fermé bien que 8080 redirige vers http://<ip>/web/index.html.

### API réseau du port 10025 : référence complète (lecture du dispatch, 2026-11-13)
**Réception (FUN_0804ef94).** Le MCU reçoit au plus 512 octets par lecture (jusqu'au premier
octet nul). Il coupe après `</harman>`, puis ne regarde QUE les balises fermantes `</name>`,
`</zone>`, `</para>` : le contenu (31 caractères au plus) est ce qui précède, depuis le `>`
d'avant. Les en-têtes HTTP sont ignorés. Si plusieurs requêtes arrivent dans la même lecture,
seule la dernière compte. Résultat dans 0x2000cb1c : nom +0, zone +0x20, para +0x40.

**Portes de cmd_dispatch, dans l'ordre.**
1. `heart-alive` : réponse immédiate, avant toute porte.
2. La zone doit commencer par « Main Zone ».
3. FUN_0802f348 : aucun drapeau « occupé » (0x2000df14 bit 0, e1de, e1dd, dfc0, e1c5, e1c6).
4. Anti-rebond `*0x2000e2a6 == 0` ; remis à 50 après chaque commande exécutée et décompté par
   FUN_08044eb4 (tic de FUN_08047360). 50 tics ~ 0,5 s mesurée => **tic de 10 ms**.
5. FUN_08071816 : si une configuration réseau est en cours, seules les commandes
   d'alimentation passent.

**Commandes reconnues** (aucune réponse sauf heart-alive ; une commande inconnue est ignorée).
- Alimentation : `power-on` (FUN_0801899c), `power-off` (FUN_080189b4), `power-toggle`
  (FUN_08018944).
- `source-selection` + para : iPod, TV, FM, AM, Disc, Internet Radio, vTuner, Media Server,
  Server, Cable Sat, USB, Game, AUX, STB, Audio, Radio, Home Network. Reconnus sans effet :
  Pandora, DVR, Sirius Radio, Source A..D.
- Volume : `volume-up`, `volume-down`, `mute-on`, `mute-off`, `mute-toggle`.
- Transport et navigation : `play`, `pause`, `next`, `previous`, `forward`, `reverse`, `up`,
  `down`, `left`, `right`, `ok`, `back`. Si FUN_080167be() == 1 (source < 8, c.-à-d. une
  entrée HDMI/analogique, avec `0x2000db00[source] == 0` et `0x2000e190 == 1`), la commande
  est relayée par FUN_08066f44(code) puis (code | 0x80) : les codes sont ceux des touches
  HDMI-CEC (0x44 lecture, 0x46 pause, 0x4b/0x4c suivant/précédent, 0x49/0x48 avance/retour,
  1..4 flèches, 0 validation, 0x0d retour). Sinon, traitement local (menu, lecture USB/réseau).
- Divers : `options`, `home`, `sleep` (FUN_0801d450), `tone`, `delay` (FUN_0801b816), `rds`
  (FUN_0801f0e8), `tune-up`, `tune-down`, `channel-up` (FUN_0801ed10), `channel-down`
  (FUN_0801f15c), `surround-mode` (FUN_0801fe9c).
- Reconnus sans effet : `setting`, `info`, `audio-effect`, `video-mode`.
- Ajouts du firmware custom : `get-status`, `set-volume`, `set-surround`,
  `source-selection` + Bluetooth.

**Réponse (build_reply).** `POST AVR HTTP/1.1`, `Host:<adresse IP sur 12 chiffres>:10025`,
User-Agent, Content-Length, puis le XML ; zone et para ne sont émis que si le contexte
0x2000cb1c vaut « status_name ». Tampon de 512 o.

**Non vérifié sur matériel** : `rds`, `delay`, `channel-up/down` ; le relais HDMI-CEC ; la
requête minimale sans en-têtes HTTP.

### Module réseau : ce qu'on peut en savoir (2026-11-13)
- **Son logiciel n'est pas dans le fichier .fw.** 0x100000..0x33FFFF = images du DSP Cirrus
  Logic (« Cirrus Logic, Inc. », version 0.6.5), 0x500000 = ressources OSD ; aucune trace du
  logiciel du module (FS1230A). Il a sa propre mémoire et sa propre mise à jour (« VENICE
  UPDATE », « NETWORK UPGRADE » dans les menus). Analyse statique impossible sans ce fichier.
- **Mesures en boîte noire sur le port 10025** (heart-alive / get-status uniquement) :
  - **Un seul client.** Une seconde connexion est acceptée et la première est fermée aussitôt
    (fin de flux côté ancien client). Le dernier connecté gagne ; un push ne peut donc aller
    qu'à lui.
  - **Première requête** : envoyée dès la connexion, servie 22 fois sur 42 (quel que soit le
    temps écoulé depuis la fermeture précédente, 0 à 1 s) ; envoyée 0,1 s ou plus après la
    connexion, servie 9 fois sur 9. Règle : attendre ~0,3 s après la connexion.
  - Délai de réponse à heart-alive : ~145 ms ou ~275 ms (deux paliers).
  - (FAUX, corrigé le 2026-11-14) Une requête sans en-têtes HTTP n'est PAS traitée : l'ampli
    rejoue alors la commande précédente. Mes sondes n'envoyaient que des heart-alive, d'où
    l'illusion. Mesure : `volume-up` sans en-têtes après un get-status -> une réponse
    get-status et aucun changement de volume. Toujours envoyer la requête HTTP complète.
  - Deux requêtes dans le même envoi : une seule réponse.
- Port 8080 : rendu DLNA (Intel MicroStack), services AVTransport, ConnectionManager,
  RenderingControl. Port 80 fermé.

### HDMI-CEC : réception et actions (statique, 2026-11-13)
- Réception : FUN_08041c18 (appelée par la boucle principale FUN_08010784). Trame dans
  0x2000d54c : [0] = émetteur << 4 | destinataire, [1] = code, [2..] = paramètres.
  Adresse logique de l'ampli : `*0x2000e06e` ; adresse physique : 0x2000df6c ; adresses des
  6 entrées HDMI : table 0x2000d8f0.
- Codes traités : 0x36 veille, 0x44/0x45 touche appuyée/relâchée (FUN_08041720), 0x46 nom,
  0x70/0x71/0x72/0x7d mode audio système et état audio, 0x80/0x81 routage, 0x82 source
  active, 0x83/0x84 adresse physique, 0x85 demande de source active, 0x86 chemin de flux,
  0x87/0x8c identifiant constructeur, 0x8f état d'alimentation, 0x9e/0x9f version,
  0xa0 commande constructeur, 0xc0..0xc4 ARC, 0x00 refus, 0xff abandon.
- Actions : FUN_0802a340(événement), seule porte : bit 0 de 0x2000df14 nul.
  1/2 mute, 3 allumage (si éteint), **4 veille**, 5/6 volume +/-, 7..12 bascule sur l'entrée
  HDMI 1..6 (FUN_08029fc2), 0x20 bascule alimentation, 0x21 bascule mute, 0x30 audio TV/ARC
  (FUN_08019196).
- **Veille (0x36)**, si diffusée ou adressée à l'ampli, ampli allumé :
  - bit 0 de 0x2000de40 posé -> FUN_080189b4 (extinction ordinaire) + PB9 et PE1 à 0 ;
  - sinon -> bit 7 de 0x2000dddc posé, bit 1 de 0x2000dde0 baissé, `0x2000e1dd = 100` :
    **extinction complète immédiate, sans passer par le sleep ni par la temporisation**.
  Le patch keepsleep ne couvre donc pas ce chemin : télé éteinte = ampli hors réseau.
  Site : `movs r0,#4 ; bl 0x0802a340` en 0x08041dce / 0x08041dd0.
- Bit 0 de 0x2000de40 : posé par FUN_0802addc, baissé par FUN_0802aed0 (avec anti-rebond
  0x2000de3c). Signification non établie (zone 2 ?).
- Aucun réglage « CEC activé / désactivé » repéré.

### Ce qui (re)lance l'ouverture du port de commande (statique)
- Chaîne de comptes à rebours, tic de 10 ms : `0x2000dfd4` (écriture d'une configuration IP
  manuelle) -> `0x2000dfd6 = 500` -> `0x2000dfd2` (lecture de la configuration IP,
  FUN_08091698) -> `0x2000e2a7 = 200` (port, FUN_08087bd4).
- `0x2000dfd2` est armé par FUN_08072a40 (à l'expiration de dfd6 : 202 ou 600), par
  FUN_08092630 (événement de connexion réseau : 505, 700 ou 1000) et par FUN_08046134 (240).
  La chaîne n'est donc pas réservée au démarrage : **tout événement de connexion réseau
  rouvre le port** 5 à 12 s plus tard.
- Piste à essayer sur un port refusé : débrancher puis rebrancher le câble réseau, au lieu de
  couper le courant.

### Drapeaux « occupé » de FUN_0802f348 (bloquent commandes réseau ; df14 bloque aussi le CEC)
- `0x2000df14` bit 0 : accès à une clé USB en cours (posé en 0x080296e6 dans FUN_0802966c,
  baissé par FUN_080402bc quand l'ouverture de fichier aboutit ; FUN_0808e4f6 = ouverture).
- `0x2000e1dd` : action d'alimentation différée (100 tics) ; à zéro, FUN_080189b4 si allumé,
  sinon FUN_08018ca4. Posé par la veille CEC et par l'expiration de la temporisation de sleep.
- `0x2000e1de` : extinction en cours (100 tics ; à 0x19 FUN_08061844, à zéro FUN_08018ca4).
- `0x2000dfc0` : défilement des versions à l'écran (FUN_08011cb0 / FUN_08052c98) : MCU, IAP,
  OSD, DSP, puis VENICE. **La version du module est en RAM à 0x2000d8b8 (16 caractères)**,
  celle du DSP à 0x2000dc54, celle de l'IAP à 0x2000e1ec.
- `0x2000e1c5` : temporisation après allumage / extinction / touche OK.
- `0x2000e1c6` : stabilisation après changement de source (puis FUN_08040574).
- Tous décomptés par le tic de FUN_0801185c, qui décompte aussi `0x2000e1ab`.

### Séquence d'alimentation : rôle des sorties (schéma, pages 169 et 171 du manuel)
- MCU IC1401 : PD8 (77) BCO_RST -> POR_N ; PD9 (78) NET_PWR_SW ; PD12 (81) USB_SEL ; PD13/PD14
  (82/85) HDMI_SDA/SCL ; PD15 (86) HDMI_RST ; PG2 (87) HDMI_MUTE_OUT ; **PG3 (88) PWR_SW1** ;
  **PG4 (89) PWR_SW2** ; PG5 (90) POWER_HIGH ; **PG6 (91) PWR_SW3** ; PG7/PG8 (92/93) VOL_EN1/2 ;
  PC6 (96) USB_OE ; PC7/PC8/PC9/PA8 (97..100) afficheur de façade (VFD_CS, CLK, RST, DATA) ;
  PG9 (124) AMP_VCC_CONT ; PE8 (59) EN_VBUS ; PE9 (60) EN_RX1_PWR ; PE12/PE13 (65/66)
  HDMI_TX_SW / HDMI_RX_SW ; PA1 (35) CEC.
- Convertisseurs (page 169) :
  - IC1201 « SIL9575 +3.3V » et IC1202 (+1,3 V HDMI) : entrée `+7VD` (alimentation
    principale), EN = PWR_SW1. Alimentent le HDMI et le DSP.
  - IC1203 : entrée `+7VD`, EN = PWR_SW2 -> USB +5 V.
  - **IC1205 « Milan +3.3V » (2 A) : entrée `ST+5V` (rail de veille), EN = NET_PWR_SW**, puis
    IC1206 -> NET_1.2V.
- Conséquences : en sleep, PWR_SW1 reste à 1 (HDMI alimenté, donc alimentation principale en
  marche) ; en « éteint », PWR_SW1, PWR_SW2, l'afficheur et NET_PWR_SW passent à 0.
  Le module réseau ne dépend PAS de l'alimentation principale : un état « éteint mais
  joignable » est électriquement possible (garder PD9 à 1 et PD8 relâché, ne pas appeler
  FUN_08011588(1) qui reconfigure des broches). Non essayé.

### HDMI-CEC : émission (statique)
- Fonctions 0x08040b08..0x08041310 : identifiant constructeur, état d'alimentation
  (FUN_08040b80), nom OSD (0x47), version CEC, demande de source active (FUN_08040d2e), pings,
  état audio (FUN_08040dea), mode audio système (FUN_08040e96 / FUN_08040f20), changement de
  routage (FUN_08041032), adresse physique (FUN_08041310), relais de touches (FUN_08041720).
- Aucune émission de « veille » (0x36) ni d'« allumage de l'écran » : l'ampli n'éteint ni
  n'allume la télé de lui-même.

### Patch netoff : module réseau alimenté ampli éteint (2026-11-13, NON flashé)
- Boucle principale FUN_08010784 : le tic réseau FUN_08047360 tourne quel que soit l'état
  d'alimentation (seules les mises à jour le suspendent) ; rien n'indique un mode basse
  consommation du MCU une fois éteint.
- FUN_08011588(1), appelée à l'extinction complète, passe PC4, PE10 et PE11 en entrée : ce ne
  sont pas des broches du module (liaison PB12..15, PD8, PD11), on n'y touche pas.
- Patch (feature `netoff`, 6 octets) : pas 0xc6, `bpl` -> `b` en 0x0801410c (PD9 mis à 1, PD8
  laissé haut) ; pas 0xaf, `bl gpio_clear(GPIOD, 0x200)` en 0x0801431a remplacé par deux `nop`.
- Commande `power-full-off` (cave +0x600) : pose le bit 7 de 0x2000dddc, baisse le bit 1 de
  0x2000dde0 et arme 0x2000e1dd = 100, comme l'ordre de veille CEC ; seulement si l'ampli est
  allumé ou en sleep. Sert à provoquer l'extinction complète sans attendre ni passer par la télé.
- Image : v1.2.0-test = v1.1.0-test + netoff.
- À établir sur matériel : l'ampli éteint répond-il sur 10025 ; `power-on` le rallume-t-il ;
  consommation ; comportement de l'afficheur et du voyant.

### Rebranchement secteur et module réseau (statique, 2026-11-13)
- Démarrage (FUN_08065676) : selon l'état mémorisé, soit allumage (`set_src_UNKNOWN_1`), soit
  mise en veille par `ddd4 |= 2 ; dddc |= 0x80 ; FUN_08018ca4()`, qui arme la séquence à 300
  (ou 250). Le démarrage en veille déroule donc la MÊME séquence d'extinction complète, pas
  0xc6 et 0xaf compris.
- À ce moment PD8 (reset du module) n'a jamais été mis à 1 : seul l'allumage le fait (pas 0xbc).
  Un patch qui garde seulement PD9 à 1 laisserait le module alimenté mais en reset après un
  rebranchement, jusqu'au premier allumage.
- netoff, version corrigée : pas 0xc6 PD9 = 1 ; pas 0xaf (23 pas plus tard) PD8 = 1 à la place
  de PD9 = 0 (`mov.w r1,#0x100` en 0x08014312, `bl gpio_set` en 0x0801431a). À l'allumage
  d'origine l'écart entre alimentation et sortie de reset n'est que de 2 pas.

### Essais sur matériel de la v1.1.0-test (2026-11-14)
- Flash puis 2 min 30 sans toucher au port : `get-status` = `110,0,2,1.1.0-test,1,45,0`.
- **Push** : `volume-up` -> message spontané `112,...` dans les 3 s ; `volume-down` -> `110,...` ;
  rien pendant 5 s sans changement. Validé pour le volume.
- **Surround** (source MHL, signal stéréo, Auto Select = Harman NSP) : acceptés 0, 5 (2CH),
  9, 45, 16, 17, 22, 23, 28 ; refusés Logic 7 Movie / Music / Game (15/18, 21/24, 27/29) et
  Dolby TrueHD (37) ; `set-surround auto` ramène en Auto Select. Une commande envoyée moins
  d'une seconde après la précédente est ignorée (anti-rebond).
- **Mute : bug trouvé.** `mute-on` ne changeait rien au champ mute. Le vrai indicateur est le
  bit 4 de `0x2000dddc` (basculé par FUN_0801b030) ; le bit 1 de `0x2000de40`, lu depuis la
  v1.0.0, est autre chose. De plus `mute-on`, `mute-off` et `mute-toggle` appellent tous la
  même bascule dans le firmware d'origine.
  Corrigé dans le constructeur (non flashé) : lecture du bon bit, et feature `mute` qui
  n'envoie `mute-on` / `mute-off` à la bascule que si l'état doit changer.
- Non vérifié : OSD vert (à regarder à l'écran), push du mute, de la source, de
  l'alimentation et du surround.
- Suite des essais v1.1.0-test (2026-11-14) : OSD vert confirmé à l'écran par le propriétaire.
  Push mesuré, délai entre la commande et le message spontané : surround 0,7 s (22 puis auto),
  source 0,6 à 0,9 s (Disc puis MHL), mise en veille 2,5 s (champ alimentation à 0), allumage
  1,1 s. Mute : aucun message, comme attendu avec le mauvais indicateur de cette image.
