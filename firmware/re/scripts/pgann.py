import pyghidra
pyghidra.start()
from ghidra.base.project import GhidraProject
from ghidra.program.model.symbol import SourceType
import os as _os  # chemins déduits de l'emplacement du script ; surcharge : AVR161_FW / AVR161_GHIDRA_DIR
_FW_DIR=_os.path.normpath(_os.path.join(_os.path.dirname(_os.path.abspath(__file__)),'../..'))
proj=GhidraProject.openProject((_os.environ.get("AVR161_GHIDRA_DIR") or _os.path.join(_FW_DIR,"ghidra")),"AVR161",True)
prog=proj.openProgram("/","AVR1610_USB(V002_20).fw",False)  # writable
fm=prog.getFunctionManager(); st=prog.getSymbolTable(); sp=prog.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
tx=prog.startTransaction("annotate BT")
try:
    # dispatcher containing the cVar1 chain = caller of 0x801af34
    rm=prog.getReferenceManager(); disp=None
    for r in rm.getReferencesTo(A(0x801af34)):
        f=fm.getFunctionContaining(r.getFromAddress())
        if f: disp=f; break
    renames=[]
    f=fm.getFunctionAt(A(0x801af34))
    if f: f.setName("set_src_Bluetooth", SourceType.USER_DEFINED); renames.append(("0x801af34","set_src_Bluetooth"))
    f2=fm.getFunctionAt(A(0x8049af8))
    if f2: f2.setName("bt_module_activate", SourceType.USER_DEFINED); renames.append(("0x8049af8","bt_module_activate"))
    if disp: disp.setName("src_switch_by_index", SourceType.USER_DEFINED); renames.append((str(disp.getEntryPoint()),"src_switch_by_index"))
    st.createLabel(A(0x2000e1ae),"g_source_enum",SourceType.USER_DEFINED); renames.append(("0x2000e1ae","g_source_enum"))
    setPlate=prog.getListing().getCodeUnitAt(A(0x801af34))
    if setPlate: setPlate.setComment(setPlate.PLATE_COMMENT,"Bascule source Bluetooth : pose g_source_enum=0x11 (OSD 'BLUETOOTH') + bt_module_activate(). Appelable depuis un patch.")
    prog.endTransaction(tx,True)
    proj.save(prog)
    print("RENAMES:", renames)
    print("dispatcher entry:", disp.getEntryPoint() if disp else "?")
except Exception as e:
    prog.endTransaction(tx,False); print("ERR",e)
proj.close()
