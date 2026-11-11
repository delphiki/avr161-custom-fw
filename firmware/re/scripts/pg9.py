import pyghidra
pyghidra.start()
from ghidra.base.project import GhidraProject
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
proj=GhidraProject.openProject("/Users/julienvilletorte/PersonnalProjects/ampli/firmware/ghidra","AVR161",True)
prog=proj.openProgram("/","AVR1610_USB(V002_20).fw",True)
fm=prog.getFunctionManager(); rm=prog.getReferenceManager(); sp=prog.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
ifc=DecompInterface(); ifc.openProgram(prog); mon=ConsoleTaskMonitor()
def decC(off):
    f=fm.getFunctionContaining(A(off)); r=ifc.decompileFunction(f,120,mon)
    return f.getName(), f.getEntryPoint().getOffset(), (r.getDecompiledFunction().getC() if r.decompileCompleted() else "(echec)")
print("== callers of FUN_0801af34 (BT routing) ==")
for r in rm.getReferencesTo(A(0x801af34)):
    f=fm.getFunctionContaining(r.getFromAddress())
    print(f"  from {r.getFromAddress()} in {f.getName() if f else '?'} @ {f.getEntryPoint() if f else ''}")
# decompile the likely leaf set_src (caller)
print("\n== decompile each caller ==")
seen=set()
for r in rm.getReferencesTo(A(0x801af34)):
    f=fm.getFunctionContaining(r.getFromAddress())
    if not f or f.getEntryPoint().getOffset() in seen: continue
    seen.add(f.getEntryPoint().getOffset())
    nm,ep,c=decC(f.getEntryPoint().getOffset())
    print(f"\n#### {nm} @ {ep:#x} ####")
    print(c)
proj.close()
