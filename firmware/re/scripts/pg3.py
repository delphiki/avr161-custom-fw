import pyghidra
pyghidra.start()
from ghidra.base.project import GhidraProject
from ghidra.util.task import ConsoleTaskMonitor
proj=GhidraProject.openProject("/Users/julienvilletorte/PersonnalProjects/ampli/firmware/ghidra","AVR161",True)
prog=proj.openProgram("/","AVR1610_USB(V002_20).fw",True)
fm=prog.getFunctionManager(); rm=prog.getReferenceManager()
from collections import defaultdict
set_src={f.getEntryPoint().getOffset():f.getName() for f in fm.getFunctions(True) if f.getName().startswith("set_src_")}
# caller func -> list of (callsite_offset, target_name)
calls=defaultdict(list)
for off,nm in set_src.items():
    ep=prog.getAddressFactory().getDefaultAddressSpace().getAddress(off)
    for r in rm.getReferencesTo(ep):
        cf=fm.getFunctionContaining(r.getFromAddress())
        if cf: calls[cf].append((r.getFromAddress().getOffset(), nm))
# print each caller's ordered sequence
for cf,lst in sorted(calls.items(), key=lambda kv:-len(kv[1])):
    lst=sorted(set(lst))
    print(f"\n### {cf.getName()} @ {cf.getEntryPoint()}  ({len(lst)} calls)")
    for a,n in lst:
        print(f"   {a:#010x} -> {n}")
proj.close()
