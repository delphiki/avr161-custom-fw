import struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
from capstone.arm_const import ARM_OP_MEM, ARM_REG_PC
FW="/Users/julienvilletorte/PersonnalProjects/ampli/firmware/AVR1610_USB(V002_20).fw"
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
    if 0x40000000<=p<0x40030000: return f"PERIPH {p:#x}"
    return f"={p:#010x}"
# precompute BL callers
bytarget={}
for va in range(0x08000000,0x080c0000,2):
    o=va-BASE
    if o+4>len(D): break
    for ins in md.disasm(D[o:o+4],va):
        if ins.mnemonic in("bl","blx"):
            try: bytarget.setdefault(int(ins.op_str.lstrip('#'),0),set()).add(va)
            except: pass
        break
def callers(t): return sorted(bytarget.get(t,set()))
for t in (0x8005480,0x80057b4,0x8005be4,0x8005d0a,0x800d188):
    print(f"callers of {t:#x}: "+", ".join(f'{c:#x}' for c in callers(t)))
def dis(start,end,label):
    print(f"\n===== {label} {start:#x}..{end:#x} =====")
    for ins in md.disasm(D[off(start):off(end)],start):
        t=litref(ins); note=""
        if t is not None:
            try: note=f"   ; [{t:#x}]={u32(t):#x} {annot(u32(t))}"
            except: note=""
        if ins.mnemonic in ("bl","blx"):
            try:
                tg=int(ins.op_str.lstrip('#'),0); note+=f"   -> {tg:#x}"
            except: pass
        print(f"  {ins.address:#08x}: {ins.mnemonic:8} {ins.op_str}{note}")
# reset -> 0x800d188: what does the startup do, does it branch to resident main or app?
dis(0x800d188,0x800d280,"STARTUP 0x800d188 (from reset)")
# resident top loop entry
dis(0x8005480,0x8005540,"resident top 0x8005480")
