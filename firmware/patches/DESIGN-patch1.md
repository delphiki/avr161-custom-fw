# Conception — Patch #1 : commandes réseau (Bluetooth, get-status, set-volume)

Firmware cible : `AVR1610_USB(V002_20).fw` (AVR 161/1610, STM32F205ZG, 1 Mo flash).
Statut : **CONCEPTION — à valider avant tout build** (règle du projet : rien ne se
construit tant que ce document n'est pas approuvé).
Références RE : `../re/NOTES.md` (toutes les adresses y sont justifiées).

## Intention & pourquoi
Ajouter au firmware trois commandes réseau (port 10025) qui manquent ou sont lentes
aujourd'hui, en réutilisant au maximum le code prouvé, pour un premier patch à **risque
minimal** servant aussi à **valider la chaîne complète** build → clé USB → flash → test.

## Objectifs
1. **Bluetooth direct** : `source-selection para=Bluetooth` bascule en BT instantanément
   (aujourd'hui : seulement via navigation menu ~9 s).
2. **get-status** : nouvelle commande réseau renvoyant volume + mute + source réels.
3. **set-volume** : nouvelle commande réseau réglant le volume à une valeur absolue.

## Non-objectifs (ce patch)
- Pas de Zone 2 (hardware-impossible, cf. NOTES), pas d'AirPlay/CEC/surround (features ultérieures).
- Pas de modification de `heart-alive` (choix validé : get-status = commande séparée, zéro impact
  sur l'appli officielle).
- Pas de nouvelle routine d'application volume « raw » (on réutilise les pas prouvés).

## Contraintes (issues de la dissection updater, cf. NOTES)
- **Le code ajouté doit vivre dans la zone réécrite par l'USB : `0x10000–0xFFFFF`.**
  → Code cave retenu : **`0x080E0000` (128 Ko de `0xFF`, idx 11, offset fichier `0xE0000`).**
- Offset fichier = adresse flash − `0x08000000` (image 1:1). Écriture **verbatim**, **aucun
  checksum/signature** à recalculer.
- Thumb-2. Les détours remplacent quelques octets au point de hook par un saut vers le cave ;
  le cave exécute la logique + les instructions déplacées, puis revient.

## Mécanisme général : détour + cave
Deux points de détour (tous deux dans la zone réécrite), un seul cave (entrées multiples) :

- **Détour A — Bluetooth** : dans `source_selection_handler` (`0x0804f44a`).
- **Détour B — get-status + set-volume** : en tête de `cmd_dispatch` (`0x0804f328`).

---

## Feature 1 — Bluetooth direct
- **Hook** : chaîne source-selection dans `cmd_dispatch` (`0x0804f44a`), qui compare `para` (= `param_1+0x40`).
- **Logique ajoutée (cave)** : `if strcmp(para,"Bluetooth")==0 { <bascule BT>; return }`.
- **⚠️ Révisé (review #4)** : `set_src_Bluetooth` (`0x0801af34`) **ne pose PAS** le flag de switch lui-même.
  Il faut **répliquer la branche HomeNetwork** (BT est structurellement identique) :
  ```
  *(u8*)0x2000e1ab = 0x19;                 // g_src_switch_flag (= DAT_0804ffb4)
  set_src_Bluetooth();                     // 0x0801af34 (g_source_enum=0x11 + bt_module_activate)
  if (((*(u8*)0x2000ddd4 & 3) >> 1) != 0)  // flag power/zone (= DAT_0804ffb8)
      FUN_08018944();                      // post-step, comme la branche HomeNetwork
  ```
  → NE PAS se contenter de `bl set_src_Bluetooth` seul (laisserait l'état switch/OSD incohérent).
- **Risque** : faible. Structure identique à la branche HomeNetwork prouvée.
- **Test** : `./ampli.py source bluetooth` → bascule immédiate (vérif OSD + get-status).

## Feature 2 — get-status (nouvelle commande)
- **Hook** : `cmd_dispatch` `0x0804f328` (tête de la chaîne de dispatch ; r0 = nom de commande).
- **Logique ajoutée (cave)** : `if strcmp(cmd,"get-status")==0 { construire+envoyer l'état; return }`.
- **Lecture d'état** :
  - volume  = `*(u8*)0x2000e1b8` (volume live 0..180 ; = celui que pilote set-volume)
  - mute    = `(*(u8*)0x2000de40 >> 1) & 1`
  - source  = `*(u8*)0x2000e1ae` (enum ; 0x11=Bluetooth, etc.)
- **Émission** : formater un `para` compact (ex. `"<vol>,<mute>,<src>"` en décimal via `int2dec`
  0x0804fdd4 + concat), puis `build_reply(name,zone,para)` (`0x0804fe7c`) → `net_send` (`0x08087e0c`).
  Buffer sortant `0x2000a0b4`. Primitives dispo : strlen/strcat/strcmp/memset (cf. NOTES).
- **⚠️ Révisé (review #3) — étape OBLIGATOIRE omise** : `build_reply` n'émet le contenu `<zone>/<para>`
  que **si la RAM `0x2000cb1c` == "status_name"** (chaîne `0x80defc0`). Ce chemin est actuellement du
  CODE MORT (personne n'arme ce ctx). Sans ça, get-status renvoie une réponse **vide** (semble marcher
  mais ne porte aucun état). Le cave doit donc :
  ```
  sauver_ctx = *(ptr*)0x2000cb1c ;  *(ptr*)0x2000cb1c = "status_name" (0x80defc0) ;
  build_reply(name, zone, para) ; net_send(0x2000a0b4) ;
  *(ptr*)0x2000cb1c = sauver_ctx ;   // RESTAURER (ctx partagé avec heart-alive/bye-bye)
  ```
  Le handler réseau est séquentiel (set→use→restore dans notre appel) → pas de course. À confirmer :
  type exact de `0x2000cb1c` (pointeur de chaîne comparé par strcmp, cf. build_reply).
- **int2dec** écrit dans un buffer fixe `0x2000dee4` → **copier chaque résultat** avant l'appel suivant.
- **Risque** : faible une fois le ctx armé. Commande isolée ; restauration du ctx protège heart-alive.
- **Test** : `./ampli.py raw get-status` → réponse parsable ; recouper avec set-volume round-trip (cf. test).

## Feature 3 — set-volume (nouvelle commande, natif firmware)
- **Hook** : même détour B (`cmd_dispatch` `0x0804f328`).
- **Logique ajoutée (cave)** : `if strcmp(cmd,"set-volume")==0 { cible=atoi(para); régler; return }`.
- **Algorithme (réutilise les pas prouvés) — RÉVISÉ (review #5, anti-oscillation)** :
  ```
  cible = clamp(atoi(para), 0, 180)
  for (i=0; i<128; i++) {                         // borne dure anti-boucle infinie
      cur = *(u8*)0x2000e1b8
      if (cur == cible) break
      sens_avant = (cur < cible)
      if (sens_avant) vol_up()                    // FUN_0801b568 (0x0801b568)
      else            vol_down()                  // FUN_0801b8f0 (0x0801b8f0)
      nouv = *(u8*)0x2000e1b8
      if (nouv == cur) break                       // garde bloquante : le pas n'a pas bougé -> stop
      if ((nouv < cible) != sens_avant) break      // ⚠️ CROISEMENT/overshoot -> stop (anti-oscillation)
  }
  ```
  - **Pourquoi le croisement** : les pas font ±2 OU ±4 (variable). Pour une cible non alignée sur la grille,
    le simple « égalité » oscillerait (60→62→60…) en martelant HW+OSD 128 fois. On s'arrête dès qu'on
    **atteint OU dépasse** la cible (résultat au pas près, ±1 crans), sans thrashing.
  - Les pas appliquent déjà le volume au matériel **et** rafraîchissent l'OSD. Pas de code HW nouveau.
  - Para exprimé dans l'échelle interne 0..180 (mapping dB documenté côté client, non bloquant).
- **Gardes (review #5)** : les pas s'appliquent bien depuis le dispatch réseau — PROUVÉ empiriquement
  (`ampli.py vol+` fonctionne déjà). En fonctionnement normal (ampli allumé, hors menu) les gardes passent ;
  si bloqué, la boucle sort via « pas n'a pas bougé ».
- **Risque** : faible-moyen. Réutilise les pas prouvés ; boucle bornée + anti-oscillation + anti-blocage.
  `para` dispo au hook (= `param_1+0x40`, résolu).
- **Test** : `./ampli.py raw set-volume 60` → volume cible ; recouper get-status + OSD.

---

## Plan build → flash → test → récupération
1. **Build** : assembler les détours + le cave, patcher les octets aux offsets fichier correspondants,
   garder le reste identique. Produire `AVR1610_USB(V002_20)_patch1.fw` (même taille, 1:1).
2. **Vérif statique** : re-désassembler les zones patchées + diff vs stock (seuls les octets voulus changent) ;
   confirmer que tout le code ajouté est dans `0x10000–0xFFFFF`.
3. **Filet AVANT tout flash** : valider empiriquement la récupération USB (clé **stock** + power-cycle sur
   ampli sain → ré-update sans menu ?). Cf. NOTES « CHEMIN D'AUTO-UPDATE AU BOOT ».
4. **Flash** : zip → clé USB FAT → menu Software Update (ou auto). ~10 min, power-cycle auto.
5. **Test** : les 3 commandes ci-dessus. Pour le volume, critère d'acceptation = **round-trip
   `set-volume N` → `get-status`** (les deux lisent/pilotent 0x2000e1b8 → cohérents). L'OSD (0x2000e213,
   octet d'affichage distinct) sert de recoupement **approximatif** seulement (review #6).
6. **Récupération si besoin** : re-flasher le `.fw` **stock** par USB (filet résident) ; SWD en recours.
   ⚠️ voir « Risque brick » ci-dessous : ce filet n'est PAS prouvé pour le cas app-cassée.

## Risques & mitigations
- **Brick (review #1 — à trancher par le propriétaire)** : le bootloader/updater résident (64 Ko bas) n'est
  jamais réécrit → il survit à un flash d'app raté. MAIS le « filet re-flash USB » n'est PAS prouvé pour le
  cas qui compte vraiment — **une app cassée** : le test de l'étape 3 (clé stock sur ampli SAIN) ne l'exerce
  pas, et NOTES signale que la confirmation « SYSTEM UPDATE CONTINUE / Press OK » est référencée par l'APP
  (0x8075xxx), pas par le résident. Si le flash USB au boot exige ce OK applicatif, une app cassée n'est PAS
  récupérable par USB — exactement le cas à couvrir.
  → **Décision prise : option (b)** — prouver le filet par RE + test dédié.
  **RE faite (cf. NOTES "APPROFONDISSEMENT #1")** : le moteur de flash résident s'arme sur **simple détection
  du fichier** (`*0x2000717d` posé par la FAT résidente), **indépendamment de l'app** — qui n'écrit jamais ce
  flag. Le "Press OK" applicatif est de l'affichage, pas un verrou. ⇒ Récupération autonome, **confiance haute**.
  Résidu : un patch cassant le **boot précoce** pourrait crasher la boucle résidente avant le poll USB → non
  récupérable. **Ce patch ne touche pas le boot** (hooks réseau + cave, zone 0x4f3xx/0xE0000), donc hors de ce cas.
  **Test A (preuve empirique, à faire avant le vrai patch)** : flasher un défaut OSD cosmétique observable
  (zone app), vérifier boot+défaut, puis clé **stock** + power-cycle → le défaut disparaît = récup auto prouvée.
- **`para` au point de hook** : `source_selection_handler` lit déjà `para` ; pour get-status/set-volume il
  faut confirmer l'accès à `para` au niveau de `cmd_dispatch` (item ouvert #1).
- **Gardes des pas volume** : la boucle set-volume s'arrête si un pas ne bouge plus → pas de blocage.
- **Authenticité du stock** : recoupement multi-miroirs recommandé (une seule source connue à ce jour,
  cf. échange GitHub `lansinghd/Harman-Kardon_AVR_Firmware`).

## Items ouverts (à finaliser en phase plan/implémentation, pas des bloqueurs)
1. ~~Buffer `para`~~ **RÉSOLU (review #2)** : struct commande `nom@+0x00, zone@+0x20, para@+0x40` ;
   `para = param_1+0x40` au point de hook `cmd_dispatch`. Hook viable.
2. **Points de détour précis** : octets exacts déplacés à `0x804f328` (et dans la chaîne source `0x804f44a`)
   + séquence de retour / équilibrage pile. À faire à l'assemblage.
3. **Format de réponse get-status** : figer la convention `para` (ex. `"vol,mute,src"`).
4. **atoi** : réutiliser une routine existante ou en écrire une minimale dans le cave.
5. **Type de `0x2000cb1c`** : confirmer (pointeur de chaîne) pour armer/restaurer le ctx "status_name".
6. **Mapping dB** : documenter 0..180 ↔ dB côté client `ampli.py` (confort, non bloquant).

## Décidé (rappel)
- get-status = **commande séparée** (pas d'enrichissement heart-alive).
- set-volume = **handler firmware natif** (réutilise les pas prouvés, pas de routine raw).
- Cave = **0x080E0000**. Filet = **re-flash USB stock** (validé empiriquement avant de flasher custom).
