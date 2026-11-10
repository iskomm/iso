"""
Yuksek seviye kodlama motoru: CBF/tanim + UDS + security'yi birlestirir.

Akis:
  oturum ac -> (gerekirse security unlock) -> kodlama blogunu OKU ->
  YEDEKLE -> alanlari degistir -> YAZ -> ECU reset -> DOGRULA.

Her yazimdan once otomatik yedek alinir; geri yukleme tek cagri.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from .uds import UdsClient, Session
from .security import SecurityProfile, unlock
from .cbf import CodingDefinition, CodingBlock


@dataclass
class Backup:
    ecu_name: str
    did: int
    timestamp: str
    raw_hex: str

    def save(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: str) -> "Backup":
        with open(path, encoding="utf-8") as f:
            return cls(**json.load(f))

    @property
    def raw(self) -> bytes:
        return bytes.fromhex(self.raw_hex)


class CodingSession:
    def __init__(self, uds: UdsClient, definition: CodingDefinition,
                 security: SecurityProfile | None = None,
                 log: Callable[[str], None] = print):
        self.uds = uds
        self.defn = definition
        self.security = security or SecurityProfile()
        self.log = log
        self._unlocked_levels: set[int] = set()

    # -- oturum ------------------------------------------------------------

    def start(self, session: int = Session.EXTENDED):
        self.log(f"oturum aciliyor: {session:#04x}")
        self.uds.diagnostic_session(session)
        self.uds.tester_present()

    def ensure_security(self, level: int):
        if level <= 0 or level in self._unlocked_levels:
            return
        self.log(f"security seviye {level} aciliyor...")
        unlock(self.uds, self.security, level, self.log)
        self._unlocked_levels.add(level)

    # -- blok bulma --------------------------------------------------------

    def block_by_name(self, name: str) -> CodingBlock:
        for b in self.defn.blocks:
            if b.name == name:
                return b
        raise KeyError(f"kodlama blogu bulunamadi: {name}")

    # -- oku ---------------------------------------------------------------

    def read_block(self, block: CodingBlock) -> bytes:
        self.ensure_security(block.security_level)
        raw = self.uds.read_data_by_id(block.did)
        self.log(f"okundu {block.name} (DID {block.did:#06x}): {raw.hex()}")
        return raw

    def decode_block(self, block: CodingBlock) -> dict:
        raw = self.read_block(block)
        return block.decode(raw)

    # -- yedekle -----------------------------------------------------------

    def backup(self, block: CodingBlock, path: str | None = None) -> Backup:
        raw = self.read_block(block)
        bk = Backup(ecu_name=self.defn.ecu_name, did=block.did,
                    timestamp=datetime.now().isoformat(timespec="seconds"),
                    raw_hex=raw.hex())
        if path:
            bk.save(path)
            self.log(f"yedek kaydedildi: {path}")
        return bk

    # -- yaz + dogrula -----------------------------------------------------

    def write_block(self, block: CodingBlock, new_raw: bytes,
                    verify: bool = True, reset: bool = True) -> bool:
        self.ensure_security(block.security_level)
        self.log(f"yaziliyor {block.name}: {new_raw.hex()}")
        self.uds.write_data_by_id(block.did, new_raw)
        if reset:
            self.log("ECU reset (11 01)...")
            try:
                self.uds.ecu_reset(0x01)
            except Exception as e:  # bazi beyinler reset'e cevap vermez
                self.log(f"reset uyarisi: {e}")
            time.sleep(1.0)
            self.start()
        if verify:
            readback = self.read_block(block)
            ok = readback == new_raw
            self.log("DOGRULAMA: " + ("OK" if ok else "FARKLI!"))
            return ok
        return True

    def set_fields(self, block: CodingBlock, changes: dict[str, int],
                   verify: bool = True, backup_path: str | None = None) -> bool:
        """Mevcut blogu okur, verilen alanlari degistirir, yazar.

        changes: {alan_adi: yeni_ham_deger}
        """
        current = bytearray(self.read_block(block))
        if backup_path:
            Backup(self.defn.ecu_name, block.did,
                   datetime.now().isoformat(timespec="seconds"),
                   bytes(current).hex()).save(backup_path)
            self.log(f"yedek: {backup_path}")
        field_map = {f.name: f for f in block.fields}
        for name, value in changes.items():
            if name not in field_map:
                raise KeyError(f"alan yok: {name}")
            field_map[name].write(current, value)
            self.log(f"  {name} <- {value}")
        return self.write_block(block, bytes(current), verify=verify)

    def restore(self, backup: Backup, verify: bool = True) -> bool:
        block = next((b for b in self.defn.blocks if b.did == backup.did), None)
        if block is None:
            raise KeyError(f"DID {backup.did:#06x} tanimda yok")
        self.log(f"geri yukleniyor {block.name} <- yedek {backup.timestamp}")
        return self.write_block(block, backup.raw, verify=verify)
