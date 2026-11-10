from fake_transport import FakeEcu
from src.uds import UdsClient, decode_dtc
from src.security import SecurityProfile, XorKey
from src.cbf import CodingDefinition, Routine
from src.coding import CodingSession


def test_decode_dtc_letter_and_flags():
    d = decode_dtc(bytes([0xB1, 0x23, 0x45, 0x08]))
    assert d["code"].startswith("B")
    assert "onaylandi" in d["flags"]
    assert d["raw"] == "b12345"


def test_read_faults_parses_multiple():
    ecu = FakeEcu()
    uds = UdsClient(ecu)
    faults = uds.read_dtcs()
    assert len(faults) == 2
    assert faults[0]["code"].startswith("B")
    assert faults[1]["code"].startswith("C")


def test_clear_faults():
    ecu = FakeEcu()
    uds = UdsClient(ecu)
    assert len(uds.read_dtcs()) == 2
    uds.clear_dtc()
    assert uds.read_dtcs() == []


def _session(ecu):
    uds = UdsClient(ecu)
    prof = SecurityProfile().register(1, XorKey(bytes([0, 0, 0, 0])))
    ecu.expected_key = ecu.seed
    defn = CodingDefinition(
        ecu_name="W176_Headlight", platform="W176",
        routines=[Routine(name="far_tanitma", title="Far Tanitma",
                          routine_id=0x0F20, control=1, security_level=1)])
    return CodingSession(uds, defn, prof, log=lambda m: None)


def test_run_routine_requires_security_then_runs():
    ecu = FakeEcu()
    sess = _session(ecu)
    sess.start()
    r = sess.defn.routine_by_name("far_tanitma")
    sess.run_routine(r)
    assert 0x0F20 in ecu.routines_run
    assert ecu.unlocked is True


def test_clear_and_reteach_flow():
    ecu = FakeEcu()
    sess = _session(ecu)
    sess.start()
    r = sess.defn.routine_by_name("far_tanitma")
    sess.clear_and_reteach(r)
    assert ecu.dtcs == b""          # once silindi
    assert 0x0F20 in ecu.routines_run  # sonra tanitildi
