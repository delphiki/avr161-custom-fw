import struct
FW="fw/x/2015-04-15 AVR 1610_USB_V002_20/AVR1610_USB(V002_20).fw"
BASE=0x08000000
d=open(FW,"rb").read()
# exact param tokens from the official app + Bluetooth variants
toks=["Cable Sat","TV","Disc","DVR","Server","Radio","AUX","Game","USB","STB",
      "Audio","Media Server","iPod","Home Network","FM","AM","vTuner",
      "Sirius Radio","Pandora","Source A","Source B","Source C","Source D",
      "Bluetooth","BLUETOOTH","BT","source-selection","heart-alive"]
def find_all(needle):
    out=[]; i=0; b=needle.encode()
    while True:
        j=d.find(b,i)
        if j<0: break
        out.append(j); i=j+1
    return out
# map VA -> list of file offsets where a 4-byte LE pointer to VA appears
def ptr_refs(va):
    pat=struct.pack("<I",va); out=[]; i=0
    while True:
        j=d.find(pat,i)
        if j<0: break
        out.append(j); i=j+1
    return out
for t in toks:
    # prefer null-terminated occurrence
    offs=[o for o in find_all(t) if o+len(t)<len(d) and d[o+len(t)] in (0,0x20)]
    if not offs:
        print(f"{t!r:18} : (absent exact/null-term)"); continue
    line=f"{t!r:18} : {len(offs)} occ"
    # for first few occurrences, count pointer refs
    refinfo=[]
    for o in offs[:4]:
        va=BASE+o
        refs=ptr_refs(va)
        refinfo.append(f"@{va:#08x}->{len(refs)}ref"+(f"{[hex(BASE+r) for r in refs[:3]]}" if refs else ""))
    print(line+" | "+" ; ".join(refinfo))
