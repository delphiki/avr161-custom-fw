import struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from capstone.arm_const import ARM_OP_MEM, ARM_REG_PC
import os as _os  # chemins déduits de l'emplacement du script ; surcharge : AVR161_FW / AVR161_GHIDRA_DIR
_FW_DIR=_os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),'..'))
FW=(_os.environ.get("AVR161_FW") or _os.path.join(_FW_DIR,"AVR1610_USB(V002_20).fw"))
BASE=0x08000000
D=open(FW,"rb").read()
md=Cs(CS_ARCH_ARM, CS_MODE_THUMB|CS_MODE_LITTLE_ENDIAN); md.detail=True
def off(va): return va-BASE
def rd(va,n): return D[off(va):off(va)+n]
def u32(va): return struct.unpack_from("<I",D,off(va))[0]
def find_bytes(b,start=0):
    out=[];i=start
    while True:
        j=D.find(b,i)
        if j<0:break
        out.append(BASE+j);i=j+1
    return out
def xrefs(va): return find_bytes(struct.pack("<I",va))
def annot(p):
    if 0x08000000<=p<0x08600000:
        s=D[off(p):off(p)+24].split(b'\x00')[0]
        if len(s)>=2 and all(9<=c<127 for c in s): return "str "+repr(s.decode('latin1'))
        return f"->{p:#x}"
    if 0x20000000<=p<0x20030000: return f"RAM {p:#x}"
    return f"={p:#010x}"
def litref(ins):
    for op in ins.operands:
        if op.type==ARM_OP_MEM and op.mem.base==ARM_REG_PC:
            return ((ins.address+4)&~3)+op.mem.disp
    return None
def trace(start,end,ann=True):
    for ins in md.disasm(rd(start,end-start),start):
        if ins.address>=end: break
        t=litref(ins); note=""
        if t is not None:
            note=f"   ; [{t:#x}]={u32(t):#x} {annot(u32(t))}"
        print(f"  {ins.address:#08x}: {ins.mnemonic:9} {ins.op_str}{note}")
def scan_litrefs(start,end,targets):
    hits=[]
    for ins in md.disasm(rd(start,end-start),start):
        if ins.address>=end: break
        t=litref(ins)
        if t in targets: hits.append((ins.address,t))
    return hits
