import pyghidra, re
pyghidra.start()
from ghidra.base.project import GhidraProject
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
import os as _os  # chemins déduits de l'emplacement du script ; surcharge : AVR161_FW / AVR161_GHIDRA_DIR
_FW_DIR=_os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),'../..'))
proj=GhidraProject.openProject((_os.environ.get("AVR161_GHIDRA_DIR") or _os.path.join(_FW_DIR,"ghidra")),"AVR161",True)
prog=proj.openProgram("/","AVR1610_USB(V002_20).fw",True)
fm=prog.getFunctionManager(); mem=prog.getMemory(); sp=prog.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
def u32(x): return mem.getInt(A(x)) & 0xffffffff
ifc=DecompInterface(); ifc.openProgram(prog); mon=ConsoleTaskMonitor()
# find functions in routing cluster that set the source enum (0x2000e1ae) to 0x11
hits=[]
for f in fm.getFunctions(True):
    ep=f.getEntryPoint().getOffset()
    if not (0x8018000<=ep<0x801b400): continue
    try:
        r=ifc.decompileFunction(f,60,mon)
        if not r.decompileCompleted(): continue
        c=r.getDecompiledFunction().getC()
    except Exception: continue
    # look for assignment of 0x11 / '\x11' to a DAT pointer that resolves to 0x2000e1ae
    for ln in c.splitlines():
        m=re.search(r'\*(DAT_[0-9a-fA-F]+)\s*=\s*(0x11|\'\\x11\'|17);', ln)
        if m:
            datname=m.group(1)
            datoff=int(datname.split('_')[1],16)
            try: tgt=u32(datoff)
            except Exception: tgt=None
            if tgt==0x2000e1ae:
                hits.append((f.getName(), ep, ln.strip()))
print("=== fonctions qui posent enum source = 0x11 (BLUETOOTH) ===")
for nm,ep,ln in hits:
    print(f"  {nm} @ {ep:#x} : {ln}")
if not hits: print("  (aucune trouvée dans la plage)")
proj.close()
