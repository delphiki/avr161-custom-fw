import socket, sys, time
IP, PORT = "192.168.1.58", 10025
def req(name, para=""):
    xml=('<?xml version="1.0" encoding="UTF-8"?>\n<harman>\n<avr>\n<common>\n<control>\n'
         f'<name>{name}</name>\n<zone>Main Zone</zone>\n<para>{para}</para>\n'
         '</control>\n</common>\n</avr>\n</harman>').encode()
    return (b"POST AVR HTTP/1.1\r\nHost: :10025\r\nUser-Agent: Harman Kardon AVR Remote Controller /2.0\r\n"
            b"Content-Length: %d\r\n\r\n" % len(xml)) + xml
def listen(s, dur):
    end=time.time()+dur
    while time.time()<end:
        s.settimeout(max(0.05,end-time.time()))
        try:
            d=s.recv(4096)
            if not d: print("  !! closed by amp", flush=True); return False
            body=d.split(b"\r\n\r\n",1)[-1]
            print("  <-", body[-120:], flush=True)
        except socket.timeout: pass
    return True
if __name__=="__main__":
    t0=time.time()
    s=socket.create_connection((IP,PORT),timeout=3)
    for a in sys.argv[1:]:
        if a.replace('.','',1).isdigit(): listen(s,float(a)); continue
        name,_,para=a.partition("=")
        s.sendall(req(name,para)); print(f"{time.time()-t0:5.1f}s sent {name} {para}", flush=True)
    listen(s,2); s.close()
