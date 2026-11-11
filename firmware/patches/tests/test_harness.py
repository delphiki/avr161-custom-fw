import pytest
import patchlib
import verifylib


def test_noop_build_is_byte_identical():
    stock = patchlib.load_stock()
    img = bytearray(stock)  # aucune modif
    assert verifylib.diff_offsets(bytes(img), stock) == set()
    assert len(img) == 6291456


def test_write_outside_rewritten_region_raises():
    img = patchlib.load_stock()
    with pytest.raises(ValueError):
        patchlib.write_bytes(img, 0x0d000, b"\x00")   # resident -> interdit
    with pytest.raises(ValueError):
        patchlib.write_bytes(img, 0x120000, b"\x00")  # composant DSP -> interdit


def test_write_inside_rewritten_region_ok():
    img = patchlib.load_stock()
    patchlib.write_bytes(img, 0xE0000, b"\xAA\xBB")  # cave -> autorise
    assert img[0xE0000:0xE0002] == b"\xAA\xBB"
