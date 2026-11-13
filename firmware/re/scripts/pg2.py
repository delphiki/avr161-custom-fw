import pyghidra
pyghidra.start()
from ghidra.base.project import GhidraProject
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
import os as _os  # chemins déduits de l'emplacement du script ; surcharge : AVR161_FW / AVR161_GHIDRA_DIR
_FW_DIR=_os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),'../..'))
proj=GhidraProject.openProject((_os.environ.get("AVR161_GHIDRA_DIR") or _os.path.join(_FW_DIR,"ghidra")),"AVR161",True)
prog=proj.openProgram("/","AVR1610_USB(V002_20).fw",True)
fm=prog.getFunctionManager(); sp=prog.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
ifc=DecompInterface(); ifc.openProgram(prog); mon=ConsoleTaskMonitor()
def dec(addr):
    f=fm.getFunctionContaining(A(addr))
    r=ifc.decompileFunction(f,90,mon)
    return f.getName(), r.getDecompiledFunction().getC() if r.decompileCompleted() else "(échec)"
import sys
for addr in [0x80561c4]:  # inside FUN_080553d0 display switch
    nm,c=dec(addr)
    print(f"===== {nm} (@{addr:#x}) =====")
    # print only lines mentioning BLUETOOTH / source enum / case values, trim huge output
    for ln in c.splitlines():
        if any(k in ln for k in ("BLUETOOTH","DAT_2000","switch","case","uVar","cVar","param","puVar")) or "DISP" in ln.upper():
            print(ln)
proj.close()
