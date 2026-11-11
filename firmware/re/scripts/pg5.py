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
def callers(off):
    out=[]
    for r in rm.getReferencesTo(A(off)):
        f=fm.getFunctionContaining(r.getFromAddress())
        out.append((r.getFromAddress().getOffset(), f.getName() if f else "?"))
    return out
print("callers UNKNOWN_7 (0x8019528):", [(hex(a),n) for a,n in callers(0x8019528)])
print("callers UNKNOWN_11(0x80197a8):", [(hex(a),n) for a,n in callers(0x80197a8)])
def decC(addr):
    f=fm.getFunctionContaining(A(addr)); r=ifc.decompileFunction(f,120,mon)
    return f.getName(), (r.getDecompiledFunction().getC() if r.decompileCompleted() else "(échec)")
for addr in [0x801ab42, 0x801a6c4]:   # routing routines of UNKNOWN_11 and UNKNOWN_7
    nm,c=decC(addr); print(f"\n####### {nm} @ {addr:#x} #######"); print(c)
proj.close()
