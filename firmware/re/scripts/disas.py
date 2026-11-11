import struct
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_MODE_LITTLE_ENDIAN
FW="fw/x/2015-04-15 AVR 1610_USB_V002_20/AVR1610_USB(V002_20).fw"
BASE=0x08000000
d=open(FW,"rb").read()
def refs(va):
    pat=struct.pack("<I",va); out=[]; i=0
    while True:
        j=d.find(pat,i)
        if j<0: break
        out.append(BASE+j); i=j+1
    return out
# Find code that references the source-selection table area.
# The table of source strings sits ~0x804ffb0; find a pointer to the table region used as a base.
cands=set()
for va in range(0x804ffa8,0x8050010,4):
    for r in refs(va):
        if r < 0x804fe00 or r>0x8050010:  # referenced from elsewhere = likely code/literal pool
            cands.add((va,r))
print("refs into the table from outside:", sorted((hex(v),hex(r)) for v,r in cands)[:20])

md=Cs(CS_ARCH_ARM, CS_MODE_THUMB|CS_MODE_LITTLE_ENDIAN)
def dis(va, n=24):
    off=va-BASE
    code=d[off:off+n*2+8]
    print(f"\n--- disasm @ {va:#x} ---")
    for ins in md.disasm(code, va):
        print(f"  {ins.address:#08x}: {ins.mnemonic:8} {ins.op_str}")
        n-=1
        if n<=0: break
# disassemble around the first external reference site (a literal pool is near code)
seen=set()
for v,r in sorted(cands):
    base_site = r & ~1
    if base_site in seen: continue
    seen.add(base_site)
    # the ref 'r' is a literal (pointer stored in code's constant pool); disassemble a bit before it
    dis(base_site-0x2c, 22)
    if len(seen)>=2: break
