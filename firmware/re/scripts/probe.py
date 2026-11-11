import socket, time, sys
sys.path.insert(0, ".")
from hk3 import req, IP, PORT
def ask(s, wait=2.0):
    s.sendall(req("heart-alive")); t=time.time(); s.settimeout(wait)
    try:
        d=s.recv(4096); return f"{(time.time()-t)*1000:.0f}ms" if d else "CLOSED"
    except socket.timeout: return "-"
    except OSError as e: return type(e).__name__
print("A) new connection per probe, 1s gap:")
r=[]
for i in range(8):
    s=socket.create_connection((IP,PORT),timeout=3); r.append(ask(s)); s.close(); time.sleep(1)
print("  ", r)
print("B) one connection, 8 probes 1s apart:")
s=socket.create_connection((IP,PORT),timeout=3); r=[]
for i in range(8): r.append(ask(s)); time.sleep(1)
print("  ", r)
print("C) same connection, idle 20s then 3 probes:")
time.sleep(20); r=[ask(s) for _ in range(3)]; print("  ", r); s.close()
