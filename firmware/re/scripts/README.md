# Scripts d'analyse — firmware AVR 161/1610 V002.20

Scripts de rétro-ingénierie utilisés pendant la session. Les conclusions qu'ils
produisent sont consignées dans **`../NOTES.md`** (c'est la référence ; ces scripts
sont les outils qui l'ont alimentée et permettent de tout rejouer).

Cible analysée : `../../AVR1610_USB(V002_20).fw`. Les scripts déduisent ce chemin (et celui du
projet Ghidra `../../ghidra`) de leur propre emplacement : ils se lancent depuis n'importe quel
dossier. Pour viser d'autres fichiers, définir `AVR161_FW` et/ou `AVR161_GHIDRA_DIR`.

## ⚙️ Environnements requis (À RECRÉER)

Les venvs utilisés en session vivaient dans un dossier temporaire (scratchpad) et
**ont disparu**. Il faut les recréer une fois :

```bash
# 1) venv capstone (scripts purs désassemblage)
python3 -m venv venvcap && ./venvcap/bin/pip install capstone

# 2) venv pyghidra (scripts de décompilation via Ghidra)
python3 -m venv venvpg && ./venvpg/bin/pip install pyghidra
```

Pour les scripts **pyghidra** (`pg*.py`), exporter aussi, à chaque lancement :

```bash
export GHIDRA_INSTALL_DIR="/opt/homebrew/Cellar/ghidra/12.2/libexec"   # adapter si autre version
export JAVA_HOME="/opt/homebrew/opt/openjdk@25/libexec/openjdk.jdk/Contents/Home"
export PATH="$JAVA_HOME/bin:$PATH"
./venvpg/bin/python3 -I pgXXX.py
```

Les scripts pyghidra ouvrent le projet Ghidra annoté `../../ghidra/AVR161` (déjà présent).

## 📜 Scripts — par thème

### Format du paquet & validation (recréés, propres, autonomes — capstone/pur)
- **`fw_format.py`** — en-tête, carte de densité 64K, en-têtes de composants, tables de layout (start/len/secteur).
- **`fw_validation.py`** — scan CRC + crypto (hash/signature) + magics/modèle/version. Répond "signé ou pas ?".
- **`fw_iap.py`** — primitives IAP flash, appelants (orchestrateurs), flag de gate d'update 0x2000717d (écrit/lu, résident).

### Désassemblage capstone (boîte à outils)
- **`../fwre.py`** — helpers (xrefs, trace, litref, u32…). Importé par plusieurs scripts.
- `disas.py`, `dumptable.py`, `refscan.py` — dumps/xrefs ponctuels (phase protocole/BT).

### Décompilation Ghidra (pyghidra) — chaîne d'update
- `pgupd.py`, `pgupd2.py`, `pgupd3.py` — localisation + décompilation des fonctions d'update (strings de validation).
- `pgflash.py` — graveur flash + appelants.
- `pgorch.py` — orchestrateurs IAP (boucle erase/program).
- `pgresident.py` — **main() résident, driver update, gate** (le cœur : chemin d'auto-update au boot).
- `pgtrace.py`, `pgtrace2.py`, `pgboot.py` — graphe d'appels reset→updater, chemin de boot.

### Décompilation Ghidra — phase Bluetooth / protocole (historique)
- `pg.py`, `pg2.py`…`pg10.py`, `pgann.py` — itérations qui ont épinglé `set_src_Bluetooth=0x0801af34`
  et les fonctions de source. `pgann.py` = annotation du projet.

### Réseau (port 10025) — découverte protocole (historique, sans firmware)
- `hk.py`, `hk2.py`, `hk3.py`, `rc.py`, `probe.py`, `probe2.py` — sondes réseau ayant servi
  à découvrir le protocole live sur l'ampli (192.168.1.58:10025).

## Note
Scripts d'itération conservés tels quels (non nettoyés) pour traçabilité. En cas de
doute sur un résultat, c'est `../NOTES.md` qui fait foi.
