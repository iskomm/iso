from src.matcher import (CbfCatalog, normalize_tokens, baumuster_from_vin,
                         CbfEntry)


def _write_cbf(tmp_path, name, ecu, ver, variants, brs):
    xml = (f"CBF-<EcuName>{ecu}</EcuName><VersionName>{ver}</VersionName>"
           + "".join(f"<VariantName>{v}</VariantName>" for v in variants)
           + " ".join(brs)).encode("latin-1")
    p = tmp_path / name
    p.write_bytes(xml)
    return str(p)


def test_catalog_identifies_ecus(tmp_path):
    _write_cbf(tmp_path, "ic.cbf", "IC_204", "IC_204.6.1.18",
               ["IC_204_Mid_Line"], ["BR204", "BR212"])
    _write_cbf(tmp_path, "sam.cbf", "SAMR_204", "SAMR_204.3.0.6",
               ["Serie"], ["BR204"])
    cat = CbfCatalog.from_folder(str(tmp_path))
    names = {e.ecu_name for e in cat.entries}
    assert names == {"IC_204", "SAMR_204"}
    ic = next(e for e in cat.entries if e.ecu_name == "IC_204")
    assert "BR204" in ic.baumuster


def test_match_prefers_baumuster_and_hint(tmp_path):
    _write_cbf(tmp_path, "ic204.cbf", "IC_204", "IC_204.6.1.18", [], ["BR204"])
    _write_cbf(tmp_path, "ic205.cbf", "IC_205", "IC_205.1.0.0", [], ["BR205"])
    cat = CbfCatalog.from_folder(str(tmp_path))
    res = cat.match(set(), car_baumuster="BR204", ecu_hint="IC_204")
    assert res[0].entry.ecu_name == "IC_204"
    assert res[0].score > res[1].score


def test_match_by_version_token(tmp_path):
    _write_cbf(tmp_path, "a.cbf", "IC_204", "IC_204.6.1.18", [], ["BR204"])
    _write_cbf(tmp_path, "b.cbf", "IC_204", "IC_204.06.01.28", [], ["BR204"])
    cat = CbfCatalog.from_folder(str(tmp_path))
    # araç yazilimi '06.01.28' versiyonunu bildiriyor -> b.cbf one cikmali
    car = normalize_tokens("Software Version 06 01 28", "A2049021234")
    res = cat.match(car, car_baumuster="BR204")
    assert res[0].entry.version == "IC_204.06.01.28"


def test_baumuster_from_vin():
    assert baumuster_from_vin("WDD2040421A123456") == "BR204"
    assert baumuster_from_vin("WDD2130421F999999") == "BR213"
    assert baumuster_from_vin("XXXX") == ""


def test_normalize_tokens_extracts_digits_and_words():
    toks = normalize_tokens("A 204 902 12 34", "IC_204.6.1.18")
    assert "2049021234" in toks
    assert "204" in toks