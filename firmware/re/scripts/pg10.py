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
f=fm.getFunctionContaining(A(0x801af34)); r=ifc.decompileFunction(f,120,mon)
print("#### FUN_0801af34 (candidate BT routing) ####")
print(r.getDecompiledFunction().getC() if r.decompileCompleted() else "(echec)")
# dispatcher entry
d=fm.getFunctionContaining(A(0x801af34))
proj.close()
