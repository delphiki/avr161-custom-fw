import sys, urllib.request, re
U="http://192.168.1.58:8080/RenderingControl/control"; ST="urn:schemas-upnp-org:service:RenderingControl:1"
def soap(action, **args):
    a="".join(f"<{k}>{v}</{k}>" for k,v in {"InstanceID":0,"Channel":"Master",**args}.items())
    body=f'<?xml version="1.0"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body><u:{action} xmlns:u="{ST}">{a}</u:{action}></s:Body></s:Envelope>'
    r=urllib.request.Request(U,body.encode(),{"Content-Type":'text/xml; charset="utf-8"',"SOAPACTION":f'"{ST}#{action}"'})
    try: x=urllib.request.urlopen(r,timeout=4).read().decode()
    except urllib.error.HTTPError as e: x=f"HTTP {e.code} "+e.read().decode()[:300]
    return re.sub(r"<[^>]*Envelope.*?<s:Body>|</s:Body>.*","",x,flags=re.S)
if __name__=="__main__": print(soap(sys.argv[1], **dict(a.split("=",1) for a in sys.argv[2:])))
