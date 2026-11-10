from src.library import DefinitionLibrary


def test_library_loads_platforms():
    lib = DefinitionLibrary.load()
    assert len(lib.definitions) >= 20
    for p in ("W176", "W177", "W205", "W213", "W222"):
        assert p in lib.platforms()


def test_every_platform_has_amg_menu():
    lib = DefinitionLibrary.load()
    hits = {d.platform for d, f in lib.find_feature_everywhere("amg_menu")}
    assert {"W176", "W177", "W205", "W213", "W222"} <= hits


def test_each_platform_has_far_ve_konfor_beyni():
    lib = DefinitionLibrary.load()
    for p in ("W176", "W205", "W222"):
        roles = {d.ecu_role for d in lib.for_platform(p)}
        assert "far_beyni" in roles
        assert "konfor_beyni" in roles
        assert "gosterge" in roles


def test_far_beyni_has_tanitma_routine():
    lib = DefinitionLibrary.load()
    d = lib.by_ecu("W205_Headlight")
    assert d is not None
    assert any(r.name == "far_tanitma" for r in d.routines)


def test_vin_autodetect():
    lib = DefinitionLibrary.load()
    hits = lib.match_vin("WDD2050421F123456")
    assert any(d.platform == "W205" for d in hits)
