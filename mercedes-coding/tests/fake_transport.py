"""ECU taklit eden sahte transport - donanim olmadan UDS testi icin."""
from __future__ import annotations


class FakeEcu:
    """Basit, programlanabilir bir UDS ECU simulatoru."""

    def __init__(self):
        self.session = 0x01
        self.unlocked = False
        self.seed = bytes([0x11, 0x22, 0x33, 0x44])
        self.expected_key: bytes | None = None
        self.data: dict[int, bytes] = {}      # DID -> veri
        self.require_security_for_write = True
        self._pending_response: bytes | None = None
        self.sent: list[bytes] = []
        # 4 byte'lik DTC kayitlari (3 kod + 1 durum)
        self.dtcs: bytes = bytes([0xB1, 0x23, 0x45, 0x08,   # B...  onaylandi
                                  0x40, 0x11, 0x22, 0x01])  # C...  testHatali
        self.routines_run: list[int] = []

    # transport arabirimi
    def send(self, payload: bytes):
        self.sent.append(payload)
        self._pending_response = self._handle(payload)

    def recv(self, timeout_ms: int = 2000):
        r, self._pending_response = self._pending_response, None
        return r

    # UDS mantigi
    def _handle(self, p: bytes) -> bytes | None:
        sid = p[0]
        if sid == 0x10:  # session control
            self.session = p[1]
            return bytes([0x50, p[1], 0x00, 0x32, 0x01, 0xF4])
        if sid == 0x3E:  # tester present
            if len(p) > 1 and p[1] & 0x80:
                return None  # suppressPosResp
            return bytes([0x7E, p[1] & 0x7F])
        if sid == 0x27:  # security access
            level = p[1]
            if level % 2 == 1:  # request seed
                if self.unlocked:
                    return bytes([0x67, level]) + bytes(len(self.seed))
                return bytes([0x67, level]) + self.seed
            else:  # send key
                key = p[2:]
                if self.expected_key is not None and key != self.expected_key:
                    return bytes([0x7F, 0x27, 0x35])  # invalidKey
                self.unlocked = True
                return bytes([0x67, level])
        if sid == 0x22:  # read data by id
            did = (p[1] << 8) | p[2]
            if did in self.data:
                return bytes([0x62, p[1], p[2]]) + self.data[did]
            return bytes([0x7F, 0x22, 0x31])  # out of range
        if sid == 0x2E:  # write data by id
            did = (p[1] << 8) | p[2]
            if self.require_security_for_write and not self.unlocked:
                return bytes([0x7F, 0x2E, 0x33])  # securityAccessDenied
            self.data[did] = p[3:]
            return bytes([0x6E, p[1], p[2]])
        if sid == 0x11:  # ecu reset
            return bytes([0x51, p[1]])
        if sid == 0x14:  # clear DTC
            self.dtcs = b""
            return bytes([0x54])
        if sid == 0x19:  # read DTC
            return bytes([0x59, p[1], 0xFF]) + self.dtcs
        if sid == 0x31:  # routine control
            rid = (p[2] << 8) | p[3]
            if self.require_security_for_write and not self.unlocked:
                return bytes([0x7F, 0x31, 0x33])
            self.routines_run.append(rid)
            return bytes([0x71, p[1], p[2], p[3], 0x00])
        return bytes([0x7F, sid, 0x11])  # serviceNotSupported


class PendingThenOkEcu(FakeEcu):
    """Ilk okumada responsePending (0x78), sonra pozitif cevap verir."""

    def __init__(self):
        super().__init__()
        self._pend_queue: list[bytes] = []

    def send(self, payload: bytes):
        self.sent.append(payload)
        if payload[0] == 0x22:
            # once pending, sonra gercek cevabi kuyrukla
            did = (payload[1] << 8) | payload[2]
            real = (bytes([0x62, payload[1], payload[2]]) + self.data.get(did, b""))
            self._pend_queue = [bytes([0x7F, 0x22, 0x78]), real]
            self._pending_response = None
        else:
            super().send(payload)

    def recv(self, timeout_ms: int = 2000):
        if self._pend_queue:
            return self._pend_queue.pop(0)
        return super().recv(timeout_ms)
