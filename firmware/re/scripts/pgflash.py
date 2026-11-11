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
af=prog.getAddressFactory()
def A(x): return sp.getAddress(x)
mon=ConsoleTaskMonitor()
di=DecompInterface(); di.openProgram(prog)
from ghidra.app.cmd.disassemble import DisassembleCommand
from ghidra.program.model.address import AddressSet

def ensure(off):
    f=fm.getFunctionContaining(A(off))
    if f: return f
    # try to disassemble+create
    try:
        DisassembleCommand(A(off|0),None,True).applyTo(prog,mon)
    except Exception as e: pass
    f=fm.getFunctionContaining(A(off))
    return f

def dec(off,tag=""):
    f=fm.getFunctionContaining(A(off)) or ensure(off&~1)
    if not f:
        print(f"\n### no func @ {off:#x} {tag}"); return None
    print("\n"+"="*72+f"\nFUNC {f.getName()} @ {f.getEntryPoint()} size={f.getBody().getNumAddresses()} {tag}\n"+"="*72)
    r=di.decompileFunction(f,90,mon)
    print(r.getDecompiledFunction().getC() if r and r.decompileCompleted() else "  <fail>")
    return f

def callers(f,tag=""):
    if not f: return
    cs=set()
    for r in rm.getReferencesTo(f.getEntryPoint()):
        cf=fm.getFunctionContaining(r.getFromAddress())
        if cf: cs.add(cf.getEntryPoint().getOffset())
    print(f"\n>>> callers of {f.getName()} ({tag}): "+", ".join(hex(c) for c in sorted(cs)))
    return sorted(cs)

# The pool with flash keys is at 0x800af44; the code using it is just above. Find function covering ~0x800ae00-0x800af44
fw_writer=None
for probe in (0x800af00,0x800aef0,0x800ae80,0x800ae00,0x800af44):
    f=fm.getFunctionContaining(A(probe))
    if f: fw_writer=f; break
if fw_writer:
    print("flash-writer function:",fw_writer.getName(),fw_writer.getEntryPoint())
    r=di.decompileFunction(fw_writer,90,mon)
    print(r.getDecompiledFunction().getC() if r and r.decompileCompleted() else "<fail>")
    cl=callers(fw_writer,"flash writer")
    for c in (cl or [])[:4]:
        dec(c,"[caller of flash writer]")
else:
    print("no function around 0x800af00; dumping raw context later")
# second flash site
dec(0x80a4d64,"[FLASH_R_BASE ref @0x80a4d64]")
proj.close()
