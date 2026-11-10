import struct
from src.cbf import CbfFile, CodingDefinition


def _fake_cbf(tmp_path):
    # Gercekci olmayan ama okunabilir stringler iceren sahte bir CBF
    payload = (b"\xef\xdd\x00\x01"
               b"SAM_F\x00some junk\x00KI222\x00"
               b"VARIANT_CODING\x00CP_REQUEST_CANIDENTIFIER\x00"
               b"COMING_HOME_OPTION\x00\x01\x02\x03random")
    p = tmp_path / "test.cbf"
    p.write_bytes(payload)
    return str(p)


def test_scan_finds_ecu_names(tmp_path):
    scan = CbfFile(_fake_cbf(tmp_path)).scan()
    assert "SAM_F" in scan.ecu_names
    assert "KI222" in scan.ecu_names


def test_scan_finds_coding_labels(tmp_path):
    scan = CbfFile(_fake_cbf(tmp_path)).scan()
    labels = " ".join(scan.did_labels)
    assert "VARIANT_CODING" in labels
    assert "CP_REQUEST_CANIDENTIFIER" in labels


def test_scan_reports_size_and_magic(tmp_path):
    path = _fake_cbf(tmp_path)
    scan = CbfFile(path).scan()
    assert scan.size > 0
    assert scan.magic.startswith("efdd")
