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

### Essais sur matériel de la v1.2.0-test (2026-11-14)
- Mute validé : champ à 1 après `mute-on`, à 0 après `mute-off` ; chaque changement est poussé ;
  `mute-on` et `mute-off` envoyés une seconde fois ne font rien ; `mute-toggle` bascule.
- `power-full-off` : le champ alimentation passe à 0, la façade s'éteint (pas de « Device
  Sleep »). **Le module réseau reste alimenté** : ping et connexion TCP au port 10025 acceptés
  pendant toute la mesure (140 s). `get-status` répond encore à +8 s et +15 s, puis plus
  rien : la connexion est acceptée mais aucune réponse.
- Cause : FUN_080146b4, appelée quand `0x2000e1d3` (posé à 7 au pas 0xaf) ou `0x2000e1d4`
  arrive à zéro. Elle coupe PG3, configure des interruptions externes de réveil
  (FUN_08014704), puis FUN_08065580(1,1) met le MCU en **mode STOP** (PWR_CR, SLEEPDEEP, WFI).
  Au réveil : FUN_08014874 puis FUN_08065f74 (remise en route des horloges).
  Un gestionnaire en 0x08074160 réarme `e1d4 = 20` et `e1d3 = 7` quand l'ampli est éteint :
  le MCU se rendort après chaque réveil. C'est ce sommeil qui tient la promesse des 0,5 W.
- Suite (v1.2.1-test, non flashée) : entrée de FUN_080146b4 détournée vers le cave (+0x680).
  Si le mot en RAM `0x2001ff08` vaut `NETS` (0x4e455453), retour immédiat sans sommeil ; sinon
  comportement d'origine. `power-full-off net` pose le mot, `power-full-off` seul l'efface.
  Le mot disparaît à la coupure secteur : filet de sécurité si le MCU éveillé se bloque
  (HDMI et DSP ne sont plus alimentés dans cet état, jamais exercé longtemps par le
  firmware d'origine).
- Rallumage par télécommande depuis « éteint, module resté alimenté, MCU endormi » : l'ampli
  se rallume du premier coup, mais le port de commande accepte la connexion sans jamais
  répondre. Le firmware d'origine compte sur le redémarrage du module à l'allumage pour
  rejouer l'ouverture du port ; un module resté seul pendant le sommeil du MCU garde des
  échanges en suspens. Conclusion : ne jamais laisser le module alimenté quand le MCU dort.
- v1.2.2-test (remplace la v1.2.1-test, jamais flashée) : les trois `bl gpio_clear` du
  module passent par des portes du cave (+0x6c0) conditionnées par le même indicateur RAM.
  Sans lui, séquence d'extinction strictement d'origine ; avec lui, module alimenté et MCU
  éveillé.

### Essais sur matériel de la v1.2.2-test (2026-11-14) : éteint ET joignable
- Après flash et 2 min 30 : port sain, `fw 1.2.2-test`.
- `power-full-off net` : 18 lectures `get-status` réussies sur 18 de +9 s à +160 s, ping constant ;
  façade vide et voyant orange constatés par le propriétaire (état éteint, pas « Device Sleep »).
  Toujours joignable plusieurs minutes plus tard.
- `power-on` par le réseau depuis cet état : ampli annoncé allumé en moins de 3 s.
  Une lecture a expiré ~15 s après l'allumage (un ping perdu au même moment), puis 12 lectures
  réussies sur 12 pendant 80 s. Cause de ce trou non établie.
- Reste à faire : tenue sur plusieurs heures ; consommation ; rendre le comportement permanent
  (y compris au rebranchement secteur et sur l'ordre de veille HDMI-CEC) ; remettre la
  temporisation veille -> éteint.

## Éteint joignable : essai d'une nuit et version candidate (2026-11-14)

### Mesure matériel, v1.2.2-test
- `power-full-off net` à 01:04, surveillance passive 8 h : 480 pings sans perte, 32 lectures
  `get-status` sur 32 (une par quart d'heure), toutes `power=False`.
- 09:05 : `power-on` par le réseau -> ampli allumé ; `power-full-off net` -> de nouveau éteint
  et joignable. Les délais de cette vérification ne sont pas exploitables (le Mac s'endormait).
- Non mesuré : consommation dans cet état ; comportement au rebranchement secteur.

### v1.2.3-test (features netoff + sleeptimer), non flashée à cette date
- L'état éteint joignable devient le comportement PAR DÉFAUT de toute extinction complète
  (fin de temporisation, ordre de veille HDMI-CEC, `power-full-off`, démarrage après
  rebranchement) : module alimenté (PD9 = 1, sortie de reset au pas 0xaf), MCU jamais en STOP.
- `power-full-off deep` : extinction d'origine (module coupé, MCU en STOP). Indicateur RAM
  0x2001ff08 : DEEP_ARMED (0x44454550) à la commande, DEEP_ACTIVE (|1) au premier passage en
  STOP, effacé par le tick 1 s dès que l'ampli est rallumé. Il survit aux réveils du MCU sans
  allumage : FUN_080146b4 n'est appelée qu'à l'expiration des compteurs 0x2000e1d3 / e1d4
  (0x08010c32, 0x080126c6), donc une fois par endormissement.
- sleeptimer : décompte veille -> éteint (3600 s) rétabli à l'identique du bloc d'origine, dans
  le cave (+0x780), avant push_tick. `power-full-off` remet le compteur à 0 pour que le
  décompte ne relance pas une extinction sur un ampli déjà éteint.
- HDMI-CEC : aucun patch. L'ordre de veille de la télé éteint toujours l'ampli directement,
  mais « éteint » est maintenant joignable.
- À valider sur matériel : veille -> éteint au bout d'une heure, extinction par la télé,
  rebranchement secteur (le module démarre-t-il et le port 10025 s'ouvre-t-il sans que l'ampli
  ait été allumé ?), `power-full-off deep` puis rallumage à la télécommande.

### Perte du module à la fin de la temporisation de veille (2026-11-14 et 15, v1.2.3-test)
- Constat : ampli éteint et joignable -> `power-on` par le réseau -> `power-off` 9 s après ->
  veille joignable pendant une heure -> à la fin de la temporisation, plus de ping ni d'ARP,
  façade éteinte, voyant orange ; la télécommande rallume l'ampli. Vu le 14 à 21:40 (via Home
  Assistant) et reproduit le 15 : `power-off` à 12:35:13, ping perdu à 13:35:18 (t+60,1 min).
- Contre-exemple : le 14, veille à 14:09 après 10 min de marche (allumage depuis la veille, pas
  depuis l'éteint), temporisation échue à 15:09, module resté joignable jusqu'à 20:40.
- Les extinctions complètes par commande (`power-full-off`) n'ont jamais perdu le module (8 h
  la nuit du 14, plusieurs essais courts).
- Lecture statique, rien de concluant : la commande et la temporisation font les trois mêmes
  écritures (dddc |= 0x80, dde0 &= ~2, e1dd = 100) ; seule la commande écrit l'indicateur
  0x2001ff08. Sites qui coupent PD9 / PD8 hors portes : FUN_0802f15a (allumage, si
  `ddd8 & 0x30`) et FUN_08040662 état 4 (lecture de fichier, mise à jour).
- `ddd8` bits 4 et 5 = mises en protection (FUN_08013060 : moyenne d'une mesure < 0x621 ;
  FUN_08013858 : PE3 bas 12 tics), elles appellent FUN_08018ca4. `ddf4` bit 6 = allumage après
  protection, effacé au pas 0x9b.
- Pas 0xaf, extinction complète : lit PG14 ; à 0 -> PG5 (POWER_HIGH) = 1, PG6 (PWR_SW3) = 1,
  PE8 (EN_VBUS) = 0 ; à 1 -> PG5 = 0, PG6 = 0, PE8 = 1. Seule dépendance à une entrée dans ce
  pas ; rôle de PG14 non établi. Piste non vérifiée : alimentation de veille en mode réduit.
- Hypothèses à départager sur matériel : extinction 9 s après l'allumage ; allumage depuis
  l'état éteint-joignable ; état d'une entrée (PG14) au moment de l'extinction.
- Outil : feature `diag` (images de test seulement, jamais publiée), `debug-peek <adresse
  décimale>` répond les 4 octets lus, `debug-poke <valeur>` écrit le mot à l'adresse mémorisée
  (RAM seulement). Permet de ramener la temporisation `0x2000dd7c` à quelques secondes et de
  relever drapeaux et ports avant la coupure. Image `out/AVR1610_patch1_v1.2.4-diag.fw`.

### Port 10025 fermé après un démarrage à froid (2026-11-15, v1.2.4-diag puis v1.2.3-test)
- Constat : après le flash de la v1.2.4-diag (clé restée branchée, façade sur FM alors que la
  télé montrait l'Apple TV), puis après un rebranchement secteur, puis après reflash de la
  v1.2.3-test (clé retirée, ampli rallumé seul) : ping et port 8080 du module OK, port 10025
  refusé, y compris après un cycle veille -> allumage à la télécommande. L'image diag n'est
  donc pas en cause. Après un rebranchement suivi d'un allumage rapide à la télécommande
  (délai non mesuré), le port s'est ouvert (17:14).
- Épisode non expliqué : à 16:05, après le premier rebranchement, le module a pris l'adresse
  169.254.50.219 puis n'a plus répondu ; revenu en 192.168.1.58 après le reflash.
- Lecture du code : `0x2000dfd2` (décompte de FUN_08091698, qui finit par `e2a7 = 200` puis
  l'écriture du port) n'est armé que par des notifications d'état réseau du module
  (FUN_08092630, FUN_080929e0 : 700 ou 1000 si `*0x2000e141 != 0` ; FUN_08072a40 ;
  FUN_08046134). FUN_08049e40 (mise en veille, appelée par FUN_08018ca4) le remet à 0.
- Hypothèse (cohérente avec l'essai, non prouvée) : avec netoff le module démarre dès le
  branchement secteur ; si sa notification « connecté » arrive ampli éteint, la passe
  d'ouverture est perdue ou annulée, et rien ne la relance. À vérifier avec l'image diag
  (lecture de dfd2, e2a7, e141 après un démarrage à froid).

### Essais avec les images diag (2026-11-15, 17:35 -> 19:05)
- v1.2.4-diag puis v1.2.5-diag (anneau de trace `0x2001fc00`, 64 entrées d'une seconde, figé
  ampli allumé). Lecture mémoire validée (SP initial, volume, bit d'alimentation).
- Port 10025 : rouvert à chaque fois par un débranchement / rebranchement du câble Ethernet
  ampli allumé (3 fois sur 3). Confirme que l'ouverture dépend d'une notification de connexion
  reçue ampli allumé. Après un rallumage à la télécommande depuis l'état « module tombé », le
  port s'est ouvert seul une fois (18:09) et pas une autre (18:54).
- Tempo ramenée à 10-15 s par `debug-poke` sur `0x2000dd7c` :
  - rallumage télécommande -> `power-off` -> tempo : module resté joignable (17:47), état
    final identique à un `power-full-off` direct (PD = 0x8300, de40 = 0x40) sauf dde0 = 1.
  - `power-full-off` -> `power-on` réseau -> `power-off` 9 s après -> tempo : module tombé
    2 à 3 s après l'échéance, 4 fois sur 4 (17:38, 18:01, 18:10, 18:53).
  - extinction par tempo -> `power-on` réseau : port 10025 refusé, ping OK (17:48).
- Trace relue après la coupure de 18:53 : pendant les 64 s précédant le rallumage, MCU en
  marche (tic 1 s), PD9 = 1, PD8 = 1, broches en sortie, dddc = 0, dd5c = 0, GPIOG ODR = 0.
  **Le MCU ne coupe donc ni l'alimentation ni le reset du module** ; l'indicateur 0x2001ff08
  valait 0. Reste : un ordre envoyé au module, ou une autre sortie (ports A, B, C, E, F non
  tracés).
- Lecture : FUN_08047a1c (extinction complète) et FUN_08047e34 (allumage après protection)
  remettent à zéro tout l'état du module côté MCU ; FUN_08049e40 (veille) en remet une partie
  et annule la passe d'ouverture du port. Le firmware d'origine suppose le module coupé à
  l'extinction et redémarré à l'allumage ; avec netoff les deux côtés se désynchronisent.
- Pistes de correction, non essayées : (a) à l'allumage depuis l'éteint, redémarrer le module
  comme le fait l'origine après une protection (FUN_080481cc), au prix d'environ 30 s sans
  réseau ; (b) ne pas faire l'extinction complète hors `deep` (rester en veille, comme la
  v1.1.0) ; (c) tracer tous les ports pour comparer l'état « bon » et l'état « tombé ».

### Journal des requêtes vers le module (2026-11-15 soir, v1.2.6-diag puis v1.2.7-diag)
- Feature `diag` étendue : détour de FUN_08073984 (point de passage de toutes les requêtes :
  r0 = 0 lire / 4 écrire / 6 notifications, r1 = {nœud, longueur, données}) vers un anneau de
  512 entrées en `0x2001c000` (indice en `0x2001bff8`, secondes en `0x2001bffc`) ; ODR des
  ports A..G au dernier tic éteint en `0x2001fe10`. La v1.2.6 notait aussi 08090300 /
  08090400 : la lecture du journal par le réseau l'écrasait (2 requêtes par lecture). La
  v1.2.7 les ignore.
- État « module tombé » : ODR des sept ports identiques à l'état éteint-joignable sain
  (A 0, B 0, C 0x180, D 0x8300, E 0x100, F 0x2000, G 0). Aucune cause électrique côté MCU.
- Extinction directe (`power-full-off`) : aucune requête envoyée au module (hors port de
  commande), deux essais.
- Démarrage à froid (flash de 21:59) : 01020000 <- 1, 08010000 <- 0, 09010000 <- 0,
  notifications 06030300 / 06060100 / 0d020000, 05090000 <- 4, 0d010000 <- 1, lecture
  01030000, 08010000 <- 1, notification 08040b00, 08040a00 <- 2, 08040403, puis **écriture du
  port 08090100 <- 10025 à +28 s et +32 s, sans effet** (port refusé). Après rebranchement du
  câble Ethernet : lecture de 08040902..906, 901, 800, puis 08090100 <- 10025 et notification
  08090200 : port ouvert. Le défaut du démarrage à froid est donc une écriture du port faite
  avant que le module soit prêt, jamais rejouée.
- 01020000 n'est écrit que par FUN_08094356, appelée par FUN_08074eac (initialisation) :
  pas un ordre d'extinction.
- Essai de 22:12 (scénario qui casse) : module tombé ; après rallumage à la télécommande,
  port refusé ; après rebranchement Ethernet, port ouvert mais **aucune réponse du MCU**
  (heart-alive, get-status), y compris après arrêt du client Home Assistant, un
  cycle veille -> allumage à la télécommande et un second rebranchement. Journal non lu.
  État jamais vu auparavant ; piste : file des requêtes en attente (20 entrées en
  0x2000a6a8) saturée.

### Cause du module qui tombe : reconfiguration réseau lancée ampli éteint (2026-11-15, 22:55)
- Journal du scénario qui casse (v1.2.7-diag ; `power-full-off` -> `power-on` -> `power-off`
  9 s après -> tempo), au début de l'extinction complète, dddc = 0x80, ampli éteint :
  dd5c 300 : 08010000 <- 0 ; 298 : 09010000 <- 0 ; 271..268 : notifications 06030300,
  06060100, 0d020000 ; 266 : 05090000 <- 4 ; 265 : 0d010000 <- 1 ; 263 : lecture 01030000 ;
  puis plus rien. Au démarrage ou à l'allumage, la même séquence continue par 08010000 <- 1
  deux à trois secondes plus tard, puis 08040b00, 08040a00 <- 2, 08040403, et l'ouverture du
  port. **08010000 = interface réseau du module (0 coupée, 1 active).** Module alimenté, PD9 /
  PD8 à 1, mais absent du réseau. Le rallumage à la télécommande rejoue la séquence entière.
- Chaîne : FUN_08087304(v) écrit 08010000. La valeur 0 ne vient que du décompte `0x2000df86`
  (FUN_08075404, à 200), armé à 0xca par FUN_08075374 <- FUN_08075368 <- **FUN_08074ef2(1)**.
  Appelants : FUN_08094a84 sur les événements 0x900 / 0x901 (FUN_08094380, appelée par
  FUN_08046134 quand `0x2000decc` ou `0x2000ded4` arrive à zéro), et FUN_0802ff7c (analyse des
  trames du module) sur la notification d'état 0101 = 2 ou 3 quand `0x2000e16b == 1`.
- Origine de la demande : pas d'allumage FUN_080481d8, si `0x2000e232 == 0` (module pas vu
  « prêt » ; FUN_08047a1c le remet à 0 à chaque extinction complète) -> `0x2000dec8 = 800`
  (8 s), puis `decc = 3`, puis l'événement. Le firmware d'origine suppose un module qui vient
  de démarrer. Ce qui retient la demande pendant la veille et la libère à l'extinction
  complète n'est pas établi.
- Port fermé au démarrage à froid : même famille. L'écriture du port suit de peu
  08010000 <- 1 ; si le module n'a pas encore sa connexion, elle échoue, et seule une
  notification de connexion relance la passe.
- Correctif candidat (feature netoff, v1.2.8-diag, NON validé sur matériel) : porte à
  l'entrée de FUN_08074ef2 ; hors extinction profonde, retour immédiat si l'ampli n'est pas
  allumé (bit 1 de 0x2000ddd4). Tests : test_netoff.py (reconfiguration réseau).
  Limite connue : une séquence lancée ampli allumé puis interrompue par une extinction dans
  les 3 s reste possible ; à surveiller.

### Correctif validé sur matériel : v1.2.8-diag (2026-11-15, 23:17 -> 23:25)
- Scénario qui cassait (`power-full-off` -> `power-on` réseau -> `power-off` 9 s après ->
  tempo ramenée à 10 s) : extinction complète déroulée (dd5c 284 -> 0, PD = 0x8300), module
  resté joignable, **aucune requête envoyée au module** pendant l'extinction (journal).
- `power-on` réseau depuis cet état : la reconfiguration part ampli allumé, 18 à 26 s après
  l'allumage, et va au bout : 08010000 <- 0 ... 08010000 <- 1 (3 s), lecture de la
  configuration IP, 09010000 <- 1, 08090100 <- 10025. `get-status` répond ensuite. Pendant
  ces quelques secondes l'ampli est injoignable : c'est l'origine des lectures ratées
  constatées 15 à 30 s après chaque allumage.
- `power-off` 6 s après la fin de la reconfiguration : l'écriture du port tombe pendant la
  séquence de mise en veille (dd5c = 196), sans conséquence.
- Non corrigé : port 10025 fermé après un démarrage à froid (ouvert une seconde à 23:13:31
  puis refusé ; rouvert par un rebranchement Ethernet).
- Non testé : extinction pendant les 3 s où l'interface est coupée ; rebranchement secteur
  sans allumage ; `power-full-off deep` ; veille de la télé (CEC).
- Nuit du 15 au 16 : surveillance passive lancée à 23:26, ampli en veille, tempo réelle de
  3600 s (échéance vers 00:24), client Home Assistant arrêté.
- Nuit du 15 au 16, relevé à 01:53 : usage réel 23:25 -> 00:15, veille à la télécommande,
  temporisation de 3600 s échue vers 01:15, ampli éteint et joignable ensuite (ODR et de40
  de l'état éteint-joignable, aucune requête au module depuis l'allumage). Aucun ping perdu.

### Port 10025 fermé après un démarrage à froid : analyse et image v1.2.9-diag (2026-11-16)
- Le journal du démarrage à froid (flash de 23:13) et celui d'un allumage réseau depuis
  l'éteint-joignable (qui marche) montrent **les mêmes requêtes, au même rythme** : 08010000
  <- 1, puis 08090100 <- 10025 deux fois (11 s et 13 s plus tard). La différence est donc côté
  module. À froid le port s'est ouvert une seconde (23:13:31, juste après la 2e écriture) puis
  a été refusé : l'écriture aboutit, c'est ensuite que le port se referme.
- Rappel des notifications = 0x0808671c (pas une fonction pour Ghidra). 08040b00 (état du
  réseau filaire) : 0 / 1 -> événements 0x607 / 0x608, **2 = connecté** -> si `0x2000e138 == 0`
  appel de FUN_08092630, puis `e138 = 1` ; 0x64 / 0x65 -> 0x60b / 0x60c. 08090200 -> `e2a8`.
- FUN_08092630 (la seule relance sur connexion) ne fait rien si l'ampli n'est pas allumé
  (bit 1 de ddd4) et n'arme `dfd2` que si `0x2000e141 != 0`. Une connexion établie ampli éteint
  (rebranchement secteur sans allumage) ne rouvre donc jamais le port ; et la relance n'a lieu
  qu'au front `e138` 0 -> 1.
- Rappel des écritures = 0x080866d0 : ne regarde l'état (`+0xc`) que pour 08030402 / 08030404.
- Vérifié en émulation sur la routine d'origine FUN_08087bd4 : `e2a7 = 200` -> écriture du port
  50 tics plus tard, notifications 08090200 à 100, 08090300 à 150. FUN_08087bd4 est appelée
  par FUN_08044eb4 <- FUN_08047360 (tic réseau, tourne quel que soit l'état d'alimentation).
- Pas établi : ce qui referme le port côté module (connexion d'un client avant l'activation
  des notifications ? fin du démarrage du module ? changement d'adresse ?).
- Feature `portretry` (tests : test_portretry.py) : dans la chaîne du tic 1 s, toutes les 32 s,
  `e2a7 = 200` si aucun client (`e2a8 == 0`), aucune passe en cours (`e2a7 == 0`) ni programmée
  (`dfd2 == 0`), et hors extinction profonde. Compteur en `0x2001ff10`. NON validée sur
  matériel. Limite connue : si `e2a8` reste non nul après la disparition d'un client, pas de
  relance.
- Feature `diag` étendue : le journal note aussi ce que le module renvoie, notifications
  (opération 0xc6, valeur = 1er octet) et accusés d'écriture (0x84, valeur = état), hors
  08090300 / 08090400.
- Image `out/AVR1610_patch1_v1.2.9-diag.fw` (sha256 4e888bf9...), NON flashée. Essais prévus :
  flash sans sonder le port pendant 3 min ; rebranchement secteur + télécommande en sondant ;
  rebranchement secteur sans allumer. Lire le journal après chacun.
- Lecture complémentaire (2026-11-16, 02:30), pistes écartées ou non tranchées :
  - `0x2000e141` = 1er octet du nœud 08040901 (ou 08030901), lu par la chaîne `dfd2` ;
    `0x2000e292` en est l'inverse. Probablement « adressage automatique » ; écrit aussi par
    FUN_080478fc et par la routine des réglages IP (`net_bye_bye_push`, mal nommée : elle
    applique la configuration IP après le bye-bye). Sur cet ampli (DHCP) il est non nul une
    fois lu, donc la relance sur connexion est bien armée ampli allumé.
  - `net_send` n'a que deux appelants d'origine (cmd_dispatch, réglages IP) ; notre push en est
    un troisième. Un push émis sans client connecté arrive tous les jours (commande puis
    déconnexion, tic une seconde après) sans fermer le port : pas la cause en régime établi.
    Après un flash la RAM est conservée (le journal d'avant flash est resté lisible), donc
    l'état du push aussi : un push peut partir pendant le démarrage. Non observable dans les
    journaux v1.2.7 / v1.2.8, qui ignorent 08090400. Non tranché.
  - Les journaux v1.2.7+ ignorant 08090300, l'absence de « NOTIF 08090300 » après l'écriture
    du port n'est pas un indice.
  - Conclusion : côté MCU, les requêtes sont identiques à froid et à chaud ; la suite passe
    par le journal des notifications reçues (v1.2.9-diag).

## Essais v1.2.9-diag et cause du port fermé (2026-11-16, 10:30–11:15)

- **Essai 1 (flash, aucun sondage 3 min)** : port ouvert à 10:36:09 (get-status OK). Connexion
  perdue ~10 s plus tard, pendant la lecture du journal ; port refusé ensuite (100 s de sondage),
  malgré `portretry`. Veille / rallumage à la télécommande : ne rouvre rien (module resté alimenté,
  la séquence d'ouverture n'est pas rejouée).
- **Essai 2 (secteur débranché / rebranché, allumage télécommande, un seul client qui attend)** :
  connexion acceptée à 11:09:47, première lecture `0x2000e2a4 = 0x9e000000` → décompte `e2a7 = 158`,
  soit 8 tics avant l'écriture de 08090100. Lecture suivante perdue, port refusé jusqu'à la fin
  (11:11:50).
- **Conclusion** : écrire 08090100 pendant qu'un client est connecté coupe le client et laisse le
  port fermé. Le firmware d'origine l'écrit deux fois à ~2 s d'écart au démarrage : un client qui
  se connecte entre les deux (sonde, Home Assistant) déclenche le défaut. `portretry` reproduisait
  la même chose à chaque relance → **retiré des images** (code encore présent, à supprimer une
  fois le correctif validé). La nuit sur v1.2.8 était stable parce que rien ne réécrivait le port.
- **Non établi** : pourquoi le port ne revient pas ensuite ; si `e2a8` est déjà non nul quand la
  deuxième écriture part (la notification 08090200 n'est activée qu'au décompte 100 de la
  première passe).
- **v1.2.10-diag** (non flashée, sha256 b123d6ed…c5d005) : v1.2.8-diag + journal des notifications
  et accusés + `portguard` (détour de FUN_08087d9c, 0x08087d9c → cave+0xe00 : retour immédiat si
  `e2a8 != 0`). Tests : `tests/test_portguard.py`, suite 268/268.

### v1.2.10-diag : port jamais ouvert, sens de `e2a8` inversé (12:05)

- Flash de v1.2.10-diag puis démarrage à froid : module joignable (ping, 8080) dès 11:58, port 10025
  refusé en continu, sans qu'aucun client se soit connecté.
- Cause : `0x2000e2a8` vaut **1 à l'initialisation** (`movs r1,#1 ; strb` en 0x0804812e et
  0x08048362) et la notification 08090200 le met à **0 quand un client se connecte** (d'où le
  `df9e = 10` qui réactive la notification des données entrantes). J'avais lu l'inverse.
  `portguard` bloquait donc toutes les écritures sans client ; `portretry` (v1.2.9) ne relançait
  que **lorsqu'un client était connecté**, ce qui explique la coupure de l'essai 1.
- Un flash ne coupe pas l'alimentation du module : un port mort le reste après le redémarrage.
- **v1.2.11-diag** (non flashée, sha256 47745e8c…40334c) : garde inversée (retour immédiat si
  `e2a8 == 0`), 1 octet de différence dans le cave + la version. Suite 269/269.
- `portretry` : code et tests toujours présents avec la condition à l'envers ; à supprimer.

### v1.2.11-diag validée à froid (12:16–12:35)

- Flash, secteur débranché / rebranché, allumage télécommande, un client en attente.
- Journal : `08010000 ← 1`, 10 s plus tard `ECRIRE 08090100` (12:16:50), client connecté à 12:16:53
  (`<-NOTIF 08090200 = 0`, `e2a8 = 0`), deuxième passe 4 s après la première : notifications
  08090200 / 08090300 réactivées, **pas de seconde écriture de 08090100** (garde active).
  Connexion conservée. `<-NOTIF 08090200` : 0 à la connexion, 1 à la déconnexion (sens confirmé).
- Coupure inexpliquée ~12:17:30–12:18:10 (ping perdu aussi, aucun échange MCU ↔ module, pas de
  notification de déconnexion) ; reconnexion acceptée ensuite.
- Surveillance 15 min ensuite : 0/180 ping perdu, 15/15 lectures d'état.
- Reste : portretry à supprimer, image de release sans diag, essais « rebranché sans rallumer »,
  « rallumage tardif », extinction pendant la fenêtre de configuration, `power-full-off deep`.

### Port mort à l'allumage depuis l'éteint, client connecté (17:45) → v1.2.12-diag

- Home Assistant connecté en permanence (une seule connexion gardée ouverte ; le module refuse
  alors tout autre client : « refusé » ne veut donc pas dire « port mort »). Ampli éteint-joignable,
  allumage : HA « allumé » 17:44:50, « indisponible » 17:45:27, port refusé ensuite. Journal perdu
  (une coupure secteur de 5 s efface la RAM ; l'indice repart vers 95 à chaque démarrage).
- Explication retenue (non lue dans un journal) : l'allumage depuis l'éteint relance l'interface
  réseau (08010000 ← 0 puis ← 1, 18 à 26 s après l'allumage, déjà noté le 15). Le client tombe sans
  notification 08090200, `e2a8` reste à 0, et `portguard` court-circuite l'écriture du port qui suit.
- **v1.2.12-diag** (non flashée, sha256 b35823e9…47cac2) : détour de FUN_08087304 (0x08087304 →
  cave+0xe40) qui remet `e2a8 = 1` à chaque écriture de 08010000 ; + feature `powerstate`.
- **powerstate** : 5e champ de get-status = 1 allumé, 2 en veille, 0 éteint. Veille = bit 1 de
  `0x2000dde0` (lu sur matériel : allumé 0x40, veille 0x03 avec dd7c = 0xe02, éteint 0x01 avec
  dd7c = 0). Sans la feature, 0 dans les deux cas (images publiées reconstructibles).
  `ampli.py` mis à jour. Suite firmware 262/262, client 39/39.
- La commande brute `sleep` est la minuterie d'arrêt de la télécommande (dddc passe à 0x40), pas la
  mise en veille ; envoyée une fois par erreur à 18:05, effacée par l'extinction / allumage suivant.

### v1.2.12-diag sur matériel (18:44–18:48)

- Scénario de 17:44 rejoué avec un client qui garde sa connexion : `power-off`, `power-full-off`,
  `power-on` ; connexion perdue à +31 s (relance de l'interface), **reconnexion acceptée 3 s plus
  tard**, stable ensuite (100 s). Le correctif `e2a8 = 1` sur écriture de 08010000 tient.
- powerstate : `get-status` renvoie bien 1 / 2 / 0. Le bit « veille » (dde0 bit 1) n'apparaît que
  2 à 3 s après la sortie de l'état allumé, donc l'état poussé à ce moment dit « éteint », et ni
  ce passage ni veille → éteint n'étaient poussés (bit hors de l'état surveillé).
- **v1.2.13-diag** (non flashée, sha256 d84374bb…745a0b) : le bit veille entre dans l'état surveillé
  par push_tick (bit 10 du mot mémorisé). Suite 269/269.
- Mesure : les lectures debug-peek en rafale se décalent d'une réponse quand une requête est
  perdue (colonnes glissées dans e9) ; un état poussé peut aussi être lu comme réponse à get-status.

### Port mort après un allumage depuis l'éteint, HA connecté (20:33) → v1.2.14-diag

- Historique HA : veille 19:44:55, éteint 20:32:24 (fin de l'heure de veille), allumé à la
  télécommande 20:32:38, indisponible 20:33:14. Port refusé en continu ensuite (60 s d'essais),
  ping OK.
- Port rouvert **sans coupure secteur** à 22:28 en revalidant la configuration dans le menu
  Réseau de l'ampli (08010000 ← 1, puis 08090100 ← 10025) : RAM et journal conservés.
- Journal (heures recalées sur la connexion de 22:28:08) : 20:32:55 `08010000 ← 0`, 20:32:58
  `← 1`, 20:33:00 `08040b00 = 0`, 20:33:08 `ECRIRE 08090100` (acquittée) + abonnement 08090200,
  `08040b00 = 2`, 20:33:10 **seconde `ECRIRE 08090100`** (acquittée). Aucune notification 08090200
  ensuite pendant 1 h 55.
- Même relance à 19:12 (essai réussi) : `08040b00 = 2`, écriture, `<-NOTIF 08090200 = 1`, seconde
  écriture 2 s après, HA (alors indisponible, un essai toutes les 10 s) reconnecté 8 s plus tard.
  Relance de 19:02 avec un client qui réessaie sans arrêt : une écriture, client connecté 3 s
  après, seconde passe court-circuitée par la garde.
- Explication retenue (non observée directement : pas de notification dans le journal) : un
  client se connecte entre les deux écritures, avant que 08090200 le signale ; la seconde
  écriture le coupe et ferme le port (cause 1). Cohérent avec le démarrage à froid du 15
  (écritures à +28 s et +32 s « sans effet », un lecteur réessayait en boucle).
- **v1.2.14-diag** (sha256 a3fbed7e…6451c5) : `portguard` ne refait pas une écriture du port
  acquittée (rappel 0x080866d0, nœud 08090100, état 1) pendant 20 s (`0x2001ff10`, décompté par
  le tick 1 s, remis à 0 par l'écriture de 08010000 ; valeur > 20 = RAM non initialisée, ignorée).
  portguard nécessite maintenant push. Suite 285/285.

### v1.2.14-diag sur matériel : ampli « sourd » après la relance (22:47) — NON validée

- Flash 22:40, `get-status` OK. Scénario e11 (client qui interroge toutes les 0,5 s et se reconnecte
  toutes les 0,2 s) : `power-off` 22:47:03, `power-full-off`, `power-on` 22:47:28, connexion perdue
  à +29 s. Ensuite **connexion TCP acceptée mais aucune réponse**, même à `heart-alive` (pourtant
  traité avant toute porte « occupé »), pendant 28 min. Clé USB restée dans l'ampli depuis le flash
  (retirée à 23:03, sans effet). Sortie vidéo vers la télé perdue à un moment non daté.
- Revalidation du menu Réseau à 22:51:55 : interface relancée, sans effet sur la surdité. Pas
  d'écriture du port dans cette relance : le lecteur s'est connecté avant l'étape (garde légitime).
- Reflash v1.2.13-diag à 23:15 (redémarrage du MCU) : répond à nouveau. Le journal survit au flash
  et l'indice continue (pas de remise à zéro).
- Journal de la période sourde : à chaque connexion `<-NOTIF 08090200 = 0`, `<-ACK 08090300`, puis
  `= 1` à la déconnexion. Le module signale donc les clients et acquitte les abonnements ; c'est le
  MCU qui ne traite plus les données reçues ou n'envoie plus ses réponses (08090300 / 08090400 hors
  journal). FUN_08087e0c (envoi) et le rappel 0x080864b8 (réception) n'ont pas de drapeau
  « occupé » propre ; cause non trouvée.
- Lecture du code : la passe d'ouverture (FUN_08087bd4, décompte e2a7 : 150 écriture du port,
  100 abonnement 08090200, 50 abonnement 08090300 ; bit 2 de de64 pour sauter d'étape) continue
  sans l'écriture ; le saut de la seconde écriture n'explique pas la surdité à lui seul.
- Trois variables non séparées : le correctif v1.2.14, le client très insistant d'e11, la clé USB.
  Essai discriminant suivant : e11 tel quel sur la v1.2.13, clé retirée.
- Entrées 0..71 et 419..511 de l'anneau (séquence de 22:47 elle-même) non lues.

### Surdité reproduite sur la v1.2.13-diag, clé retirée (23:30) : ni le correctif ni la clé

- Journal de 22:47 (v1.2.14) relu après reflash : `08010000 ← 0` puis `← 1` 3 s après, écriture du
  port acquittée 9 s plus tard, `08040b00 = 2`, seconde passe 3 s après **sans écriture** (abonnement
  08090200 seul). Le correctif fait ce qui est prévu ; même déroulé au démarrage qui suit le flash,
  où l'ampli répondait.
- e11 rejoué tel quel sur la v1.2.13-diag, clé USB retirée : `power-on` 23:30:22, connexion perdue
  à +29 s, puis connexion acceptée sans réponse. **La surdité vient du client insistant** (requête
  toutes les 0,5 s, reconnexion toutes les 0,2 s pendant la relance de l'interface), pas de la
  v1.2.14 ni de la clé. e8 (2 s / 1,5 s) passait sur la v1.2.12.
- Extinction / allumage à la télécommande (23:34) : toujours sourd. Menu Réseau : sans effet
  (22:51). Seul un redémarrage du MCU en sort (reflash constaté ; secteur à confirmer).
- Mécanisme inconnu. Pour le lire : la RAM d'origine est réinitialisée au démarrage, seul le haut
  de la RAM (anneau 0x2001c000) survit à un reflash ; il faudrait une image diag qui recopie chaque
  seconde l'état utile (file des requêtes 0x2000a6a8, tampon de réception 0x20009eb0, dff2) vers
  le haut de la RAM, puis reflasher pour le relire.
- À faire : valider la v1.2.14 avec Home Assistant comme client ; mécanisme de la surdité.

### v1.2.14-diag avec Home Assistant (2026-11-16 23:56 → 2026-11-17 00:05) : correctif insuffisant

- Tour 1 (allumage HA 23:56, volume manipulé) : tenu. Journal : `08040b00 = 2`, écriture du port
  **non acquittée** à la même seconde, seconde écriture 2 s après (acquittée), HA reconnecté aussitôt.
- Tour 2 (allumage 00:02) : volume OK quelques fois puis indisponible, port refusé. Journal :
  `08010000 ← 0` 00:02:26, `← 1` +3 s, `08040b00 = 2` +13 s, **une seule écriture du port**
  (acquittée) +15 s, abonnement 08090200, puis rien. Port mort après une seule écriture : la
  « seconde écriture » n'est pas la cause, l'attente de 20 s est retirée.
- Port rouvert par le menu Réseau (00:05:59), comme à 22:28.

### Supprimer la reconfiguration à l'allumage : essai par debug-poke (00:10) → v1.2.15-diag

- Pas d'allumage FUN_080481d8 (de9c bit 0) : `e232 != 0` → FUN_0802f088(0), ded4 = 0x177,
  FUN_08074eac (initialisation), e232 = 1 ; `e232 == 0` → FUN_080478fc, ded4 = 0.
- Essai (v1.2.14-diag, client à 2 s) : `power-off`, `power-full-off`, `power-on`, puis lecture
  toutes les 2 à 4 s et remise à zéro de dec8 / decc / ded4 : à +2,2 s decc = 0x313 (remis à 0),
  à +5,1 s dec8 = 0x2cd (remis à 0), plus rien ensuite ; e232 et df86 restent à 0.
  **Aucune coupure en 90 s, aucune réponse perdue.**
- **v1.2.15-diag** (sha256 8d369ad5…1a5f24, non flashée) : `portguard` garde la garde « client
  connecté » et l'oubli du client à la relance de l'interface ; en plus, marque `0x2001ff10 =
  "PTOK"` posée quand l'écriture du port est acquittée, effacée par le tick pendant une extinction
  profonde (armée ou en cours) ; tant qu'elle est posée, le tick 1 s remet dec8 et decc à zéro.
  Suite 281/281. Le menu Réseau (autre chemin) reste le moyen de rouvrir un port.
- À vérifier sur matériel : allumage depuis l'éteint avec HA (plus de coupure à +30 s), démarrage
  à froid, `power-full-off deep` puis allumage (la reconfiguration doit avoir lieu).

### v1.2.15-diag sur matériel (00:25 → 00:36) puis v1.2.16-diag

- Allumage depuis l'éteint, client à 2 s (00:26:38) : 100 s sans coupure ; journal : ni écriture de
  08010000 ni de 08090100 après l'allumage, seulement `NOTIF 09040300`. Marque = "PTOK".
- Même scénario avec Home Assistant (00:31) : pas d'indisponible, volume OK, image présente.
- **Démarrage à froid (secteur 10 s, 00:33) : module absent du réseau** (ni ping ni ARP après
  3 min). La marque posée sur l'accusé d'écriture du port arrive avant que le module soit sur le
  réseau, et dec8 / decc servent aussi à finir sa configuration au démarrage.
- Lecture : le pas d'allumage FUN_080481d8 met lui-même `e2a8 = 1` (0x08048362), `dec8 = 0x32`,
  `decc = 0` ; FUN_08047a1c (extinction complète) met aussi `e2a8 = 1` (0x08047d9c) et `e232 = 0`.
  **À chaque allumage depuis l'éteint, l'état « client » est donc faux (1 alors que HA est
  connecté)** : la garde laisse passer l'écriture du port de la reconfiguration, qui coupe le
  client et ferme le port. C'est la cause des ports morts de 17:45, 20:33 et 00:02.
- **v1.2.16-diag** (sha256 c77ac57f…04ddf6) : la marque (nouveau mot "POK2", l'ancien
  survit au reflash) n'est posée par le tick que lorsque `e2a8 == 0`, c'est-à-dire qu'un client
  est connecté ; plus de détour du rappel des accusés. Suite 280/280.
- Vidéo : sortie HDMI perdue deux fois (22:47+, 00:10+), chaque fois après un allumage depuis
  l'éteint par le réseau avec mes clients de test ; présente à 00:31 avec HA. Non expliqué.

### v1.2.16-diag sur matériel (2026-11-17, 00:50 →)

- Flash seul : module toujours absent du réseau (état incomplet hérité de la v1.2.15 ; le flash
  ne redémarre pas le module).
- **Démarrage à froid** (secteur 10 s, télécommande, 00:53) : `get-status` répond 30 s après.
- **Allumage depuis l'éteint, client à 2 s** (00:54:35) : 100 s sans coupure ; journal : seulement
  `NOTIF 09040300` à l'allumage ; marque = "POK2".
- **Allumage depuis l'éteint avec Home Assistant** (00:58) : pas d'indisponible, volume et image OK.
- **Extinction profonde puis allumage** (`power-full-off deep` 01:00:21, Home Assistant déconnecté) :
  ping perdu 5 s après ; rallumage télécommande ~01:01:40, `get-status` répond à 01:02:07. Journal :
  la reconfiguration a bien lieu (`08010000 ← 0`, `← 1` 3 s après, `08040b00 = 2`, écriture du port
  deux fois à 3 s d'écart, client connecté 2 s plus tard) ; marque "POK2" reposée ensuite.
- Reste : démarrage à froid avec HA actif, surdité (client insistant), perte de la sortie vidéo,
  image de publication sans diag.
- **Démarrage à froid avec Home Assistant actif** (secteur 10 s, télécommande, ~01:08) : HA revient
  à « allumé » de lui-même, volume OK.

### Image de publication v1.2.0 (préparée le 2026-11-17, non flashée, non publiée)

- `out/AVR1610_patch1_v1.2.0.fw`, sha256 61fa5799…f10650. Features : getstatus, setvolume,
  bluetooth, keepsleep, push, osdgreen, surround, netoff, mute, sleeptimer, portguard, powerstate.
- Diffère de la v1.2.16-diag validée sur matériel par : les trois détours du journal, l'aiguillage
  des commandes (debug-peek / debug-poke en moins), les caves du diagnostic, la chaîne de version
  et la fin du tick portguard (enchaîne sur le tick veille au lieu de la trace). Tests :
  test_released_images.py. Suite 284/284.
- Avant publication : la flasher et refaire au moins allumage depuis l'éteint avec HA et démarrage
  à froid ; README à mettre à jour (tableau des versions, commande de build, problèmes connus).
