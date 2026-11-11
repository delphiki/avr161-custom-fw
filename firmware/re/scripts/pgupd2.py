import os, pyghidra
pyghidra.start()
from ghidra.base.project import GhidraProject
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

PROJ="/Users/julienvilletorte/PersonnalProjects/ampli/firmware/ghidra"
proj=GhidraProject.openProject(PROJ,"AVR161",True)
prog=proj.openProgram("/","AVR1610_USB(V002_20).fw",True)
fm=prog.getFunctionManager(); rm=prog.getReferenceManager()
sp=prog.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
mon=ConsoleTaskMonitor()
di=DecompInterface(); di.openProgram(prog)

def dec(off,tag=""):
    f=fm.getFunctionContaining(A(off)) or fm.getFunctionAt(A(off))
    if not f:
        print(f"\n### no function at {off:#x} {tag}"); return None
    print("\n"+"="*72)
    print(f"FUNC {f.getName()} @ {f.getEntryPoint()} size={f.getBody().getNumAddresses()} {tag}")
    print("="*72)
    r=di.decompileFunction(f,60,mon)
    if r and r.decompileCompleted(): print(r.getDecompiledFunction().getC())
    else: print("  <fail>")
    return f

def callers(off,tag=""):
    f=fm.getFunctionContaining(A(off))
    if not f: print(f"no func {off:#x}"); return []
    cs=set()
    for r in rm.getReferencesTo(f.getEntryPoint()):
        cf=fm.getFunctionContaining(r.getFromAddress())
        if cf: cs.add(cf.getEntryPoint().getOffset())
    print(f"callers of {f.getName()} ({tag}): " + ", ".join(hex(c) for c in sorted(cs)))
    return sorted(cs)

# 1) INCORRECT VERSION gate
dec(0x080a281c,"[INCORRECT VERSION]")
callers(0x080a281c,"INCORRECT VERSION")
# 2) fwUpdEnabled
dec(0x080ac348,"[app.fwUpdEnabled]")
callers(0x080ac348,"fwUpdEnabled")
# 3) is 0x080b7420 an MD5 state block? who refs it
print("\n=== refs to 0x080b7420 (MD5-IV-looking block) ===")
for r in rm.getReferencesTo(A(0x080b7420)):
    f=fm.getFunctionContaining(r.getFromAddress())
    print(f"  from {r.getFromAddress()} in {f.getName() if f else '?'}")
# also the function spanning 0x080b7420 (is it code or data?)
fcon=fm.getFunctionContaining(A(0x080b7420))
print("  containing function:", fcon.getName() if fcon else "None (data)")
proj.close()
