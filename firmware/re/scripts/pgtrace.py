import struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from capstone.arm_const import ARM_OP_MEM, ARM_REG_PC
FW="/Users/julienvilletorte/PersonnalProjects/ampli/firmware/AVR1610_USB(V002_20).fw"
BASE=0x08000000; D=open(FW,"rb").read()
md=Cs(CS_ARCH_ARM, CS_MODE_THUMB|CS_MODE_LITTLE_ENDIAN); md.detail=True
def off(va): return va-BASE
def u32(va): return struct.unpack_from("<I",D,off(va))[0]

# Precompute every BL/BLX edge (caller_va -> target) over whole code region, once.
edges=[]          # (caller, target)
bytarget={}       # target -> set of callers
print("scanning BL edges...")
for va in range(0x08000000,0x080c0000,2):
    o=va-BASE
    if o+4>len(D): break
    for ins in md.disasm(D[o:o+4],va):
        if ins.mnemonic in("bl","blx"):
            try:
                t=int(ins.op_str.lstrip('#'),0)
                bytarget.setdefault(t,set()).add(va)
            except: pass
        break
print("edges done, targets:",len(bytarget))

def func_of(va):
    # crude: scan back up to 0x400 for a push {...,lr} prologue
    for a in range(va & ~1, (va&~1)-0x600, -2):
        o=a-BASE
        if o<0: break
        hw=struct.unpack_from("<H",D,o)[0]
        # push {...,lr}: 1011 0101 xxxxxxxx (b5xx) ; or 32-bit push.w (e92d ....)
        if (hw & 0xfe00)==0xb400 and (hw & 0x0100):  # push with lr
            return a
        if hw==0xe92d:  # stmdb sp!,{...} 32-bit push
            return a
    return None

def climb(target, depth=0, seen=None, maxd=6):
    if seen is None: seen=set()
    callers=bytarget.get(target,set())
    region=lambda v:"RESIDENT(<0x10000)" if v<0x08010000 else "app"
    for c in sorted(callers):
        f=func_of(c)
        tag=region(c)
        mark=" <<< RESIDENT PATH" if c<0x08010000 else ""
        print("   "*depth + f"<- bl@{c:#x} (func {f and hex(f)}) [{tag}]{mark}")
        key=(f or c)
        if depth<maxd and key not in seen and f:
            seen.add(key)
            climb(f, depth+1, seen, maxd)

for tgt,name in [(0x8005d56,"updater top (sets up state machine)"),
                 (0x8005e64,"state-machine run"),
                 (0x800aa9e,'file-open "!!ANAM SOFT!!"')]:
    print(f"\n===== reverse call graph of {name} {tgt:#x} =====")
    climb(tgt,0,set(),5)

# Also: does reset (0x800d36c) chain reach updater? print its direct bl targets
print("\n===== reset 0x800d36c direct calls =====")
for ins in md.disasm(D[off(0x800d36c):off(0x800d36c)+0x20],0x800d36c):
    if ins.mnemonic in("bl","blx","b.w","b"):
        print(f"  {ins.address:#x}: {ins.mnemonic} {ins.op_str}")
