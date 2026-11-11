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
    f=fm.getFunctionContaining(A(addr)); r=ifc.decompileFunction(f,120,mon)
    return f.getName(), (r.getDecompiledFunction().getC() if r.decompileCompleted() else "(échec)")
# 1) enum->name display (FUN_08052f80) : find value mapped to BLUETOOTH
nm,c=decC(0x80531d0)
print(f"===== {nm} : lignes autour de BLUETOOTH / enum =====")
lines=c.splitlines()
for i,ln in enumerate(lines):
    if "BLUETOOTH" in ln or "d98f0" in ln:
        for j in range(max(0,i-6),min(len(lines),i+2)): print("  ",lines[j])
        print("   ----")
# 2) media menu around 0x802bcae : confirm UNKNOWN_11 is the Bluetooth item
nm,c=decC(0x802bcae)
print(f"\n===== media menu {nm} : extrait set_src_UNKNOWN_11 =====")
lines=c.splitlines()
for i,ln in enumerate(lines):
    if "UNKNOWN_11" in ln or "UNKNOWN_8" in ln or "iPod" in ln or "0x8019704" in ln or "0x8019690" in ln:
        print(f"  {ln.strip()}")
proj.close()
