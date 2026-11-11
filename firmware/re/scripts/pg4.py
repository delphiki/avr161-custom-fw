import pyghidra
pyghidra.start()
from ghidra.base.project import GhidraProject
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
proj=GhidraProject.openProject("/Users/julienvilletorte/PersonnalProjects/ampli/firmware/ghidra","AVR161",True)
prog=proj.openProgram("/","AVR1610_USB(V002_20).fw",True)
fm=prog.getFunctionManager(); sp=prog.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
ifc=DecompInterface(); ifc.openProgram(prog); mon=ConsoleTaskMonitor()
def decC(addr):
    f=fm.getFunctionContaining(A(addr))
    r=ifc.decompileFunction(f,120,mon)
    return f.getName(), (r.getDecompiledFunction().getC() if r.decompileCompleted() else "(échec)")
# candidates NOT reachable from network handler + known media ones for reference
cands={ "UNKNOWN_1":0x801899c,"UNKNOWN_5":0x801947c,"UNKNOWN_6":0x80194c8,
        "UNKNOWN_7":0x8019528,"UNKNOWN_11":0x80197a8,
        "REF_HomeNetwork":0x801abd2,"REF_iPod":0x801963c }
for tag,addr in cands.items():
    nm,c=decC(addr)
    print(f"\n################ {tag}  {nm} @ {addr:#x} ################")
    print(c)
proj.close()
