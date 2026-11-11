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
