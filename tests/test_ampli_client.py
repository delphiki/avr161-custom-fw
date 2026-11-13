import ampli


def test_parse_status_reply():
    assert ampli.parse_status("42,0,17") == {"vol": 42, "mute": False, "source": "Bluetooth"}


def test_parse_status_muted_unknown_source():
    assert ampli.parse_status("110,1,2") == {"vol": 110, "mute": True, "source": "2"}


def test_db_mapping_bounds():
    assert ampli.internal_to_db(0) == -80.0
    assert ampli.internal_to_db(180) == 10.0


def test_db_mapping_midpoint():
    assert ampli.internal_to_db(160) == 0.0  # 0 dB de référence


def test_db_to_internal_roundtrip():
    for n in (0, 42, 110, 160, 180):
        assert ampli.db_to_internal(ampli.internal_to_db(n)) == n


def test_parse_status_with_fw_version():
    assert ampli.parse_status("90,0,17,1.0.0") == {
        "vol": 90, "mute": False, "source": "Bluetooth", "fw": "1.0.0"}


def test_parse_status_without_fw_has_no_fw_key():
    assert "fw" not in ampli.parse_status("90,0,2")


# --- set-volume : commande firmware (>= v1.0.4) avec repli boucle client ---

def test_fw_at_least():
    assert ampli.fw_at_least("1.0.4", (1, 0, 4))
    assert ampli.fw_at_least("1.2.0", (1, 0, 4))
    assert not ampli.fw_at_least("1.0.3", (1, 0, 4))
    assert not ampli.fw_at_least("1.0.2d", (1, 0, 4))      # suffixe non numérique toléré
    assert not ampli.fw_at_least(None, (1, 0, 4))
    assert not ampli.fw_at_least("", (1, 0, 4))


class FakeAmp(ampli.Ampli):
    """Ampli sans socket : modélise le volume, la version firmware et les refus (cooldown)."""

    def __init__(self, vol, fw=None, refuse=0):
        self.vol, self.fw, self.refuse, self.sent = vol, fw, refuse, []

    def get_status(self):
        d = {"vol": self.vol, "mute": False, "source": "2"}
        if self.fw:
            d["fw"] = self.fw
        return d

    def send(self, name, para="", times=1):
        self.sent.append((name, para))
        if name == "set-volume":
            if self.refuse > 0:
                self.refuse -= 1
            else:
                self.vol = int(para)
        elif name == "volume-up":
            self.vol += 2
        elif name == "volume-down":
            self.vol -= 2


def test_set_volume_uses_single_firmware_command_on_recent_fw():
    a = FakeAmp(110, fw="1.0.4")
    assert a.set_volume(82) == 82
    assert a.sent == [("set-volume", "82")]


def test_set_volume_retries_when_firmware_step_is_refused():
    a = FakeAmp(110, fw="1.0.4", refuse=1)            # 1er envoi ignoré (cooldown de l'ampli)
    assert a.set_volume(82) == 82
    assert a.sent == [("set-volume", "82"), ("set-volume", "82")]


def test_set_volume_falls_back_to_client_loop_on_old_fw():
    a = FakeAmp(110, fw="1.0.2")
    assert abs(a.set_volume(104) - 104) <= 1
    assert all(n == "volume-down" for n, _ in a.sent) and len(a.sent) == 3


def test_set_volume_falls_back_if_firmware_never_applies():
    a = FakeAmp(110, fw="1.0.4", refuse=99)
    assert abs(a.set_volume(106) - 106) <= 1
    assert ("volume-down", "") in a.sent


def test_set_volume_clamps_target():
    a = FakeAmp(100, fw="1.0.4")
    assert a.set_volume(999) == 180
    assert a.sent == [("set-volume", "180")]


def test_set_volume_noop_when_already_there():
    a = FakeAmp(90, fw="1.0.4")
    assert a.set_volume(90) == 90 and a.sent == []
