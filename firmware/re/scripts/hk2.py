import socket, sys, time
IP, PORT = "192.168.1.58", 10025
def req(name, para=""):
    xml=('<?xml version="1.0" encoding="UTF-8"?>\n<harman>\n<avr>\n<common>\n<control>\n'
         f'<name>{name}</name>\n<zone>Main Zone</zone>\n<para>{para}</para>\n'
         '</control>\n</common>\n</avr>\n</harman>').encode()
    return (b"POST AVR HTTP/1.1\r\nHost: :10025\r\nUser-Agent: Harman Kardon AVR Remote Controller /2.0\r\n"
            b"Content-Length: %d\r\n\r\n" % len(xml)) + xml
s = socket.create_connection((IP, PORT), timeout=3)
args = sys.argv[1:]  # name[=para] [delay] ...
for a in args:
    if a.replace('.','',1).isdigit(): time.sleep(float(a)); continue
    name, _, para = a.partition("=")
    s.sendall(req(name, para)); print("sent", name, para, flush=True)
s.settimeout(1.5)
try: print("reply:", s.recv(4096)[:500])
except Exception as e: print("no reply", type(e).__name__)
time.sleep(1); s.close()
