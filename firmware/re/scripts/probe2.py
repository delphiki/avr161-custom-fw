import socket, time, sys
sys.path.insert(0, ".")
from hk3 import req, IP, PORT
def ask(s, wait=1.5):
    s.sendall(req("heart-alive")); s.settimeout(wait)
    try: return "ok" if s.recv(4096) else "CLOSED"
    except socket.timeout: return "-"
    except OSError as e: return type(e).__name__
def summ(tag, r): print(f"{tag}: {r.count('ok')}/{len(r)} ok  ", "".join('.' if x=='ok' else 'X' for x in r), flush=True)
s=socket.create_connection((IP,PORT),timeout=3)
r=[]
for i in range(40): r.append(ask(s)); time.sleep(0.3)
summ("persistent x40, 0.3s gap", r); s.close(); time.sleep(3)
r=[]
for i in range(15):
    s=socket.create_connection((IP,PORT),timeout=3); r.append(ask(s)); s.close(); time.sleep(0.3)
summ("fresh conn, send immediately x15", r); time.sleep(3)
r=[]
for i in range(15):
    s=socket.create_connection((IP,PORT),timeout=3); time.sleep(0.7); r.append(ask(s)); s.close(); time.sleep(0.3)
summ("fresh conn, wait 0.7s before send x15", r); time.sleep(3)
r=[]
for i in range(15):
    s=socket.create_connection((IP,PORT),timeout=3); a=ask(s); b=ask(s); r.append("ok" if b=="ok" else "-"); s.close(); time.sleep(0.3)
summ("fresh conn, 2nd request x15", r)
