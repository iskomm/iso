import pytest
from fake_transport import FakeEcu, PendingThenOkEcu
from src.uds import UdsClient, Session, UdsNegativeResponse


def test_session_control():
    ecu = FakeEcu()
    uds = UdsClient(ecu)
    resp = uds.diagnostic_session(Session.EXTENDED)
    assert ecu.session == 0x03
    assert resp[0] == 0x03


def test_read_data_by_id_strips_did():
    ecu = FakeEcu()
    ecu.data[0x0100] = bytes([0xAA, 0xBB, 0xCC])
    uds = UdsClient(ecu)
    assert uds.read_data_by_id(0x0100) == bytes([0xAA, 0xBB, 0xCC])


def test_write_denied_without_security():
    ecu = FakeEcu()
    uds = UdsClient(ecu)
    with pytest.raises(UdsNegativeResponse) as e:
        uds.write_data_by_id(0x0100, b"\x01")
    assert e.value.nrc == 0x33  # securityAccessDenied


def test_tester_present_suppressed_has_no_response():
    ecu = FakeEcu()
    uds = UdsClient(ecu)
    uds.tester_present(suppress=True)  # patlamamali


def test_response_pending_is_awaited():
    ecu = PendingThenOkEcu()
    ecu.data[0x0200] = bytes([0x42])
    uds = UdsClient(ecu, p2_timeout_ms=500, p2_star_ms=500)
    assert uds.read_data_by_id(0x0200) == bytes([0x42])


def test_negative_response_raises_with_text():
    ecu = FakeEcu()
    uds = UdsClient(ecu)
    with pytest.raises(UdsNegativeResponse):
        uds.read_data_by_id(0x9999)  # tanimsiz DID -> 0x31
