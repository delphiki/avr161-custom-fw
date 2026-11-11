#!/usr/bin/env python3
"""Updater IAP : primitives flash STM32, orchestrateurs qui les appellent,
et le flag de gate d'update (0x2000717d) ecrit/lu par du code RESIDENT.

Recree les scans inline de la session (voir ../NOTES.md "DISSECTION UPDATER IAP").
Deps : capstone. Lancer : python3 fw_iap.py
"""
import os, struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from capstone.arm_const import ARM_OP_MEM, ARM_REG_PC
FW=os.path.join(os.path.dirname(__file__), "..", "..", "AVR1610_USB(V002_20).fw")
BASE=0x08000000
D=open(FW,"rb").read()
md=Cs(CS_ARCH_ARM, CS_MODE_THUMB|CS_MODE_LITTLE_ENDIAN); md.detail=True
def off(va): return va-BASE
def u32(va): return struct.unpack_from("<I",D,off(va))[0]
def litref(ins):
    for op in ins.operands:
        if op.type==ARM_OP_MEM and op.mem.base==ARM_REG_PC:
            return ((ins.address+4)&~3)+op.mem.disp
    return None

# Primitives IAP identifiees (cf. NOTES)
IAP={0x800ada4:"unlock",0x800adba:"lock",0x800adcc:"erase_sector",
     0x800ae4a:"program_word",0x800aeaa:"program_byte",0x800af54:"wait_ready"}

print("=== 1) cles de deverrouillage flash STM32F2 (localise le driver IAP) ===")
for key,lab in [(0x45670123,"FLASH_KEY1"),(0xCDEF89AB,"FLASH_KEY2"),(0x40023c10,"FLASH_CR")]:
    pat=struct.pack("<I",key);i=0;h=[]
    while True:
        j=D.find(pat,i)
        if j<0:break
        h.append(BASE+j);i=j+1
    print(f"  {lab} {key:#010x}: " + ", ".join(f'{x:#x}' for x in h[:6]))

print("\n=== 2) appelants des primitives IAP (= les 2 orchestrateurs de flash) ===")
callers={k:[] for k in IAP}
for va in range(0x08000000,0x080c0000,2):
    o=va-BASE
    if o+4>len(D): break
    for ins in md.disasm(D[o:o+4],va):
        if ins.mnemonic in("bl","blx"):
            try:
                t=int(ins.op_str.lstrip('#'),0)
                if t in callers: callers[t].append(va)
            except: pass
        break
for k,nm in IAP.items():
    print(f"  {nm:13} {k:#x}: " + ", ".join(f'{c:#x}' for c in callers[k]))

print("\n=== 3) flag de gate d'update 0x2000717d : qui l'ecrit (strb) / le lit (ldrb) ===")
POOLS=[]  # pool entries contenant l'adresse 0x2000717d
pat=struct.pack("<I",0x2000717d); i=0
while True:
    j=D.find(pat,i)
    if j<0: break
    if j<0xc0000: POOLS.append(BASE+j)
    i=j+1
for va in range(0x08000000,0x0800c000,2):
    o=va-BASE
    if o+4>len(D): break
    for ins in md.disasm(D[o:o+4],va):
        t=litref(ins)
        if t in POOLS and ins.mnemonic.startswith("ldr"):
            # instruction suivante = strb (ecrit) ou ldrb (lit) ?
            nxt=list(md.disasm(D[o+ins.size:o+ins.size+6], va+ins.size))
            k=nxt[0].mnemonic if nxt else "?"
            zone="RESIDENT" if va<0x08010000 else "APP"
            print(f"  {va:#x} [{zone}] ldr &flag ; suivant={k}")
        break
print("  -> ecrit a 0x8003db4 (strb #1) par la couche FAT RESIDENTE quand le fichier d'update")
print("     est detecte ; lu a 0x8005dae (gate). Jamais touche par l'app. cf. ../NOTES.md")
