#!/usr/bin/env python3
"""Pilotage réseau d'un ampli Harman Kardon AVR 161 (port 10025).

Usage :
    ampli.py ping                  vérifie que l'ampli répond
    ampli.py on | off              allume / éteint
    ampli.py toggle                bascule allumé/éteint (marche aussi depuis la veille)
    ampli.py vol+ [n] | vol- [n]   monte / baisse le volume de n crans (défaut 1)
    ampli.py mute [on|off]         coupe/remet le son ; sans argument = bascule
    ampli.py source <nom>          change de source (ex. TV, Disc, MHL, "Cable Sat")
                                   bluetooth est la seule à passer par le menu de
                                   l'ampli (une dizaine de secondes) ; l'ampli n'a
                                   pas de commande directe pour cette source.
    ampli.py raw <commande> [para] envoie une commande brute (voir COMMANDS)

La liste des sources et des commandes vient du décompilage de l'appli officielle
« Harman Kardon Remote » (classe CommandSetAvr).

L'adresse de l'ampli se change avec la variable d'environnement AMPLI_HOST.

L'ampli ne confirme jamais l'exécution d'une commande : seule `heart-alive`
reçoit une réponse. Il perd aussi souvent la première requête d'une connexion
toute neuve. On envoie donc `heart-alive` jusqu'à obtenir une réponse avant
toute commande, puis on garde la même connexion.
"""
import os
import socket
import sys
import time

HOST = os.environ.get("AMPLI_HOST", "192.168.1.58")
PORT = 10025
STEP_DELAY = 0.3  # pause entre deux commandes sur la même connexion

# Valeurs `para` de `source-selection` envoyées par l'appli officielle (AVR).
# L'ampli ignore celles qu'il n'a pas physiquement (ex. DVR, Pandora sur le 161).
SOURCES = ["TV", "Disc", "Cable Sat", "DVR", "Server", "Radio", "AUX", "Game",
           "USB", "STB", "Audio", "Media Server", "iPod", "Home Network",
           "FM", "AM", "vTuner", "Sirius Radio", "Pandora",
           "Source A", "Source B", "Source C", "Source D"]

# Noms pratiques -> valeur `para` réelle (l'afficheur montre d'autres libellés).
ALIASES = {"mhl": "Media Server", "set-top box": "STB"}

# L'ampli n'a AUCUNE commande directe pour le Bluetooth (l'appli officielle non
# plus : onSourceBluetoothClick n'existe que pour les barres de son BDS). On
# l'atteint en naviguant dans le menu : home > Source Select > flèches > ok.
# La liste « Source Select » fait 15 lignes, s'ouvre sur la première et boucle,
# donc un seul « haut » mène à Bluetooth (dernière ligne).
MENU_SOURCES = {"bluetooth": 14}
MENU_LENGTH = 15
MENU_OPEN_DELAY = 3.0   # temps d'ouverture du menu puis de la liste
MENU_STEP_DELAY = 1.0   # pause entre deux touches : plus vite, l'ampli en perd

# Commandes brutes connues (nom envoyé dans <name>), issues de CommandSetAvr.
RAW_COMMANDS = ["power-on", "power-off", "power-toggle", "sleep",
                "volume-up", "volume-down", "mute-toggle", "mute-on", "mute-off",
                "play", "pause", "next", "previous", "forward", "reverse",
                "tune-up", "tune-down", "tone", "info", "options",
                "home", "ok", "back", "up", "down", "left", "right",
                "source-selection", "heart-alive", "bye-bye"]


def _request(name, para=""):
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<harman>\n<avr>\n<common>\n<control>\n'
           f'<name>{name}</name>\n<zone>Main Zone</zone>\n<para>{para}</para>\n'
           '</control>\n</common>\n</avr>\n</harman>').encode()
    head = ("POST AVR HTTP/1.1\r\nHost: :10025\r\n"
            "User-Agent: Harman Kardon AVR Remote Controller /2.0\r\n"
            f"Content-Length: {len(xml)}\r\n\r\n").encode()
    return head + xml


class Ampli:
    def __init__(self, host=HOST, port=PORT):
        self.sock = socket.create_connection((host, port), timeout=3)
        if not self.ping():
            raise ConnectionError("l'ampli accepte la connexion mais ne répond pas")

    def ping(self, tries=4):
        """Envoie heart-alive jusqu'à obtenir une réponse."""
        for _ in range(tries):
            self.sock.sendall(_request("heart-alive"))
            self.sock.settimeout(1.0)
            try:
                if b"heart-alive" in self.sock.recv(4096):
                    return True
            except socket.timeout:
                pass
        return False

    def send(self, name, para="", times=1):
        for _ in range(times):
            self.sock.sendall(_request(name, para))
            time.sleep(STEP_DELAY)

    def select_menu_source(self, position):
        """Choisit une source par sa position dans le menu « Source Select »."""
        self.send("home")
        time.sleep(MENU_OPEN_DELAY)
        self.send("ok")
        time.sleep(MENU_OPEN_DELAY)
        ups = MENU_LENGTH - position
        key, count = ("up", ups) if ups < position else ("down", position)
        for _ in range(count):
            self.send(key)
            time.sleep(MENU_STEP_DELAY - STEP_DELAY)
        self.send("ok")

    def close(self):
        self.sock.close()


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, args = argv[0], argv[1:]
    try:
        amp = Ampli()
    except OSError as e:
        print(f"Ampli injoignable sur {HOST}:{PORT} ({e}).", file=sys.stderr)
        return 1
    try:
        if cmd == "ping":
            print(f"L'ampli répond sur {HOST}.")
        elif cmd == "on":
            amp.send("power-on")
        elif cmd == "off":
            amp.send("power-off")
        elif cmd == "toggle":
            amp.send("power-toggle")
        elif cmd in ("vol+", "vol-"):
            n = int(args[0]) if args else 1
            amp.send("volume-up" if cmd == "vol+" else "volume-down", times=n)
        elif cmd == "mute":
            arg = args[0].lower() if args else ""
            if arg == "on":
                amp.send("mute-on")
            elif arg == "off":
                amp.send("mute-off")
            else:
                amp.send("mute-toggle")
        elif cmd == "source":
            if not args:
                print("Sources directes : " + ", ".join(SOURCES + ["MHL"]), file=sys.stderr)
                print("Via le menu (~10 s) : " + ", ".join(MENU_SOURCES), file=sys.stderr)
                return 2
            wanted = " ".join(args)
            if wanted.lower() in MENU_SOURCES:
                amp.select_menu_source(MENU_SOURCES[wanted.lower()])
            else:
                wanted = ALIASES.get(wanted.lower(), wanted)
                name = next((s for s in SOURCES if s.lower() == wanted.lower()), wanted)
                amp.send("source-selection", name)
        elif cmd == "raw":
            if not args:
                print("Usage : ampli.py raw <commande> [para]", file=sys.stderr)
                print("Commandes : " + ", ".join(RAW_COMMANDS), file=sys.stderr)
                return 2
            amp.send(args[0], " ".join(args[1:]))
        else:
            print(f"Commande inconnue : {cmd}\n{__doc__}", file=sys.stderr)
            return 2
    finally:
        amp.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
