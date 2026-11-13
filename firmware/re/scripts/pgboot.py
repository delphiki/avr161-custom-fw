import struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from capstone.arm_const import ARM_OP_MEM, ARM_REG_PC
import os as _os  # chemins déduits de l'emplacement du script ; surcharge : AVR161_FW / AVR161_GHIDRA_DIR
_FW_DIR=_os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),'../..'))
FW=(_os.environ.get("AVR161_FW") or _os.path.join(_FW_DIR,"AVR1610_USB(V002_20).fw"))
BASE=0x08000000; D=open(FW,"rb").read()
md=Cs(CS_ARCH_ARM, CS_MODE_THUMB|CS_MODE_LITTLE_ENDIAN); md.detail=True
def off(va): return va-BASE
def u32(va): return struct.unpack_from("<I",D,off(va))[0]
def litref(ins):
    for op in ins.operands:
        if op.type==ARM_OP_MEM and op.mem.base==ARM_REG_PC:
            return ((ins.address+4)&~3)+op.mem.disp
    return None
def annot(p):
    if 0x08000000<=p<0x08600000:
        s=D[off(p):off(p)+28].split(b'\x00')[0]
        if len(s)>=3 and all(9<=c<127 for c in s): return "str "+repr(s.decode('latin1'))
        return f"->{p:#x}"
    if 0x20000000<=p<0x20030000: return f"RAM {p:#x}"
    return f"={p:#010x}"
def dis(start,end,label):
    print(f"\n===== {label} {start:#x}..{end:#x} =====")
    for ins in md.disasm(D[off(start):off(end)],start):
        t=litref(ins); note=""
        if t is not None:
            try: note=f"   ; [{t:#x}]={u32(t):#x} {annot(u32(t))}"
            except: note=""
        print(f"  {ins.address:#08x}: {ins.mnemonic:8} {ins.op_str}{note}")
# find all code refs (bl + state write) to state-machine step 0x8005e64 and state var 0x20007180
def find_bl(target):
    out=[]
    for va in range(0x08000000,0x080c0000,2):
        o=va-BASE
        if o+4>len(D): break
        for ins in md.disasm(D[o:o+4],va):
            if ins.mnemonic in("bl","blx"):
                try:
                    if int(ins.op_str.lstrip('#'),0)==target: out.append(va)
                except: pass
            break
    return out
for tgt in (0x8005e64,0x8005e6c):
    print(f"callers of state-step {tgt:#x}: "+", ".join(f'{c:#x}' for c in find_bl(tgt)))
# data refs (literal pool) to state var 0x20007180
pat=struct.pack("<I",0x20007180);i=0;poolrefs=[]
while True:
    j=D.find(pat,i)
    if j<0:break
    if j<0xc0000: poolrefs.append(BASE+j)
    i=j+1
print(f"\npool refs to state var 0x20007180: {len(poolrefs)} -> "+", ".join(f'{p:#x}' for p in poolrefs[:20]))
# reset / boot path
print("\n--- reset vector target ---", hex(u32(0x08000004)))
dis(0x0800d36c,0x0800d420,"RESET/boot head")
PY
