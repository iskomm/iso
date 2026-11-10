"""
J2534 PassThru arabirimi - OpenPort 2.0 (Tactrix) icin.

Bu modul SADECE Windows'ta ve 32-bit Python'da calisir cunku OpenPort
surucusu (op20pt32.dll) 32-bittir. Linux/test ortaminda import edilebilsin
diye DLL yuklemesi tembel (lazy) yapilir; gercek yukleme connect() sirasinda
olur.

UDS/KWP katmani bu siniftan bagimsizdir: asagidaki J2534Transport nesnesi
sadece send(bytes)/recv(timeout) saglar. Boylece uds.py donanim olmadan da
test edilebilir (bkz. tests/test_uds.py icindeki FakeTransport).
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass

# ---- J2534 sabitleri (SAE J2534-1) ---------------------------------------

# Protokoller
CAN = 5
ISO15765 = 6
ISO9141 = 3
ISO14230 = 4  # KWP2000 (K-Line)

# Filtre tipleri
PASS_FILTER = 1
BLOCK_FILTER = 2
FLOW_CONTROL_FILTER = 3

# TxFlags
ISO15765_FRAME_PAD = 0x00000040
CAN_29BIT_ID = 0x00000100

# RxStatus bitleri
TX_MSG_TYPE = 0x00000001          # loopback / gonderim onayi
START_OF_MESSAGE = 0x00000002     # ISO15765 ilk-cerceve bildirimi

# Connect flags
CAN_ID_BOTH = 0x00000800

# IOCTL
SET_CONFIG = 0x05
CLEAR_RX_BUFFER = 0x08
CLEAR_TX_BUFFER = 0x09

# Hata kodlari
STATUS_NOERROR = 0x00
ERR_BUFFER_EMPTY = 0x10
ERR_TIMEOUT = 0x11


class J2534Error(Exception):
    """J2534 API cagrisi basarisiz oldugunda firlatilir."""


# ctypes yapilari ve DLL yuklemesi yalnizca gercekten gerekince kurulur,
# boylece Linux CI'da import patlamaz.
def _load_ctypes():
    import ctypes
    from ctypes import c_ulong, c_long, c_void_p, c_char_p, POINTER, Structure

    class PASSTHRU_MSG(Structure):
        _fields_ = [
            ("ProtocolID", c_ulong),
            ("RxStatus", c_ulong),
            ("TxFlags", c_ulong),
            ("Timestamp", c_ulong),
            ("DataSize", c_ulong),
            ("ExtraDataIndex", c_ulong),
            ("Data", ctypes.c_ubyte * 4128),
        ]

    class SCONFIG(Structure):
        _fields_ = [("Parameter", c_ulong), ("Value", c_ulong)]

    class SCONFIG_LIST(Structure):
        _fields_ = [("NumOfParams", c_ulong), ("ConfigPtr", POINTER(SCONFIG))]

    return ctypes, c_ulong, c_long, c_void_p, c_char_p, POINTER, PASSTHRU_MSG, SCONFIG, SCONFIG_LIST


def find_openport_dll():
    """Windows registry'den OpenPort J2534 DLL yolunu bulur.

    PassThruSupport.04.04 altindaki kayitlari tarar, adinda 'openport'
    gecen ilk cihazin FunctionLibrary degerini dondurur.
    """
    if sys.platform != "win32":
        raise J2534Error("J2534 yalnizca Windows'ta kullanilabilir")
    import winreg

    for root in (r"SOFTWARE\WOW6432Node\PassThruSupport.04.04",
                 r"SOFTWARE\PassThruSupport.04.04"):
        try:
            base = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root)
        except OSError:
            continue
        count = winreg.QueryInfoKey(base)[0]
        for i in range(count):
            sub = winreg.OpenKey(base, winreg.EnumKey(base, i))
            try:
                name = winreg.QueryValueEx(sub, "Name")[0]
                lib = winreg.QueryValueEx(sub, "FunctionLibrary")[0]
            except OSError:
                continue
            if "openport" in name.lower() or "tactrix" in name.lower():
                return lib
    raise J2534Error("OpenPort/Tactrix J2534 surucusu bulunamadi")


@dataclass
class CanConfig:
    """Bir ECU ile ISO-TP (ISO15765) iletisim parametreleri.

    request_id / response_id degerleri CBF'deki ComParam'lardan gelir
    (CP_REQUEST_CANIDENTIFIER, CP_RESPONSE_CANIDENTIFIER). Tahmin etme.
    """
    request_id: int = 0x7E0
    response_id: int = 0x7E8
    baudrate: int = 500000
    extended_id: bool = False      # 29-bit CAN ID
    pad_frames: bool = True        # cerceveleri 8 byte'a tamamla


class J2534Device:
    """OpenPort 2.0 ile tek bir ISO15765 kanali uzerinden konusur."""

    def __init__(self, dll_path: str | None = None):
        self.dll_path = dll_path
        self._j = None
        self._ct = None
        self._PMSG = None
        self._SCONFIG = None
        self._SCONFIG_LIST = None
        self.device_id = None
        self.channel_id = None
        self.cfg: CanConfig | None = None

    # -- yasam dongusu -----------------------------------------------------

    def open(self):
        (self._ct, c_ulong, c_long, c_void_p, c_char_p, POINTER,
         self._PMSG, self._SCONFIG, self._SCONFIG_LIST) = _load_ctypes()
        path = self.dll_path or find_openport_dll()
        self._j = self._ct.WinDLL(path)
        dev = c_ulong(0)
        self._check(self._j.PassThruOpen(None, self._ct.byref(dev)), "PassThruOpen")
        self.device_id = dev.value
        return self

    def close(self):
        if self._j is None:
            return
        try:
            if self.channel_id is not None:
                self._j.PassThruDisconnect(self.channel_id)
            if self.device_id is not None:
                self._j.PassThruClose(self.device_id)
        finally:
            self.channel_id = None
            self.device_id = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    # -- kanal kurulumu ----------------------------------------------------

    def connect(self, cfg: CanConfig):
        """ISO15765 kanali acar ve flow-control filtresini kurar."""
        self.cfg = cfg
        ct = self._ct
        flags = CAN_29BIT_ID if cfg.extended_id else 0
        ch = ct.c_ulong(0)
        self._check(
            self._j.PassThruConnect(self.device_id, ISO15765, flags,
                                    cfg.baudrate, ct.byref(ch)),
            "PassThruConnect")
        self.channel_id = ch.value
        self._set_flow_control_filter()
        self.clear_buffers()
        return self

    def _set_flow_control_filter(self):
        ct = self._ct
        cfg = self.cfg
        mask = self._msg(b"\xff\xff\xff\xff")
        patt = self._msg(self._id_bytes(cfg.response_id))
        flow = self._msg(self._id_bytes(cfg.request_id))
        fid = ct.c_ulong(0)
        self._check(
            self._j.PassThruStartMsgFilter(self.channel_id, FLOW_CONTROL_FILTER,
                                           ct.byref(mask), ct.byref(patt),
                                           ct.byref(flow), ct.byref(fid)),
            "PassThruStartMsgFilter")

    def clear_buffers(self):
        self._j.PassThruIoctl(self.channel_id, CLEAR_RX_BUFFER, None, None)
        self._j.PassThruIoctl(self.channel_id, CLEAR_TX_BUFFER, None, None)

    # -- dusuk seviye mesaj yardimcilari -----------------------------------

    def _id_bytes(self, can_id: int) -> bytes:
        return can_id.to_bytes(4, "big")

    def _msg(self, data: bytes):
        m = self._PMSG()
        m.ProtocolID = ISO15765
        m.TxFlags = ISO15765_FRAME_PAD if (self.cfg and self.cfg.pad_frames) else 0
        if self.cfg and self.cfg.extended_id:
            m.TxFlags |= CAN_29BIT_ID
        m.DataSize = len(data)
        for i, b in enumerate(data):
            m.Data[i] = b
        return m

    def _check(self, rc, where):
        if rc != STATUS_NOERROR:
            raise J2534Error(f"{where} basarisiz (kod={rc:#x})")

    # -- Transport arabirimi (uds.py bunu kullanir) ------------------------

    def send(self, payload: bytes):
        """UDS/KWP istek verisini (servis + parametreler) ECU'ya gonderir.

        CAN ID basa eklenir; ISO-TP segmentasyonunu DLL yapar.
        """
        ct = self._ct
        data = self._id_bytes(self.cfg.request_id) + payload
        m = self._msg(data)
        n = ct.c_ulong(1)
        self._check(
            self._j.PassThruWriteMsgs(self.channel_id, ct.byref(m),
                                      ct.byref(n), 1000),
            "PassThruWriteMsgs")

    def recv(self, timeout_ms: int = 2000) -> bytes | None:
        """Bir UDS/KWP cevabi okur. Loopback ve first-frame bildirimleri atlanir.

        Donen deger: CAN ID'si cikarilmis saf payload (orn. 50 03 ...).
        Zaman asiminda None.
        """
        ct = self._ct
        deadline = time.monotonic() + timeout_ms / 1000.0
        while time.monotonic() < deadline:
            m = self._PMSG()
            n = ct.c_ulong(1)
            rc = self._j.PassThruReadMsgs(self.channel_id, ct.byref(m),
                                          ct.byref(n), 100)
            if rc == ERR_BUFFER_EMPTY or rc == ERR_TIMEOUT or n.value == 0:
                continue
            self._check(rc, "PassThruReadMsgs")
            # TX onayi (loopback) ve ISO-TP ilk-cerceve bildirimi: atla
            if m.RxStatus & TX_MSG_TYPE:
                continue
            if m.RxStatus & START_OF_MESSAGE:
                continue
            if m.DataSize <= 4:
                continue
            return bytes(m.Data[4:m.DataSize])
        return None
