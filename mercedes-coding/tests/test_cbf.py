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


def test_extract_metadata_from_embedded_xml(tmp_path):
    payload = (b"CBF-\x00junk"
               b"<EcuName>IC_204</EcuName>"
               b"<VersionName>IC_204.6.1.18</VersionName>"
               b"<VariantName>IC_204_Mid_Line_D1</VariantName>"
               b"<VariantName>IC_204_Entry_D1</VariantName>"
               b"...Variantenkodierung...")
    p = tmp_path / "ic.cbf"
    p.write_bytes(payload)
    meta = CbfFile(str(p)).extract_metadata()
    assert meta["ecu_name"] == "IC_204"
    assert meta["version"] == "IC_204.6.1.18"
    assert "IC_204_Mid_Line_D1" in meta["variants"]
    assert "Variantenkodierung" in meta["coding_classes"]


def test_extract_coding_options(tmp_path):
    payload = (b"x\x00Globale Kodierungen: Night View (NightView)\x00"
               b"y\x00Globale Kodierungen: Distronic (DTR (Distronic))\x00"
               b"z\x00Globale Kodierungen: Steering Variant (Linkslenker) (Rechtslenker)\x00")
    p = tmp_path / "c.cbf"
    p.write_bytes(payload)
    opts = CbfFile(str(p)).extract_coding_options()
    shorts = {o["short"] for o in opts}
    assert "NightView" in shorts
    assert "DTR" in shorts
    labels = {o["label"] for o in opts}
    assert "Night View" in labels
