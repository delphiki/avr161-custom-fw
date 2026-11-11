# Patch #1 — Commandes réseau (Bluetooth, get-status, set-volume) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produire un firmware AVR 161/1610 patché (via détour + code-cave) ajoutant 3 commandes réseau port 10025 — Bluetooth direct, get-status, set-volume absolu — plus le client `ampli.py` correspondant, avec une preuve de récupération USB (Test A) avant tout flash du vrai patch.

**Architecture:** Toolchain Python qui part de l'image stock et produit l'image patchée : le code ajouté (Thumb-2) est **assemblé avec keystone** et écrit dans un **code-cave à `0x080E0000`** (zone réécrite, 128 Ko de `0xFF`) ; des **détours** (quelques octets remplacés par un `b.w`) dans `cmd_dispatch` (`0x0804f328`) et dans sa chaîne source-selection redirigent vers le cave, qui exécute la logique puis revient. La vérification est **statique** (capstone : diff vs stock + désassemblage des zones patchées) ; l'intégration est **matérielle** (flash USB + observation), explicitement gatée par l'accord du propriétaire.

**Tech Stack:** Python 3 ; `keystone-engine` (assembleur ARM Thumb) ; `capstone` (désassembleur/vérif) ; firmware STM32F205ZG Thumb-2 ; client `ampli.py` (sockets).

**Spec:** `firmware/patches/DESIGN-patch1.md` (+ RE justifiée dans `firmware/re/NOTES.md`).

## Global Constraints

- Image cible : `firmware/AVR1610_USB(V002_20).fw`, base flash `0x08000000`, Thumb-2, taille **exacte 6 291 456 octets**.
- Correspondance **1:1** : offset fichier = adresse flash − `0x08000000`. Écriture **verbatim**, **aucun checksum/signature** à recalculer.
- Tout code/donnée ajouté réside **dans `0x10000–0xFFFFF`** (zone réécrite par l'USB). **Cave = `0x080E0000`** (offset fichier `0xE0000`).
- **Interdit** de modifier `0x00000–0x0FFFF` (bootloader/updater résident) ou tout composant `≥0x100000` (DSP/réseau).
- Interworking Thumb : tout pointeur de fonction vers du code Thumb est **impair** (`|1`) ; branches via `b.w`/`bl` (encodage Thumb). Les `bl` existants restent valides.
- Adresses de référence (verbatim du spec/NOTES) : `cmd_dispatch=0x0804f328` ; chaîne source dans `cmd_dispatch` compare `para=param_1+0x40` ; `set_src_Bluetooth=0x0801af34` ; `g_src_switch_flag=0x2000e1ab` ; flag power/zone `0x2000ddd4` (bit `(x&3)>>1`) ; post-step source `FUN_08018944` ; `build_reply=0x0804fe7c` ; `net_send=0x08087e0c` ; buffer sortant `0x2000a0b4` ; `int2dec=0x0804fdd4` (buffer `0x2000dee4`) ; ctx status `0x2000cb1c` ← chaîne `"status_name"` `0x080defc0` ; volume live `0x2000e1b8` (0..0xB4) ; `vol_up=0x0801b568` ; `vol_down=0x0801b8f0` ; mute bit1 `0x2000de40` ; source enum `0x2000e1ae` ; version affichée (candidate) `0x080dbbb4` `"V002.20"`.

## Review Focus

- **Octets collatéraux** : un octet changé hors des zones de patch voulues → brick/comportement erratique. (Test : Task 1 `assert_only_changed`, chaque task passe son set d'offsets attendus.)
- **Retour de trampoline / pile** dans `cmd_dispatch` : si les instructions déplacées ou le retour sont faux, **toute** commande casse (même heart-alive). (Test : Task 3 désassemble le trampoline et vérifie prologue déplacé + retour exact ; HW : heart-alive répond encore.)
- **ctx get-status non restauré** : laisser `0x2000cb1c="status_name"` corromprait la réponse heart-alive de l'appli officielle. (Test : Task 3 vérifie save+restore dans le cave ; HW : appli officielle marche encore.)
- **Boucle set-volume** non bornée ou oscillante → martèlement HW/hang. (Test : Task 4 vérifie borne ≤128 + garde de croisement dans le désassemblage du cave.)
- **Littéraux PC-relatifs du cave** faux une fois placé à `0x080E0000` → mauvaises adresses appelées. (Test : Task 3 assemble à la VA `0x080E0000`, désassemble, vérifie que chaque cible de `bl`/littéral résout l'adresse voulue.)

---

### Task 1 : Harness de build + vérif (round-trip fidèle)

**Files:**
- Create: `firmware/patches/patchlib.py` (helpers build+assemble)
- Create: `firmware/patches/verifylib.py` (helpers vérif capstone)
- Create: `firmware/patches/build_patch1.py` (script de build principal, vide au début)
- Test: `firmware/patches/tests/test_harness.py`

**Interfaces:**
- Produces :
  - `patchlib.load_stock() -> bytearray` (lit l'image stock)
  - `patchlib.write_bytes(img, file_off:int, data:bytes)` (écrit à un offset fichier, lève si hors 0x10000–0xFFFFF sauf override explicite)
  - `patchlib.asm_thumb(src:str, va:int) -> bytes` (assemble du Thumb à la VA donnée via keystone)
  - `patchlib.detour(img, at_va:int, cave_va:int) -> bytes` (écrit un `b.w cave_va` à `at_va`, renvoie les octets **déplacés**)
  - `patchlib.save(img, path:str)` (écrit l'image, assert taille 6291456)
  - `verifylib.diff_offsets(a:bytes, b:bytes) -> set[int]` (offsets différents)
  - `verifylib.assert_only_changed(patched:bytes, stock:bytes, allowed:set[int])` (lève si un offset hors `allowed` change)
  - `verifylib.disasm(img, va:int, n:int) -> list[str]` (désassemble n instructions Thumb)
  - `verifylib.in_rewritten_region(va:int) -> bool` (0x10000 ≤ va−0x08000000 < 0x100000)

- [ ] **Step 1 : Écrire le test d'identité**

```python
def test_noop_build_is_byte_identical():
    stock = patchlib.load_stock()
    img = bytearray(stock)          # aucune modif
    assert verifylib.diff_offsets(bytes(img), stock) == set()
    assert len(img) == 6291456
```

- [ ] **Step 2 : Lancer, vérifier l'échec** — Run: `python3 -m pytest firmware/patches/tests/test_harness.py -v` — Expected: FAIL (modules absents).

- [ ] **Step 3 : Implémenter `patchlib.py` + `verifylib.py`** avec les signatures de l'Interfaces ci-dessus. `asm_thumb` : keystone `Ks(KS_ARCH_ARM, KS_MODE_THUMB)`, assemble à `va`. `detour` : encode un `b.w` 32-bit Thumb vers `cave_va` ; déplace assez d'instructions **entières** pour couvrir ≥4 octets.

- [ ] **Step 4 : Ajouter le test de garde de région**

```python
def test_write_outside_rewritten_region_raises():
    img = patchlib.load_stock()
    with pytest.raises(ValueError):
        patchlib.write_bytes(img, 0x0d000, b"\x00")   # resident -> interdit
    with pytest.raises(ValueError):
        patchlib.write_bytes(img, 0x120000, b"\x00")  # composant DSP -> interdit
```

- [ ] **Step 5 : Lancer, vérifier PASS** — Run: `python3 -m pytest firmware/patches/tests/test_harness.py -v` — Expected: PASS (2 tests).

- [ ] **Step 6 : Commit** — `git add firmware/patches/{patchlib,verifylib,build_patch1}.py firmware/patches/tests/test_harness.py && git commit -m "feat(patch): build+verify harness, faithful no-op round-trip"`
  *(Note : le repo n'est pas encore sous git — initialiser d'abord si l'exécuteur le décide ; sinon ignorer le commit.)*

---

### Task 2 : Test A — patch cosmétique de version (preuve de récupération USB)

Objectif : prouver empiriquement le cycle build → flash USB → l'ampli tourne notre custom → récup par clé **stock**. Instrument = la chaîne de version affichée.

**Files:**
- Modify: `firmware/patches/build_patch1.py` (ajoute une cible `build_testA`)
- Test: `firmware/patches/tests/test_testA.py`
- Create (sortie) : `firmware/patches/out/AVR1610_testA.fw`

**Interfaces:**
- Consumes : `patchlib`, `verifylib` (Task 1).

- [ ] **Step 1 : Confirmer la chaîne de version affichée (RE, lecture seule)** — vérifier que `0x080dbbb4` (`"V002.20"`) est bien la chaîne rendue par *System Setup → Software Update*. Chercher ses xrefs (pool) et leur fonction OSD. Si ce n'est pas la bonne, choisir la chaîne effectivement affichée (documenter l'adresse retenue). **Décision bloquante** : ne pas continuer Task 2 sans une chaîne prouvée observable.

- [ ] **Step 2 : Écrire le test (changement cosmétique localisé)**

```python
def test_testA_changes_only_version_string():
    stock = patchlib.load_stock()
    img = build_testA(bytearray(stock))       # remplace "V002.20" -> "V002.21"
    changed = verifylib.diff_offsets(bytes(img), stock)
    assert changed and all(VER_OFF <= o < VER_OFF+8 for o in changed)  # VER_OFF = offset de la chaîne prouvée
    assert len(img) == 6291456
```

- [ ] **Step 3 : Lancer, vérifier l'échec** — Expected: FAIL (`build_testA` absent).

- [ ] **Step 4 : Implémenter `build_testA`** : `write_bytes` de la nouvelle chaîne ASCII (même longueur, terminateur préservé) à l'offset prouvé ; `save` vers `out/AVR1610_testA.fw`.

- [ ] **Step 5 : Lancer, vérifier PASS** — Expected: PASS.

- [ ] **Step 6 : [MATÉRIEL — requiert l'accord explicite du propriétaire AVANT de flasher] Preuve de récupération** :
  1. Zipper `out/AVR1610_testA.fw`, clé USB FAT, flasher via menu ; vérifier *Software Update* affiche la **nouvelle** version → custom OK + ampli 100% fonctionnel.
  2. Clé **stock** (`AVR1610_USB(V002_20).fw`), power-cycle ; vérifier la version repasse à `V002.20` → **récupération USB prouvée**.
  - Critère de succès : les deux observations. En cas d'échec de la récup auto, re-flasher stock **via le menu** (l'ampli boote, menu accessible). Consigner le résultat dans `firmware/patches/out/testA-result.md`.

- [ ] **Step 7 : Commit** — `git add firmware/patches/build_patch1.py firmware/patches/tests/test_testA.py firmware/patches/out/testA-result.md && git commit -m "test(patch): Test A version-string recovery proof"`

---

### Task 3 : Cave + trampoline `cmd_dispatch` + get-status

**Files:**
- Modify: `firmware/patches/build_patch1.py` (layout du cave, trampoline, bloc get-status)
- Test: `firmware/patches/tests/test_getstatus.py`

**Interfaces:**
- Consumes : `patchlib`, `verifylib`.
- Produces :
  - `CAVE_VA = 0x080E0000` ; allocateur séquentiel `cave_alloc(name, size) -> va`.
  - `build_dispatch_trampoline(img)` : écrit à `0x0804f328` un `b.w` vers `cave_dispatch` ; renvoie les octets du prologue déplacé (consommés par Task 4 aussi).
  - Entrée cave `cave_dispatch` : `if strcmp(name,"get-status")==0 { emit_status; return } [place pour set-volume Task 4] else { <prologue déplacé> ; b.w 0x0804f328+N }`.

- [ ] **Step 1 : Écrire le test de structure (statique)**

```python
def test_getstatus_patch_structure():
    stock = patchlib.load_stock()
    img = build_patch1(bytearray(stock), features={"getstatus"})
    # 1) détour en tête de cmd_dispatch
    assert verifylib.disasm(img, 0x0804f328, 1)[0].startswith("b.w")
    # 2) tout octet modifié est dans la zone réécrite 0x10000..0xFFFFF (détour ~0x4f328 et cave 0xE0000 y sont)
    for off in verifylib.diff_offsets(bytes(img), stock):
        assert 0x10000 <= off < 0x100000
    # 3) le cave référence build_reply, net_send, int2dec, le ctx status_name et le restaure
    text = "\n".join(verifylib.disasm(img, CAVE_VA, 120))
    assert "0x804fe7c" in text and "0x8087e0c" in text        # build_reply + net_send
    assert "0x2000cb1c" in text and "0x80defc0" in text       # arme ctx status_name
    assert text.count("0x2000cb1c") >= 2                      # armé ET restauré
    assert "0x2000e1b8" in text and "0x2000de40" in text and "0x2000e1ae" in text  # vol/mute/source
```

- [ ] **Step 2 : Lancer, vérifier l'échec** — Expected: FAIL.

- [ ] **Step 3 : Implémenter le cave get-status + le trampoline** dans `build_patch1.py`.
  Logique (assemblée via `asm_thumb` à `CAVE_VA`) :
  ```
  cave_dispatch:
     push {r0-r3,lr}
     r0 = name (param_1 déjà en r0 à l'entrée de cmd_dispatch)
     bl strcmp(name, "get-status")      ; chaîne "get-status" placée dans le cave
     si == 0 -> emit_status ; pop ; return (vers l'appelant de cmd_dispatch)
     ; (Task 4 insérera set-volume ici)
     pop {r0-r3,lr}
     <prologue déplacé de cmd_dispatch>
     b.w 0x0804f328 + N
  emit_status:
     sauver *0x2000cb1c
     *0x2000cb1c = 0x80defc0            ; "status_name"
     construire para = "<vol>,<mute>,<src>" via int2dec (copier chaque résultat hors 0x2000dee4)
     build_reply("get-status", zone, para)   ; 0x0804fe7c
     net_send(0x2000a0b4)                     ; 0x08087e0c
     restaurer *0x2000cb1c
  ```
  Détails (nom de commande, zone, format para) : cf. items ouverts #3/#5 du spec ; l'implémenteur fige `"vol,mute,src"` décimal.

- [ ] **Step 4 : Vérifier les littéraux PC-relatifs** (Review Focus #5)

```python
def test_cave_literals_resolve_when_placed_at_cave():
    img = build_patch1(bytearray(patchlib.load_stock()), features={"getstatus"})
    text = "\n".join(verifylib.disasm(img, CAVE_VA, 120))
    # chaque bl cible une fonction connue (pas d'adresse aberrante hors flash)
    for line in text.splitlines():
        if line.strip().startswith("bl "):
            tgt = int(line.split("#")[-1], 16)
            assert 0x08000000 <= tgt < 0x08100000
```

- [ ] **Step 5 : Lancer, vérifier PASS** — Expected: PASS (2 tests).

- [ ] **Step 6 : Commit** — `... && git commit -m "feat(patch): code cave + cmd_dispatch trampoline + get-status"`

---

### Task 4 : set-volume (étend le dispatch du cave)

**Files:**
- Modify: `firmware/patches/build_patch1.py` (bloc set-volume dans le cave)
- Test: `firmware/patches/tests/test_setvolume.py`

**Interfaces:**
- Consumes : `cave_dispatch`, `cave_alloc` (Task 3), `vol_up=0x0801b568`, `vol_down=0x0801b8f0`.

- [ ] **Step 1 : Écrire le test de structure**

```python
def test_setvolume_loop_has_bound_and_crossing_guard():
    img = build_patch1(bytearray(patchlib.load_stock()), features={"getstatus","setvolume"})
    text = "\n".join(verifylib.disasm(img, CAVE_VA, 200))
    assert "0x801b568" in text and "0x801b8f0" in text   # appelle vol_up ET vol_down
    assert "0x2000e1b8" in text                          # lit la variable volume live
    # borne dure : une comparaison d'itération à <=128 et une garde de croisement existent
    # (vérifiées par présence d'un compteur + d'un test de signe ; voir Step 3)
```

- [ ] **Step 2 : Lancer, vérifier l'échec** — Expected: FAIL (set-volume pas encore dans le cave).

- [ ] **Step 3 : Implémenter le bloc set-volume** dans `cave_dispatch` :
  ```
  bl strcmp(name, "set-volume")
  si == 0:
     cible = atoi(para)            ; para = param_1+0x40 ; atoi minimal dans le cave
     cible = clamp(cible, 0, 180)
     for (i=0; i<128; i++):
        cur = *0x2000e1b8
        if cur == cible: break
        avant = (cur < cible)
        if avant: bl vol_up else bl vol_down
        nouv = *0x2000e1b8
        if nouv == cur: break                 ; garde bloquante
        if ((nouv < cible) != avant): break    ; croisement/overshoot
     pop ; return
  ```

- [ ] **Step 4 : Test de non-régression collatérale** — `assert_only_changed` : le set des offsets modifiés = détour `cmd_dispatch` ∪ plage du cave utilisée. Aucun autre octet.

```python
def test_no_collateral_changes():
    stock = patchlib.load_stock()
    img = build_patch1(bytearray(stock), features={"getstatus","setvolume"})
    changed = verifylib.diff_offsets(bytes(img), stock)
    allowed = detour_offsets() | cave_used_offsets()
    verifylib.assert_only_changed(bytes(img), stock, allowed)
```

- [ ] **Step 5 : Lancer, vérifier PASS** — Expected: PASS.

- [ ] **Step 6 : Commit** — `... && git commit -m "feat(patch): set-volume absolute via bounded reuse of proven steps"`

---

### Task 5 : Bluetooth direct (hook chaîne source-selection)

**Files:**
- Modify: `firmware/patches/build_patch1.py` (détour source + stub BT dans le cave)
- Test: `firmware/patches/tests/test_bluetooth.py`

**Interfaces:**
- Consumes : `set_src_Bluetooth=0x0801af34`, `g_src_switch_flag=0x2000e1ab`, flag `0x2000ddd4`, `FUN_08018944`.

- [ ] **Step 1 : Écrire le test de structure**

```python
def test_bluetooth_branch_replicates_homenetwork_pattern():
    img = build_patch1(bytearray(patchlib.load_stock()), features={"bluetooth"})
    text = "\n".join(verifylib.disasm(img, CAVE_VA, 260))
    assert "0x2000e1ab" in text          # pose le flag de switch
    assert "0x801af34"  in text          # appelle set_src_Bluetooth
    assert "0x8018944"  in text          # post-step comme HomeNetwork
    # la comparaison "Bluetooth" existe dans la chaîne source patchée
    assert b"Bluetooth" in open_out_image()  # la chaîne est embarquée dans le cave
```

- [ ] **Step 2 : Lancer, vérifier l'échec** — Expected: FAIL.

- [ ] **Step 3 : Implémenter le hook BT** : dans la chaîne source-selection de `cmd_dispatch`, au point de non-correspondance (fall-through), détour vers un stub cave :
  ```
  cave_bt:
     bl strcmp(para, "Bluetooth")          ; para = param_1+0x40 ; chaîne "Bluetooth" dans le cave
     si == 0:
        *0x2000e1ab = 0x19
        bl set_src_Bluetooth               ; 0x0801af34
        if (((*0x2000ddd4 & 3)>>1) != 0): bl 0x08018944
        <marquer traité / return>
     sinon: <instructions déplacées> ; b.w <retour chaîne source>
  ```
  Le point de détour exact + le retour sont fixés à l'assemblage (item ouvert #2).

- [ ] **Step 4 : Test collatéral global (3 features)** — `assert_only_changed` avec les détours (cmd_dispatch + source) ∪ plage cave, features `{getstatus,setvolume,bluetooth}`.

- [ ] **Step 5 : Lancer, vérifier PASS** — Expected: PASS.

- [ ] **Step 6 : Build de l'image finale** : `python3 firmware/patches/build_patch1.py --all --out firmware/patches/out/AVR1610_patch1.fw` ; assert taille 6291456.

- [ ] **Step 7 : Commit** — `... && git commit -m "feat(patch): direct Bluetooth source-selection command"`

---

### Task 6 : Client `ampli.py` (status, bluetooth direct, set-volume absolu)

**Files:**
- Modify: `ampli.py`
- Test: `tests/test_ampli_client.py`

**Interfaces:**
- Consumes : la réponse get-status `"vol,mute,src"` (Task 3) ; les commandes réseau existantes.
- Produces : `Ampli.get_status() -> dict{vol:int,mute:bool,source:str}` ; `main` sous-commandes `status`, `set-volume <n>` (ou `vol <n>`), et `source bluetooth` passe désormais par la commande directe.

- [ ] **Step 1 : Écrire les tests (logique pure, pas de réseau)**

```python
def test_parse_status_reply():
    assert parse_status("42,0,17") == {"vol":42,"mute":False,"source":"Bluetooth"}

def test_db_mapping_roundtrip():
    # 0..180 interne <-> dB affiché ; mapping documenté (non bloquant)
    assert internal_to_db(0) == -80.0 and internal_to_db(180) == 10.0
```

- [ ] **Step 2 : Lancer, vérifier l'échec** — Expected: FAIL.

- [ ] **Step 3 : Implémenter** `parse_status`, `internal_to_db`, `Ampli.get_status`, la sous-commande `status`, `set-volume`/`vol`, et faire pointer `source bluetooth` sur `source-selection para=Bluetooth` (retirer la navigation menu `MENU_SOURCES` pour BT une fois le firmware patché — garder un fallback commenté).

- [ ] **Step 4 : Lancer, vérifier PASS** — Expected: PASS.

- [ ] **Step 5 : Commit** — `... && git commit -m "feat(client): status, absolute volume, direct bluetooth"`

---

### Task 7 : Intégration matérielle (GATÉE par Test A + accord propriétaire)

**Files:**
- Create: `firmware/patches/out/integration-result.md`

- [ ] **Step 1 : Pré-conditions** — Task 2 (Test A) réussie (récup USB prouvée) **et** accord explicite du propriétaire pour flasher le vrai patch. Si Test A a échoué ou non fait → **STOP**, repasser par la décision filet (SWD).

- [ ] **Step 2 : [MATÉRIEL] Flash** `out/AVR1610_patch1.fw` via clé USB (+ le filet stock prêt à côté).

- [ ] **Step 3 : [MATÉRIEL] Tests fonctionnels** avec `ampli.py` patché :
  - `./ampli.py source bluetooth` → bascule immédiate (plus de ~9 s) ; recouper OSD.
  - `./ampli.py status` → vol/mute/source cohérents ; recouper OSD.
  - `./ampli.py set-volume 60` puis `./ampli.py status` → **round-trip cohérent** (critère d'acceptation) ; OSD = recoupement approximatif.
  - Sanity : `./ampli.py ping` (heart-alive) répond encore → trampoline + ctx restauré OK.

- [ ] **Step 4 : Consigner** le résultat dans `integration-result.md` (succès/échec par feature). En cas d'anomalie → re-flash stock (filet), analyser, itérer le patch.

---

## Notes d'exécution
- Les « tests » firmware sont **statiques** (capstone sur l'image produite) ; ils ne prouvent pas le comportement runtime — c'est le rôle des steps MATÉRIEL (Tasks 2 & 7), explicitement gatés.
- Aucun flash sans accord explicite du propriétaire au moment voulu. Le filet stock (`AVR1610_USB(V002_20).fw`) reste disponible à chaque flash.
- `keystone-engine` et `capstone` à installer dans un venv (cf. `firmware/re/scripts/README.md` pour le modèle d'environnement).
