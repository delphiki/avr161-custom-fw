#!/usr/bin/env python3
"""Format du paquet .fw AVR 161/1610 : en-tete, queue, carte de densite 64K,
en-tetes de composants, et tables de layout de l'updater (start/len/secteur).

Recree les analyses inline de la session (voir ../NOTES.md section "Format du paquet").
Deps : capstone (pour rien ici en fait, pur struct). Lancer : python3 fw_format.py
"""
import os, struct
FW=os.path.join(os.path.dirname(__file__), "..", "..", "AVR1610_USB(V002_20).fw")
BASE=0x08000000
D=open(FW,"rb").read()
def off(va): return va-BASE
def u32(va): return struct.unpack_from("<I",D,off(va))[0]

print(f"=== taille : {len(D)} octets ({len(D)/2**20:.0f} Mio) ===")
print("\n=== en-tete (table de vecteurs STM32) ===")
print(f"  SP initial  = {u32(0x08000000):#010x}  (attendu SRAM 0x2000xxxx)")
print(f"  reset       = {u32(0x08000004):#010x}  (attendu flash 0x080xxxxx, Thumb=impair)")

print("\n=== carte de densite par bloc de 64K (contenu vs padding 0xFF) ===")
BL=0x10000
for i in range(0,len(D),BL):
    b=D[i:i+BL]; ff=b.count(0xff); other=len(b)-ff-b.count(0)
    if other>100 or ff<BL:  # ne montre que les blocs avec du contenu
        bar='#'*(other*40//len(b))
        print(f"  0x{i:06x}  FF={ff:5d} other={other:5d} {bar}")

print("\n=== en-tetes de composants ===")
for base,lab in [(0x100000,"composant @0x100000 (DSP)"),(0x500000,"composant @0x500000")]:
    print(f"  --- {lab} ---")
    for r in range(base, base+0x40, 16):
        hexs=' '.join(f'{D[r+k]:02x}' for k in range(16))
        print(f"    {r:#08x}: {hexs}")

print("\n=== tables de layout updater (idx 0..11) ===")
print("  idx   start(0x800d0a8)  len(0x800d0dc)   secteur(0x800d324)")
for i in range(12):
    st=u32(0x800d0a8+4*i); ln=u32(0x800d0dc+4*i); sec=D[off(0x800d324)+i]
    zone="bootloader/updater (jamais reecrit)" if i<4 else "application (reecrit depuis fichier)"
    print(f"   {i:2}    {st:#010x}      {ln:#010x}     {sec:#04x}   {zone}")
