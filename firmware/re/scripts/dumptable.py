import struct
FW="fw/x/2015-04-15 AVR 1610_USB_V002_20/AVR1610_USB(V002_20).fw"
BASE=0x08000000
d=open(FW,"rb").read()
def s_at(off,maxlen=40):
    e=off
    while e<len(d) and d[e] not in (0,) and e-off<maxlen: e+=1
    return d[off:e].decode("latin1").rstrip()
# Walk the pointer region and resolve each 4-byte LE pointer into 0x080xxxxx to its string
def dump(start_va, end_va):
    print(f"--- table {start_va:#x}..{end_va:#x} ---")
    for va in range(start_va, end_va, 4):
        off=va-BASE
        p=struct.unpack_from("<I",d,off)[0]
        if 0x08000000<=p<0x08600000:
            tgt=p-BASE
            txt=s_at(tgt)
            # only show entries whose target is a plausible ascii string
            if txt and all(31<ord(c)<127 for c in txt[:3] or 'x'):
                print(f"  [{va:#08x}] -> {p:#08x}  {txt!r}")
            else:
                print(f"  [{va:#08x}] -> {p:#08x}  (non-str)")
        else:
            print(f"  [{va:#08x}] = {p:#010x}")
dump(0x804fe50, 0x8050010)
