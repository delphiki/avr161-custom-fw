import socket, sys
IP="192.168.1.58"
def send(name, para=""):
    body=('<?xml version="1.0" encoding="UTF-8"?> <harman> <avr> <common> <control> '
          f'<name>{name}</name> <zone>Main Zone</zone> <para>{para}</para> '
          '</control> </common> </avr> </harman>')
    req=(f"POST /HK_APP HTTP/1.1\r\nHost: {IP}:10025\r\n"
         "User-Agent: Harman Kardon AVR Remote Controller /1.0\r\n"
         f"Content-Length: {len(body)}\r\n\r\n{body}")
    s=socket.create_connection((IP,10025),timeout=3); s.sendall(req.encode())
    try: r=s.recv(4096); print(name, para, "->", repr(r[:300]))
    except socket.timeout: print(name, para, "-> (sent, no reply)")
    s.close()
if __name__=="__main__": send(*sys.argv[1:])
