"""Les images publiées ou validées sur matériel doivent rester reconstructibles à l'octet près.
`legacymute` rétablit l'ancienne lecture (fausse) du mute, que ces images contiennent."""
import hashlib
import pytest
import patchlib
from build_patch1 import build_patch1

V110 = {"getstatus", "setvolume", "bluetooth", "keepsleep", "push", "osdgreen", "surround", "legacymute"}
V105 = {"getstatus", "setvolume", "bluetooth", "keepsleep", "legacymute"}


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
