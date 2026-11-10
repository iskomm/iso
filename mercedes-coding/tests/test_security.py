import pytest
from fake_transport import FakeEcu
from src.uds import UdsClient
from src.security import (SecurityProfile, XorKey, AddConstantKey, ConstantKey,
                          LfsrRotateKey, unlock, SeedKeyError)


def test_xor_key_roundtrip():
    algo = XorKey(bytes([0xFF, 0xFF, 0xFF, 0xFF]))
    assert algo(bytes([0x00, 0x0F, 0xF0, 0xAA])) == bytes([0xFF, 0xF0, 0x0F, 0x55])


def test_add_constant_wraps():
    algo = AddConstantKey(0x1000)
    assert algo(bytes([0x00, 0x00])) == bytes([0x10, 0x00])
    # tasma mod 2^16
    assert algo(bytes([0xFF, 0xFF])) == bytes([0x0F, 0xFF])


def test_lfsr_is_deterministic():
    algo = LfsrRotateKey()
    seed = bytes([0x11, 0x22, 0x33, 0x44])
    assert algo(seed) == algo(seed)
    assert len(algo(seed)) == 4


def test_profile_requires_registered_level():
    prof = SecurityProfile()
    with pytest.raises(SeedKeyError):
        prof.key_for(3, b"\x00")


def test_full_unlock_handshake_with_matching_algo():
    # ECU'nun bekledigi anahtar: seed XOR mask olsun
    mask = bytes([0xAA, 0xBB, 0xCC, 0xDD])
    ecu = FakeEcu()
    ecu.expected_key = bytes(s ^ m for s, m in zip(ecu.seed, mask))
    uds = UdsClient(ecu)

    prof = SecurityProfile().register(1, XorKey(mask))
    assert unlock(uds, prof, level=1) is True
    assert ecu.unlocked is True


def test_wrong_key_is_rejected():
    ecu = FakeEcu()
    ecu.expected_key = bytes([0xDE, 0xAD, 0xBE, 0xEF])
    uds = UdsClient(ecu)
    prof = SecurityProfile().register(1, ConstantKey(bytes([0, 0, 0, 0])))
    with pytest.raises(Exception):
        unlock(uds, prof, level=1)


def test_already_unlocked_seed_zero():
    ecu = FakeEcu()
    ecu.unlocked = True  # seed sifir doner
    uds = UdsClient(ecu)
    prof = SecurityProfile().register(1, ConstantKey(b"\x00"))
    assert unlock(uds, prof, level=1) is True
