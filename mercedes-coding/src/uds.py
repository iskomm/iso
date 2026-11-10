"""
UDS (ISO 14229) ve kismi KWP2000 istemcisi.

Transport bagimsizdir: send(bytes) ve recv(timeout_ms)->bytes|None saglayan
herhangi bir nesne ile calisir. Gercekte J2534Device, testte FakeTransport.

Negatif cevaplar (0x7F) UdsNegativeResponse olarak firlatilir; 0x78
(responsePending) otomatik olarak beklenir.
"""

from __future__ import annotations

import time
from typing import Protocol


class Transport(Protocol):
    def send(self, payload: bytes) -> None: ...
    def recv(self, timeout_ms: int = 2000) -> bytes | None: ...


# UDS servis kimlikleri
class SID:
    DIAGNOSTIC_SESSION_CONTROL = 0x10
    ECU_RESET = 0x11
    CLEAR_DTC = 0x14
    READ_DTC = 0x19
    READ_DATA_BY_ID = 0x22
    SECURITY_ACCESS = 0x27
    COMMUNICATION_CONTROL = 0x28
    WRITE_DATA_BY_ID = 0x2E
    ROUTINE_CONTROL = 0x31
    TESTER_PRESENT = 0x3E
    # KWP2000 (Mercedes eski beyinler)
    START_DIAGNOSTIC_SESSION = 0x10
    READ_MEMORY_BY_ADDRESS = 0x23


# Oturum tipleri
class Session:
    DEFAULT = 0x01
    PROGRAMMING = 0x02
    EXTENDED = 0x03


# Negatif cevap kodlari (en sik gorulenler)
NRC = {
    0x10: "genel red (generalReject)",
    0x11: "servis desteklenmiyor (serviceNotSupported)",
    0x12: "alt-fonksiyon desteklenmiyor (subFunctionNotSupported)",
    0x13: "mesaj uzunlugu/format hatali",
    0x22: "kosullar uygun degil (conditionsNotCorrect)",
    0x24: "istek sirasi hatali (requestSequenceError)",
    0x31: "istek araligi disinda (requestOutOfRange)",
    0x33: "guvenlik erisimi reddedildi (securityAccessDenied)",
    0x35: "gecersiz anahtar (invalidKey)",
    0x36: "cok fazla deneme (exceedNumberOfAttempts)",
    0x37: "gerekli zaman gecmedi (requiredTimeDelayNotExpired)",
    0x7E: "alt-fonksiyon bu oturumda desteklenmiyor",
    0x7F: "servis bu oturumda desteklenmiyor",
    0x78: "cevap bekleniyor (responsePending)",
}


class UdsError(Exception):
    pass


class UdsNegativeResponse(UdsError):
    def __init__(self, service: int, nrc: int):
        self.service = service
        self.nrc = nrc
        text = NRC.get(nrc, f"bilinmeyen NRC {nrc:#x}")
        super().__init__(f"servis {service:#04x} reddedildi: {text}")


class UdsClient:
    def __init__(self, transport: Transport, p2_timeout_ms: int = 2000,
                 p2_star_ms: int = 5000):
        self.t = transport
        self.p2 = p2_timeout_ms          # normal cevap suresi
        self.p2_star = p2_star_ms        # responsePending sonrasi bekleme

    # -- temel istek/cevap -------------------------------------------------

    def request(self, payload: bytes, expect_response: bool = True) -> bytes:
        """Ham UDS istegi gonderir, pozitif cevabin govdesini dondurur.

        responsePending (7F xx 78) geldiginde p2_star kadar daha bekler.
        expect_response=False ise (orn. suppressPosResp) bos dondurur.
        """
        self.t.send(payload)
        if not expect_response:
            return b""
        service = payload[0]
        deadline = time.monotonic() + self.p2 / 1000.0
        while True:
            remaining = max(1, int((deadline - time.monotonic()) * 1000))
            resp = self.t.recv(remaining)
            if resp is None:
                raise UdsError(f"servis {service:#04x} icin cevap yok (timeout)")
            if resp[0] == 0x7F and len(resp) >= 3:
                nrc = resp[2]
                if nrc == 0x78:  # responsePending: ECU calisiyor, bekle
                    deadline = time.monotonic() + self.p2_star / 1000.0
                    continue
                raise UdsNegativeResponse(service, nrc)
            if resp[0] == service + 0x40:
                return resp[1:]
            # beklenmeyen cerceve: bir sonrakini dene
            if time.monotonic() >= deadline:
                raise UdsError(
                    f"servis {service:#04x}: beklenmeyen cevap {resp.hex()}")

    # -- yuksek seviye servisler ------------------------------------------

    def diagnostic_session(self, session: int) -> bytes:
        return self.request(bytes([SID.DIAGNOSTIC_SESSION_CONTROL, session]))

    def ecu_reset(self, reset_type: int = 0x01) -> bytes:
        return self.request(bytes([SID.ECU_RESET, reset_type]))

    def tester_present(self, suppress: bool = True) -> None:
        sub = 0x80 if suppress else 0x00
        self.request(bytes([SID.TESTER_PRESENT, sub]),
                     expect_response=not suppress)

    def read_data_by_id(self, did: int) -> bytes:
        resp = self.request(bytes([SID.READ_DATA_BY_ID,
                                   (did >> 8) & 0xFF, did & 0xFF]))
        # cevap: DID(2) + veri
        if len(resp) >= 2 and (resp[0] << 8 | resp[1]) == did:
            return resp[2:]
        return resp

    def write_data_by_id(self, did: int, data: bytes) -> bytes:
        return self.request(bytes([SID.WRITE_DATA_BY_ID,
                                   (did >> 8) & 0xFF, did & 0xFF]) + data)

    def routine_control(self, control: int, routine_id: int,
                        data: bytes = b"") -> bytes:
        # control: 0x01 start, 0x02 stop, 0x03 requestResults
        return self.request(bytes([SID.ROUTINE_CONTROL, control,
                                   (routine_id >> 8) & 0xFF,
                                   routine_id & 0xFF]) + data)

    def clear_dtc(self, group: int = 0xFFFFFF) -> bytes:
        return self.request(bytes([SID.CLEAR_DTC,
                                   (group >> 16) & 0xFF,
                                   (group >> 8) & 0xFF, group & 0xFF]))

    def read_dtc(self, sub: int = 0x02, mask: int = 0xFF) -> bytes:
        return self.request(bytes([SID.READ_DTC, sub, mask]))

    # -- security access ---------------------------------------------------

    def request_seed(self, level: int) -> bytes:
        """27 <level> gonderir, seed'i dondurur. level tek sayi olmali."""
        resp = self.request(bytes([SID.SECURITY_ACCESS, level]))
        # resp: echo-level + seed
        return resp[1:] if resp and resp[0] == level else resp

    def send_key(self, level: int, key: bytes) -> bytes:
        """27 <level+1> <key> gonderir. Pozitif cevapta kilit acilmistir."""
        return self.request(bytes([SID.SECURITY_ACCESS, level + 1]) + key)
