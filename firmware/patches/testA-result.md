# Test A — résultat (preuve de récupération USB sans SWD)

Instrument final : **testB** (témoin RÉSEAU), après que testA (nom OSD source) se soit
révélé un mauvais témoin (la chaîne affichée passe par une couche réglages, pas lue
directement du flash). testB change "Kardon"->"PATCH1" dans le User-Agent émis à chaque
heart-alive (chaîne 100% MCU, lue via le réseau).

## Observations matérielles (propriétaire)
- Flash testA : "DSP UPDATE" + "MCU UPDATE" + UPGRADE SUCCESS, reboot OK. "USB" inchangé (mauvais témoin).
- Flash testB : "OSD UPDATE" vu aussi, UPGRADE SUCCESS, reboot OK.

## Preuves réseau (lues par ampli via heart-alive)
- Après testB : User-Agent = `Harman PATCH1 AVR161/AVR1610`
  => nos octets MCU sont flashés ; mapping fichier↔flash = 1:1 CONFIRMÉ ; flash non-brickant.
- Après re-flash STOCK : User-Agent = `Harman Kardon AVR161/AVR1610`
  => RÉCUPÉRATION USB (sans SWD) PROUVÉE.

## Conclusion
Le cycle flash custom ↔ retour stock fonctionne entièrement par USB, pour tout patch
ne cassant pas le boot précoce (cas des features réseau du patch #1). Filet validé.
