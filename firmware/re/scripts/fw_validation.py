#!/usr/bin/env python3
"""Recherche de tout mecanisme d'integrite/signature dans le .fw :
constantes CRC, constantes crypto (hash/asymetrique), magics, modele, version.

Repond a la question "signe ou juste checksumme ?" (voir ../NOTES.md).
Conclusion de la session : PAS de CRC32, PAS de crypto asymetrique, PAS de hash
actif sur l'image -> contenu ecrit verbatim. Lancer : python3 fw_validation.py
"""
import os, struct
FW=os.path.join(os.path.dirname(__file__), "..", "..", "AVR1610_USB(V002_20).fw")
BASE=0x08000000
D=open(FW,"rb").read()
def hits(pat):
    out=[]; i=0
    while True:
        j=D.find(pat,i)
        if j<0: break
        out.append(BASE+j); i=j+1
    return out

print("=== constantes CRC (polynomes) ===")
for poly,lab in [(0xEDB88320,"CRC32 reflechi"),(0x04C11DB7,"CRC32 normal"),
                 (0x1021,"CRC16-CCITT"),(0x8408,"CRC16 reflechi")]:
    for e in (('<I','>I') if poly>0xffff else ('<H','>H')):
        h=hits(struct.pack(e,poly))
        print(f"  {lab:16} {e}: {len(h):4d} hits" + (f"  ex {h[0]:#x}" if h else ""))

print("\n=== constantes crypto (hash / signature) ===")
for c,lab in [(0x6a09e667,"SHA256 H0"),(0xbb67ae85,"SHA256 H1"),(0x67452301,"MD5/SHA1 A"),
              (0xefcdab89,"MD5/SHA1 B"),(0x428a2f98,"SHA256 K0")]:
    for e in ('<I','>I'):
        h=hits(struct.pack(e,c))
        if h: print(f"  {lab:12} {e}: {len(h)} -> " + ", ".join(f'{x:#x}' for x in h[:6]))
print("  (note : les blocs MD5-IV trouves sont des DONNEES DSP / non referencees,")
print("          pas un hash actif sur l'image. cf. ../NOTES.md)")

print("\n=== chaines crypto / lib ===")
import re
txt=D.decode('latin1')
found=set(re.findall(r'(RSA|ECDSA|SHA-?256|HMAC|mbedtls|wolfssl|openssl|-----BEGIN|signature|certificate)', txt, re.I))
print("  trouvees :", sorted(found) if found else "AUCUNE")

print("\n=== magics / modele / version ===")
for mg in (b"!!ANAM SOFT!!",b"AVR161",b"AVR1610",b"V002.20",b"harman",b"Harman Kardon AVR161/AVR1610"):
    h=hits(mg)
    print(f"  {mg.decode('latin1'):32}: {len(h)} -> " + ", ".join(f'{x:#x}' for x in h[:4]))
