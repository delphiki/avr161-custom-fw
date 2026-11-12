# AVR 161 — pilotage réseau & firmware custom

Rétro-ingénierie, outil de contrôle réseau et **firmware custom** pour un ampli
**Harman Kardon AVR 161 / 1610** (MCU STM32F205ZG, Thumb-2), sur réseau local.

> Ampli de récupération, modifié à ses risques par le propriétaire. Le firmware
> d'origine reste récupérable par USB (voir « Filet de sécurité »).

---

## Ce que ça fait

- **`ampli.py`** — pilote l'ampli par le réseau (port 10025, protocole XML HK) :
  power, volume, mute, source, Bluetooth, et — avec le firmware custom — **get-status**
  et **set-volume absolu**.
- **Patch #1** — firmware custom ajoutant 3 commandes réseau (détour + code-cave) :
  - `get-status` : renvoie volume / mute / source réels (le firmware stock ne les expose pas).
  - `set-volume <n>` : règle le volume à une valeur absolue (0..180).
  - `source-selection Bluetooth` : bascule Bluetooth **directe** (le stock n'a que la navigation menu ~9 s).

## Arborescence

```
ampli.py                         outil de pilotage réseau (+ get-status/set-volume)
tests/                           tests du client (parse, mapping dB)
firmware/
  AVR1610_USB(V002_20).fw        firmware STOCK V002.20 (6 Mio) — image de récupération
  re/NOTES.md                    toute la rétro-ingénierie (adresses justifiées)
  re/scripts/                    scripts d'analyse (capstone / pyghidra) + README
  ghidra/                        projet Ghidra annoté
  patches/
    DESIGN-patch1.md             document de conception du patch #1
    build_patch1.py              construit l'image patchée (keystone + capstone)
    patchlib.py / verifylib.py   harness build + vérification statique
    tests/                       tests statiques du patch
    testA-result.md              preuve de récupération USB (Test A)
    out/                         images générées (non versionné)
docs/superpowers/
  specs/… plans/…                design & plan d'implémentation
```

## Historique (ce qui a été fait)

1. **Détection & protocole** — ampli trouvé sur le LAN ; protocole réseau port 10025
   (HTTP+XML) rétro-conçu et prouvé en pilotant l'ampli (power/volume/mute/source).
2. **Rétro-ingénierie firmware** — image `.fw` analysée (capstone + Ghidra) : dispatcheur
   réseau, `build_reply`/`net_send`, variables d'état (volume/mute/source), fonctions de
   bascule de source dont `set_src_Bluetooth`.
3. **Dissection de l'updater** — format du `.fw`, machine à états de flash IAP, tables de
   layout. Conclusions : image **non signée, non checksummée** (écrite verbatim), MCU =
   **1 Mo**, **code-cave à `0x080E0000`** (zone réécrite). Chemin d'auto-update résident
   analysé → récupération par USB **sans SWD** possible.
4. **Conception & plan** — `DESIGN-patch1.md` (relu par un agent « builder ») + plan TDD.
5. **Harness** — build fidèle (round-trip identique au bit près) + vérif statique (capstone).
6. **Test A — preuve de récupération** (matériel) : flash d'un témoin réseau, confirmé en
   lisant le User-Agent de la réponse heart-alive (`Harman PATCH1…`), puis retour au stock
   (`Harman Kardon…`). **Cycle flash custom ↔ retour stock prouvé par USB.**
7. **Patch #1** — get-status, set-volume, Bluetooth direct (détour sur `cmd_dispatch` +
   cave). get-status **validé sur matériel** (heart-alive intact, `<para>vol,mute,src</para>`).
8. **Client** — `ampli.py` étendu (`status`, `set-volume`, `source bluetooth` direct).

Détails techniques exhaustifs : `firmware/re/NOTES.md`.

---

## Flasher le firmware

> ⚠️ Un flash est irréversible en cours de route : **ne coupe pas l'alimentation**
> pendant les ~10 min. Ampli de récup, risque assumé.

### Préparer la clé USB
1. Clé **FAT32**, racine propre.
2. Copier l'image à la racine, **nommée exactement** `AVR1610_USB(V002_20).fw` :
   - firmware **custom** : `firmware/patches/out/AVR1610_patch1.fw`
   - firmware **stock** (récupération) : `firmware/AVR1610_USB(V002_20).fw`

   (sous macOS : formatage `diskutil eraseDisk FAT32 AVRUPDATE MBRFormat /dev/diskN`,
   puis `cp … "/Volumes/AVRUPDATE/AVR1610_USB(V002_20).fw"` et `diskutil eject`.)

### Flasher sur l'ampli
1. Ampli allumé, clé sur le port USB **façade**.
2. **System Setup → Software Update → OK → « SYSTEM UPDATE CONTINUE »**.
3. ~10 min, l'ampli s'éteint puis se rallume (« UPGRADE SUCCESS »).

### Filet de sécurité (récupération)
Le bootloader/updater résident (64 Ko bas) **n'est jamais réécrit** : un flash d'app raté
reste récupérable en re-flashant le **stock** par USB (prouvé, cf. Test A). Pour un patch
qui casserait le boot précoce (pas le cas des features réseau), prévoir un **ST-Link SWD**.

---

## Utiliser `ampli.py`

```bash
./ampli.py ping                 # l'ampli répond ?
./ampli.py on | off | toggle    # alimentation
./ampli.py vol+ [n] | vol- [n]  # volume relatif (n crans)
./ampli.py mute [on|off]        # mute
./ampli.py source <nom>         # ex. TV, Disc, "Cable Sat", bluetooth
# --- firmware custom (patch #1) uniquement ---
./ampli.py status               # volume (dB) | mute | source
./ampli.py set-volume <0-180>   # volume absolu  (ou: set-volume -25db)
./ampli.py source bluetooth     # bascule Bluetooth directe
```

Adresse de l'ampli : variable d'environnement `AMPLI_HOST` (défaut `192.168.1.58`).

## Reconstruire le patch

```bash
cd firmware/patches
python3 -m venv .venv && ./.venv/bin/pip install keystone-engine capstone "setuptools<81" pytest
# (keystone nécessite la lib native : brew install keystone)
./.venv/bin/python -m pytest -q                     # tests statiques
./.venv/bin/python -c "import patchlib; from build_patch1 import build_patch1; \
  patchlib.save(build_patch1(patchlib.load_stock(), features={'getstatus','setvolume','bluetooth'}), 'out/AVR1610_patch1.fw')"
```

Le patch n'ajoute/modifie que la zone réécrite (`0x10000–0xFFFFF`) : un détour de 4 octets
sur `cmd_dispatch` + un code-cave à `0x080E0000`. Image **même taille, 1:1** avec le stock.
