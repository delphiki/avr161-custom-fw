import pyghidra
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
# resolve the two enum pointers
print("ptr @0x0801b008 ->", hex(u32(0x0801b008)))   # routing enum
print("ptr @0x0805367c ->", hex(u32(0x0805367c)))   # display enum
# full enum->name map from display FUN_08052f80
ifc=DecompInterface(); ifc.openProgram(prog); mon=ConsoleTaskMonitor()
f=fm.getFunctionContaining(A(0x80531d0)); r=ifc.decompileFunction(f,120,mon)
c=r.getDecompiledFunction().getC()
import re
lines=c.splitlines()
print("\n== enum->name (display) ==")
cur=None
for ln in lines:
    m=re.search(r'==\s*(0x[0-9a-fA-F]+)\)', ln)
    if m: cur=m.group(1)
    if "osd_print" in ln and ("disp" in ln or "DAT_080536" in ln or "BLUETOOTH" in ln):
        s=ln.strip()
        print(f"   enum {cur} -> {s}")
proj.close()
