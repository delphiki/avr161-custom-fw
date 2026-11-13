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

STRS={
 "USB Software Upgrade":0x80d8574,
 "Press OK to update to":0x80d86ac,
 "INCORRECT VERSION":0x80dc834,
 "NO upgrade file":0x80d9abc,
 "app.fwUpdEnabled":0x80d8c04,
 "MCU IAP VERSION":0x80d979c,
 "UPGRADE SUCCESS":0x80d9634,
 "Current Version":0x80d942c,
 "WRITE FAIL":0x80d0254,
 "MCU UPDATE":0x80d01c8,
 "VENICE UPDATE":0x80d96e8,
 "DSP UPDATE":0x80d9724,
}
print("=== string -> referencing functions ===")
funcs={}
for name,va in STRS.items():
    refs=list(rm.getReferencesTo(A(va)))
    fs=[]
    for r in refs:
        f=fm.getFunctionContaining(r.getFromAddress())
        if f:
            fs.append(f.getName()+"@"+str(f.getEntryPoint()))
            funcs[f.getEntryPoint().getOffset()]=f
    print(f"  {name:24s} ({va:#x}): {len(refs)} refs -> {sorted(set(fs))}")

print(f"\n=== {len(funcs)} unique functions to decompile ===")
di=DecompInterface(); di.openProgram(prog)
for off in sorted(funcs):
    f=funcs[off]
    print("\n"+"="*70)
    print(f"FUNC {f.getName()} @ {f.getEntryPoint()}  size={f.getBody().getNumAddresses()}")
    print("="*70)
    res=di.decompileFunction(f,60,mon)
    if res and res.decompileCompleted():
        print(res.getDecompiledFunction().getC())
    else:
        print("  <decompile failed>")
proj.close()
