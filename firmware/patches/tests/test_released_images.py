"""Les images publiées ou validées sur matériel doivent rester reconstructibles à l'octet près.
`legacymute` rétablit l'ancienne lecture (fausse) du mute, que ces images contiennent."""
import hashlib
import pytest
import patchlib
from build_patch1 import build_patch1

V110 = {"getstatus", "setvolume", "bluetooth", "keepsleep", "push", "osdgreen", "surround", "legacymute"}
V105 = {"getstatus", "setvolume", "bluetooth", "keepsleep", "legacymute"}
V120 = {"getstatus", "setvolume", "bluetooth", "keepsleep", "push", "osdgreen", "surround", "netoff", "mute",
        "sleeptimer", "portguard", "powerstate"}


def _sha(features, version):
    return hashlib.sha256(bytes(build_patch1(patchlib.load_stock(), features=features, version=version))).hexdigest()


def test_image_validated_on_hardware_on_2026_11_14_is_reproducible():
    # flashée sous le nom v1.1.0-test : push, OSD vert, surround
    assert _sha(V110, "1.1.0-test") == "3eaa84c65f2567d4b819f5889e4cc855055245e5cad3cd172eb2588e41fce238"


def test_v1_1_0_release_differs_from_the_validated_image_only_by_its_version_string():
    stock = patchlib.load_stock()
    a = bytes(build_patch1(patchlib.load_stock(), features=V110, version="1.1.0-test"))
    b = bytes(build_patch1(patchlib.load_stock(), features=V110, version="1.1.0"))
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    assert diff and min(diff) >= 0xe03c0 and max(diff) < 0xe03cb      # la chaîne de version, rien d'autre


def test_legacymute_and_mute_cannot_be_combined():
    with pytest.raises(ValueError):
        build_patch1(patchlib.load_stock(), features={"getstatus", "mute", "legacymute"})


def test_image_validated_on_hardware_on_2026_11_17_is_reproducible():
    # flashée sous le nom v1.2.16-diag : éteint-joignable, extinction profonde, état de veille,
    # allumage depuis l'éteint sans relance du réseau ; avec les commandes de diagnostic
    assert _sha(V120 | {"diag"}, "1.2.16-diag") == "c77ac57fe48de731ad37b2ccc6510372718a0c851aa8131a71678313ac04ddf6"


def test_v1_2_0_release_is_reproducible():
    assert _sha(V120, "1.2.0") == "61fa57993e71b106e7c3ccb835b17cdb3b8170e11469d4c62f73137476f10650"


def test_v1_2_0_release_differs_from_the_validated_image_only_by_the_diagnostics_and_the_version():
    a = bytes(build_patch1(patchlib.load_stock(), features=V120 | {"diag"}, version="1.2.16-diag"))
    b = bytes(build_patch1(patchlib.load_stock(), features=V120, version="1.2.0"))
    allowed = [(0x73984, 0x73988), (0x866d0, 0x866d4), (0x8671c, 0x86720),   # trois détours du journal
               (0xe01f8, 0xe0280),      # aiguillage des commandes : debug-peek / debug-poke en moins
               (0xe03c0, 0xe03d0),      # chaîne de version
               (0xe0860, 0xe0a00),      # commandes de diagnostic et leurs noms
               (0xe0a00, 0xe0e00),      # trace, journal et détours du diagnostic
               (0xe0f1e, 0xe0f20)]      # fin du tick portguard : enchaîne sur le tick suivant
    diff = [i for i in range(len(a)) if a[i] != b[i]]
    assert diff and all(any(lo <= i < hi for lo, hi in allowed) for i in diff)


def test_v1_2_0_release_has_no_diagnostic_command():
    b = bytes(build_patch1(patchlib.load_stock(), features=V120, version="1.2.0"))
    assert b"debug-peek" not in b and b"debug-poke" not in b
