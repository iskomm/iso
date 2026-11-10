import json
from fake_transport import FakeEcu
from src.uds import UdsClient
from src.security import SecurityProfile, XorKey
from src.cbf import CodingDefinition, CodingBlock, CodingField
from src.coding import CodingSession, Backup


def _demo_definition():
    return CodingDefinition(
        ecu_name="SAM_F",
        blocks=[CodingBlock(
            name="konfor",
            did=0x0100,
            security_level=1,
            fields=[
                CodingField("coming_home", 0, 0, 1,
                            options={0: "kapali", 1: "acik"}),
                CodingField("leaving_home", 0, 1, 1,
                            options={0: "kapali", 1: "acik"}),
                CodingField("flasor_sayisi", 0, 2, 3,
                            description="konfor sinyali yaniş sayisi"),
            ],
        )],
    )


def _session(ecu):
    uds = UdsClient(ecu)
    prof = SecurityProfile().register(1, XorKey(bytes([0, 0, 0, 0])))  # key=seed
    ecu.expected_key = ecu.seed  # XOR 0 => key=seed
    return CodingSession(uds, _demo_definition(), prof, log=lambda m: None)


def test_field_bit_read_write():
    # LSB-first: 0b00011100 -> bit2..4 degeri 0b111 = 7
    f = CodingField("x", 0, 2, 3)
    blk = bytearray([0b00011100])
    assert f.read(blk) == 0b111
    f.write(blk, 0b010)
    assert f.read(blk) == 0b010
    # yazim yalnizca kendi bitlerini etkiler, komsu bitler korunur
    assert blk[0] & 0b00000011 == 0b00000000


def test_unmapped_field_write_is_blocked():
    import pytest
    f = CodingField("gizli", -1, 0, 1)   # eslenmemis
    with pytest.raises(ValueError, match="eslenmemis"):
        f.write(bytearray([0]), 1)


def test_decode_block():
    blk = _demo_definition().blocks[0]
    # LSB-first: bit0=1, bit1=0, bit2..4=101(=5) -> 0b00010101
    raw = bytes([0b00010101])
    d = blk.decode(raw)
    assert d["coming_home"]["label"] == "acik"
    assert d["leaving_home"]["label"] == "kapali"
    assert d["flasor_sayisi"]["value"] == 5


def test_set_fields_unlocks_and_writes_and_verifies():
    ecu = FakeEcu()
    ecu.data[0x0100] = bytes([0x00])
    sess = _session(ecu)
    sess.start()
    ok = sess.set_fields(sess.block_by_name("konfor"),
                         {"coming_home": 1, "flasor_sayisi": 3},
                         verify=True)
    assert ok is True
    assert ecu.unlocked is True
    # yazilan deger: bit0=1 (coming), bit2..4=011 -> 1000 1100? kontrol decode ile
    decoded = sess.decode_block(sess.block_by_name("konfor"))
    assert decoded["coming_home"]["value"] == 1
    assert decoded["flasor_sayisi"]["value"] == 3


def test_backup_restore(tmp_path):
    ecu = FakeEcu()
    ecu.data[0x0100] = bytes([0xAB])
    sess = _session(ecu)
    sess.start()
    path = tmp_path / "backup.json"
    bk = sess.backup(sess.block_by_name("konfor"), str(path))
    assert bk.raw == bytes([0xAB])
    # degistir (0xAB icinde flasor_sayisi=2; 5 yapinca blok degisir)
    sess.set_fields(sess.block_by_name("konfor"), {"flasor_sayisi": 5})
    assert ecu.data[0x0100] != bytes([0xAB])
    # geri yukle
    loaded = Backup.load(str(path))
    sess.restore(loaded)
    assert ecu.data[0x0100] == bytes([0xAB])


def test_definition_json_roundtrip(tmp_path):
    d = _demo_definition()
    p = tmp_path / "def.json"
    d.to_json(str(p))
    d2 = CodingDefinition.from_json(str(p))
    assert d2.ecu_name == "SAM_F"
    assert d2.blocks[0].fields[2].bit_length == 3
    assert d2.blocks[0].fields[0].options[1] == "acik"
