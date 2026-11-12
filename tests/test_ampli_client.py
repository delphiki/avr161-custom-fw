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
