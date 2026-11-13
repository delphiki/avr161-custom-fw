import os, pyghidra
pyghidra.start()
from ghidra.base.project import GhidraProject
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
import os as _os  # chemins déduits de l'emplacement du script ; surcharge : AVR161_FW / AVR161_GHIDRA_DIR
_FW_DIR=_os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),'../..'))
PROJ=(_os.environ.get("AVR161_GHIDRA_DIR") or _os.path.join(_FW_DIR,"ghidra"))
proj=GhidraProject.openProject(PROJ,"AVR161",True)
prog=proj.openProgram("/","AVR1610_USB(V002_20).fw",True)
fm=prog.getFunctionManager(); rm=prog.getReferenceManager()
sp=prog.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
mon=ConsoleTaskMonitor()
di=DecompInterface(); di.openProgram(prog)
def dec(off,tag=""):
    f=fm.getFunctionContaining(A(off))
    if not f: print(f"\n### no func @ {off:#x} {tag}"); return
    print("\n"+"="*72+f"\nFUNC {f.getName()} @ {f.getEntryPoint()} size={f.getBody().getNumAddresses()} {tag}\n"+"="*72)
    r=di.decompileFunction(f,90,mon)
    print(r.getDecompiledFunction().getC() if r and r.decompileCompleted() else "  <fail>")
# orchestrator functions that touch component offsets
for off,tag in [(0x800d0d8,"ref 0x100000 (near boot)"),
                (0x80b5971,"ref 0x100000 (DSP flash)"),
                (0x80b728d,"ref 0x500000"),
                (0x80b83cd,"ref 0x500000"),
                (0x80ad308,"caller of fwUpdEnabled (update entry?)")]:
    dec(off,tag)
proj.close()
