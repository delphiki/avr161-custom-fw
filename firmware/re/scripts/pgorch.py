import os, pyghidra
pyghidra.start()
from ghidra.base.project import GhidraProject
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.app.cmd.disassemble import DisassembleCommand
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
def fn(off):
    return fm.getFunctionContaining(A(off))
def dec(f,tag=""):
    if not f: print(f"  <no func> {tag}"); return
    print("\n"+"="*72+f"\nFUNC {f.getName()} @ {f.getEntryPoint()} size={f.getBody().getNumAddresses()} {tag}\n"+"="*72)
    r=di.decompileFunction(f,120,mon)
    print(r.getDecompiledFunction().getC() if r and r.decompileCompleted() else "  <fail>")
def callers_of(f):
    cs=set()
    for r in rm.getReferencesTo(f.getEntryPoint()):
        cf=fm.getFunctionContaining(r.getFromAddress())
        if cf: cs.add(cf.getEntryPoint().getOffset())
    return sorted(cs)

seen=set()
# containing functions of the two IAP orchestrators
probes={0x8005fe8:"A:program_word loop",0x800603c:"A:program_byte",0x8005f74:"A:erase",
        0x8007f00:"B:program_word loop",0x8007ece:"B:erase"}
topfuncs={}
for off,tag in probes.items():
    f=fn(off)
    if f and f.getEntryPoint().getOffset() not in seen:
        seen.add(f.getEntryPoint().getOffset()); topfuncs[f.getEntryPoint().getOffset()]=f
        dec(f,tag)
# one level up
print("\n\n##### CALLERS (update driver level) #####")
up=set()
for off,f in topfuncs.items():
    cs=callers_of(f)
    print(f"callers of {f.getName()}: "+", ".join(hex(c) for c in cs))
    up.update(cs)
for c in sorted(up):
    if c not in seen:
        seen.add(c); dec(fn(c),"[caller]")
proj.close()
