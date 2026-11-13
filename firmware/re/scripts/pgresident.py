import pyghidra
pyghidra.start()
from ghidra.base.project import GhidraProject
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.app.cmd.disassemble import DisassembleCommand
from ghidra.app.cmd.function import CreateFunctionCmd
import os as _os  # chemins déduits de l'emplacement du script ; surcharge : AVR161_FW / AVR161_GHIDRA_DIR
_FW_DIR=_os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),'../..'))
PROJ=(_os.environ.get("AVR161_GHIDRA_DIR") or _os.path.join(_FW_DIR,"ghidra"))
proj=GhidraProject.openProject(PROJ,"AVR161",True)
prog=proj.openProgram("/","AVR1610_USB(V002_20).fw",True)
fm=prog.getFunctionManager()
sp=prog.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
mon=ConsoleTaskMonitor()

targets=[0x8005500,0x80057b4,0x8005be4,0x8005d0a,0x8005480,0x8004c78]
tid=prog.startTransaction("diss")
try:
    for t in targets:
        if not fm.getFunctionContaining(A(t)):
            DisassembleCommand(A(t),None,True).applyTo(prog,mon)
            CreateFunctionCmd(A(t)).applyTo(prog,mon)
finally:
    prog.endTransaction(tid,True)

di=DecompInterface(); di.openProgram(prog)
for t in targets:
    f=fm.getFunctionContaining(A(t))
    print("\n"+"="*72)
    print(f"{'FUNC '+f.getName()+' @ '+str(f.getEntryPoint()) if f else 'NO FUNC @ '+hex(t)}")
    print("="*72)
    if f:
        r=di.decompileFunction(f,120,mon)
        print(r.getDecompiledFunction().getC() if r and r.decompileCompleted() else "  <fail>")
proj.save(prog)
proj.close()
