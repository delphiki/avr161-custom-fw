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

BT_STR=0x80d98f0
# 1) functions that reference the BLUETOOTH display string
print("=== refs to str_disp_BLUETOOTH (0x80d98f0) ===")
bt_funcs=set()
for r in rm.getReferencesTo(A(BT_STR)):
    fa=r.getFromAddress()
    f=fm.getFunctionContaining(fa)
    nm=f.getName() if f else "?"
    print(f"  from {fa} in {nm}")
    if f: bt_funcs.add(f)

# 2) all set_src_* functions (known + unknown) by name
set_src=[f for f in fm.getFunctions(True) if f.getName().startswith("set_src_")]
print(f"\n=== {len(set_src)} set_src_* functions ===")
addrs={f.getEntryPoint().getOffset():f.getName() for f in set_src}

# 3) callers of each set_src, grouped by caller function
from collections import defaultdict
caller_calls=defaultdict(list)
for f in set_src:
    for r in rm.getReferencesTo(f.getEntryPoint()):
        cf=fm.getFunctionContaining(r.getFromAddress())
        if cf: caller_calls[cf].append((r.getFromAddress(), f.getName()))

# 4) functions that both reference BT string AND call a set_src -> the menu
print("\n=== functions referencing BT string AND calling set_src ===")
for f in bt_funcs:
    if f in caller_calls:
        print(f"  *** {f.getName()} @ {f.getEntryPoint()} : calls {[c[1] for c in caller_calls[f]]}")
# also list what each BT-referencing function calls
print("\n=== set_src calls inside each BT-referencing function ===")
for f in bt_funcs:
    print(f"  {f.getName()} @ {f.getEntryPoint()}: {[(str(a),n) for a,n in caller_calls.get(f,[])]}")
proj.close()
