#!/usr/bin/env python3
"""Pilotage réseau d'un ampli Harman Kardon AVR 161 (port 10025).

Usage :
    ampli.py ping                  vérifie que l'ampli répond
    ampli.py on | off              allume / éteint
    ampli.py toggle                bascule allumé/éteint (marche aussi depuis la veille)
    ampli.py vol+ [n] | vol- [n]   monte / baisse le volume de n crans (défaut 1)
    ampli.py mute [on|off]         coupe/remet le son ; sans argument = bascule
    ampli.py source <nom>          change de source (ex. TV, Disc, MHL, "Cable Sat",
                                   Bluetooth — direct avec le firmware custom)
    ampli.py status                alimentation (firmware >= 1.0.5) / volume / mute / source /
                                   version (firmware custom)
    ampli.py set-volume <n|NdB>    volume absolu 0-180 ou en dB (ex. -25db) ; une seule
                                   commande avec le firmware custom >= 1.0.4, sinon
                                   boucle de pas côté client
    ampli.py surround [mode]       sans argument : mode surround courant et liste des modes ;
                                   avec un nom, un code (0-45) ou « auto » (Auto Select) :
                                   sélection directe (firmware custom avec la fonction surround)
    ampli.py version               version du firmware custom
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

# Le firmware STOCK n'a aucune commande directe pour le Bluetooth (l'appli officielle
# non plus) ; le firmware custom en ajoute une (source-selection Bluetooth). Repli stock :
# naviguer dans le menu : home > Source Select > flèches > ok.
# La liste « Source Select » fait 15 lignes, s'ouvre sur la première et boucle,
# donc un seul « haut » mène à Bluetooth (dernière ligne).
MENU_SOURCES = {"bluetooth": 14}
MENU_LENGTH = 15
MENU_OPEN_DELAY = 3.0   # temps d'ouverture du menu puis de la liste
MENU_STEP_DELAY = 1.0   # pause entre deux touches : plus vite, l'ampli en perd

# Commandes brutes connues (nom envoyé dans <name>), issues de CommandSetAvr.
# get-status / set-volume ne sont dispo qu'avec le firmware CUSTOM (patch #1 ; set-volume >= 1.0.4).
RAW_COMMANDS = ["power-on", "power-off", "power-toggle", "sleep",
                "volume-up", "volume-down", "mute-toggle", "mute-on", "mute-off",
                "play", "pause", "next", "previous", "forward", "reverse",
                "tune-up", "tune-down", "tone", "info", "options",
                "home", "ok", "back", "up", "down", "left", "right",
                "source-selection", "heart-alive", "bye-bye",
                "rds", "delay", "channel-up", "channel-down", "surround-mode",
                "get-status", "set-volume", "set-surround", "power-full-off"]

# Code de source renvoyé par get-status (firmware custom) -> nom lisible. Vérifié sur
# l'ampli le 2026-11-13 en sélectionnant chaque source (16 = Home Network DMR : décompilage).
SOURCE_ENUM = {0: "Cable Sat", 1: "Disc", 2: "MHL", 3: "AUX", 4: "Game", 5: "STB",
               6: "Audio", 7: "TV", 8: "AM", 9: "FM", 10: "USB", 11: "iPod",
               12: "Home Network", 13: "vTuner", 16: "Home Network", 17: "Bluetooth"}


# Code du mode surround (6e champ de get-status, para de set-surround) -> nom affiché par
# l'ampli. Tiré de la routine d'affichage du firmware (FUN_0805b02c) ; plusieurs codes portent
# le même nom (variantes selon le signal d'entrée et le nombre d'enceintes) : le premier sert
# à la sélection par nom. L'ampli refuse un mode impossible avec le signal courant.
SURROUND_MODES = {
    0: "Virtual Surround", 1: "Virtual Surr.2", 2: "2CH Stereo", 3: "2CH Stereo",
    4: "2CH Stereo", 5: "2CH Stereo", 6: "Dolby Digital", 7: "DTS", 8: "DTS 96/24",
    9: "5CH Stereo", 10: "Dolby Digital EX", 11: "DTS-ES Matrix", 12: "DTS-ES Discrete",
    13: "DTS Neo:6 Cinema", 14: "7CH Stereo", 15: "Logic 7 Movie", 16: "Dolby PLII Movie",
    17: "DTS Neo:6 Cinema", 18: "Logic 7 Movie", 19: "Dolby PLIIx Movie",
    20: "DTS Neo:6 Cinema", 21: "Logic 7 Music", 22: "Dolby PLII Music",
    23: "DTS Neo:6 Music", 24: "Logic 7 Music", 25: "Dolby PLIIx Music",
    26: "DTS Neo:6 Music", 27: "Logic 7 Game", 28: "Dolby PLII Game", 29: "Logic 7 Game",
    30: "Dolby PLIIx Game", 31: "Dolby PLIIz", 32: "Dolby PLIIz", 33: "Dolby PLIIz",
    37: "Dolby TrueHD", 38: "Dolby Digital Plus", 39: "DTS-HD Master", 40: "DTS-HD Hi Res",
    41: "DTS-HD LBR", 42: "Headphone Bypass", 43: "Harman Headphone", 44: "Multi-CH PCM",
    45: "Harman NSP",
}
SURROUND_MAX = 45
# Modes que le défilement du firmware propose sur un ampli 5.1 (fonctions « mode suivant » de
# chaque catégorie : FUN_0803a696 stéréo, a72e film, a858 musique, a922 jeu), en plus de
# « Auto Select ». Nom -> codes à essayer dans l'ordre (variantes selon le signal).
SURROUND_CHOICES = {
    "Virtual Surround": [0], "2CH Stereo": [2, 3, 5], "5CH Stereo": [9], "Harman NSP": [45],
    "Logic 7 Movie": [15, 18], "Dolby PLII Movie": [16], "DTS Neo:6 Cinema": [17, 13, 20],
    "Logic 7 Music": [21, 24], "Dolby PLII Music": [22], "DTS Neo:6 Music": [23, 26],
    "Logic 7 Game": [27, 29], "Dolby PLII Game": [28],
}


def surround_code(wanted):
    """Nom (insensible à la casse) ou code décimal -> code de mode surround. ValueError sinon."""
    w = wanted.strip().lower()
    if w.isdigit():
        if int(w) <= SURROUND_MAX:
            return int(w)
        raise ValueError(f"mode surround hors plage : {wanted}")
    for code, name in SURROUND_MODES.items():
        if name.lower() == w:
            return code
    raise ValueError(f"mode surround inconnu : {wanted!r}")


def parse_status(para):
    """Parse le `para` de get-status ('vol,mute,src[,fw[,pwr[,sur]]]') ->
    dict {vol,mute,source[,fw][,power][,surround,surround_code]} ; power (firmware >= 1.0.5) :
    True = allumé, False = sleep ; surround : nom du mode (ou son code s'il est inconnu)."""
    vol, mute, src, fw, pwr, sur, cat = (para.split(",") + [""] * 7)[:7]
    d = {"vol": int(vol), "mute": bool(int(mute)),
         "source": SOURCE_ENUM.get(int(src), str(int(src)))}
    if fw:
        d["fw"] = fw          # version du firmware custom (patch >= v1.0.0)
    if pwr:
        d["power"] = bool(int(pwr))
    if sur:
        d["surround_code"] = int(sur)
        d["surround"] = SURROUND_MODES.get(int(sur), str(int(sur)))
    if cat:
        d["surround_auto"] = int(cat) == 0     # catégorie 0 = Auto Select
    return d


SETVOL_FW_MIN = (1, 0, 4)   # 1re version dont la commande firmware set-volume est validée
FW_TRIES = 3                # envois max de la commande firmware (l'ampli ignore une commande
FW_RETRY_DELAY = 0.7        # arrivant < ~0,5 s après la précédente : cooldown du dispatch)


def fw_at_least(fw, minimum):
    """True si la version firmware `fw` ('1.0.4', '1.0.2d'…) est >= `minimum` (tuple)."""
    import re
    if not fw:
        return False
    parts = []
    for comp in fw.split("."):
        m = re.match(r"\d+", comp)
        if not m:
            return False
        parts.append(int(m.group()))
    return tuple(parts) >= tuple(minimum)


# Échelle volume interne 0..180 (~0,5 dB/pas) <-> dB (-80..+10 dB, 0 dB à l'index 160).
def internal_to_db(n):
    return round(-80.0 + 0.5 * n, 1)


def db_to_internal(db):
    return int(round((db + 80.0) * 2))


def _request(name, para=""):
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<harman>\n<avr>\n<common>\n<control>\n'
           f'<name>{name}</name>\n<zone>Main Zone</zone>\n<para>{para}</para>\n'
           '</control>\n</common>\n</avr>\n</harman>').encode()
    head = ("POST AVR HTTP/1.1\r\nHost: :10025\r\n"
            "User-Agent: Harman Kardon AVR Remote Controller /2.0\r\n"
            f"Content-Length: {len(xml)}\r\n\r\n").encode()
    return head + xml


# Une requête envoyée dans les ~100 ms qui suivent la connexion est perdue une fois sur deux
# (mesuré le 2026-11-13 : 22 servies sur 42 sans attente, 9 sur 9 avec 0,1 s ou plus).
CONNECT_SETTLE = 0.3


class Ampli:
    def __init__(self, host=HOST, port=PORT):
        self.sock = socket.create_connection((host, port), timeout=3)
        time.sleep(CONNECT_SETTLE)
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

    def set_volume(self, target):
        """Règle le volume à une valeur absolue (0..180). Firmware custom >= 1.0.4 : UNE
        commande `set-volume` (saut direct, pile sur la cible), renvoyée si l'ampli l'a
        ignorée (cooldown). Sinon, ou si elle ne prend pas : boucle de pas côté client."""
        target = max(0, min(180, int(target)))
        st = self.get_status()
        if st is None:
            return None
        if st["vol"] == target:
            return target
        if fw_at_least(st.get("fw"), SETVOL_FW_MIN):
            for attempt in range(FW_TRIES):
                if attempt:
                    time.sleep(FW_RETRY_DELAY)
                self.send("set-volume", str(target))
                st = self.get_status()
                if st is None:
                    return None
                if st["vol"] == target:
                    return target
        return self.set_volume_absolute(target)

    def set_volume_absolute(self, target, max_steps=120):
        """Règle le volume à une valeur absolue (0..180), côté client : lit get-status
        puis envoie des volume-up/down jusqu'à la cible. Nécessite get-status (firmware
        custom). Robuste (réutilise les commandes volume-up/down prouvées)."""
        target = max(0, min(180, int(target)))
        for _ in range(max_steps):
            st = self.get_status()
            if st is None:
                return None
            cur = st["vol"]
            if abs(cur - target) <= 1:
                return cur
            self.send("volume-up" if cur < target else "volume-down")
        return self.get_status()["vol"] if self.get_status() else None

    def get_status(self):
        """Interroge get-status (firmware custom) -> dict {vol,mute,source} ou None."""
        import re
        for _ in range(6):
            self.sock.sendall(_request("get-status"))
            self.sock.settimeout(1.5)
            try:
                r = self.sock.recv(8192)
            except socket.timeout:
                continue
            m = re.search(rb"<para>([^<]*)</para>", r)
            if b"get-status" in r and m and b"," in m.group(1):
                return parse_status(m.group(1).decode())
        return None

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
        elif cmd == "status":
            st = amp.get_status()
            if st is None:
                print("get-status sans réponse (nécessite le firmware custom).", file=sys.stderr)
                return 1
            line = (f"volume {st['vol']} ({internal_to_db(st['vol']):+.1f} dB) | "
                    f"mute {'on' if st['mute'] else 'off'} | source {st['source']}")
            if "surround" in st:
                line += (f" | surround Auto Select ({st['surround']})" if st.get("surround_auto")
                         else f" | surround {st['surround']}")
            if "fw" in st:
                line += f" | fw {st['fw']}"
            if "power" in st:
                line = ("allumé | " if st["power"] else "en sleep | ") + line
            print(line)
        elif cmd == "surround":
            st = amp.get_status()
            if st is None or "surround" not in st:
                print("mode surround indisponible (firmware custom avec la fonction surround requis).",
                      file=sys.stderr)
                return 1
            def shown(st):
                return ((f"surround Auto Select ({st['surround']})" if st.get("surround_auto")
                         else f"surround {st['surround']}") + f" (code {st['surround_code']})")
            if not args:
                print(shown(st))
                print("Modes : auto, " + ", ".join(SURROUND_CHOICES))
                return 0
            wanted = " ".join(args)
            if wanted.lower() in ("auto", "auto select"):
                paras, done = ["auto"], (lambda st: st.get("surround_auto", False))
            else:
                try:
                    code = surround_code(wanted)
                except ValueError as e:
                    print(e, file=sys.stderr)
                    return 2
                if wanted.strip().isdigit():       # code brut : on ne juge que le mode appliqué
                    codes = [code]
                    done = (lambda st: st["surround_code"] in codes)
                else:
                    codes = SURROUND_CHOICES.get(SURROUND_MODES.get(code), [code])
                    done = (lambda st: st["surround_code"] in codes
                            and not st.get("surround_auto", False))
                paras = [str(c) for c in codes]
            for para in paras * FW_TRIES:      # l'ampli ignore une commande trop rapprochée
                if done(st):
                    break
                time.sleep(FW_RETRY_DELAY)
                amp.send("set-surround", para)
                time.sleep(FW_RETRY_DELAY)
                st = amp.get_status() or st
            print(shown(st))
            if not done(st):
                print("mode refusé par l'ampli (impossible avec le signal ou la source en cours ?).",
                      file=sys.stderr)
                return 1
        elif cmd == "version":
            st = amp.get_status()
            if st and "fw" in st:
                print(f"firmware custom v{st['fw']}")
            elif st:
                print("firmware stock (pas de version custom).")
            else:
                print("ampli injoignable / get-status sans réponse.", file=sys.stderr)
                return 1
        elif cmd in ("set-volume", "setvol"):
            if not args:
                print("Usage : ampli.py set-volume <0-180 | NdB>  (nécessite le firmware custom)", file=sys.stderr)
                return 2
            a = args[0].lower()
            n = db_to_internal(float(a[:-2])) if a.endswith("db") else int(a)
            res = amp.set_volume(n)
            if res is None:
                print("set-volume impossible (get-status sans réponse — firmware custom requis).",
                      file=sys.stderr)
                return 1
            print(f"volume {res} ({internal_to_db(res):+.1f} dB)")
        elif cmd == "source":
            if not args:
                print("Sources directes : " + ", ".join(SOURCES + ["MHL", "Bluetooth"]), file=sys.stderr)
                return 2
            wanted = " ".join(args)
            if wanted.lower() == "bluetooth":
                # commande directe (firmware custom patch #1) ; fallback menu : select_menu_source(14)
                amp.send("source-selection", "Bluetooth")
            elif wanted.lower() in MENU_SOURCES:
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
