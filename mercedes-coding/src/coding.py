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
from .cbf import CodingDefinition, CodingBlock, Feature, Routine

# Standart tanimlama DID'leri (ISO 14229-1 Annex C)
DID_VIN = 0xF190
DID_PART_NUMBER = 0xF187
DID_SW_VERSION = 0xF189
DID_SYSTEM_NAME = 0xF197


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

    # -- tanimlama (VIN / parca no) ---------------------------------------

    def _read_ascii_did(self, did: int) -> str:
        try:
            raw = self.uds.read_data_by_id(did)
            return raw.decode("ascii", "ignore").strip("\x00 ").strip()
        except Exception as e:
            self.log(f"DID {did:#06x} okunamadi: {e}")
            return ""

    def read_vin(self) -> str:
        return self._read_ascii_did(DID_VIN)

    def identify(self) -> dict:
        """Bagli beynin kimligini okur: VIN, parca no, yazilim, sistem adi."""
        info = {
            "vin": self._read_ascii_did(DID_VIN),
            "part_number": self._read_ascii_did(DID_PART_NUMBER),
            "sw_version": self._read_ascii_did(DID_SW_VERSION),
            "system_name": self._read_ascii_did(DID_SYSTEM_NAME),
        }
        self.log(f"kimlik: {info}")
        return info

    # Eslestirme icin okunan genis kimlik DID kumesi (ISO + Daimler araligi)
    IDENTITY_DIDS = [DID_VIN, DID_PART_NUMBER, DID_SW_VERSION, DID_SYSTEM_NAME,
                     0xF191, 0xF18C, 0xF18A, 0xF195, 0xF150, 0xF151, 0xF153]

    def read_identity_tokens(self) -> tuple[dict, set]:
        """CBF eslestirmesi icin beynin kimlik DID'lerini okur (SADECE OKUMA).

        Doner: (okunabilir bilgi sozlugu, eslestirme token kumesi).
        """
        from .matcher import normalize_tokens
        info = {}
        texts = []
        for did in self.IDENTITY_DIDS:
            val = self._read_ascii_did(did)
            if val:
                info[f"DID_{did:04X}"] = val
                texts.append(val)
        tokens = normalize_tokens(*texts)
        self.log(f"arac kimlik tokenlari ({len(tokens)}): "
                 f"{', '.join(sorted(tokens)[:10])}")
        return info, tokens

    # -- hazir ozellik uygulama (AMG menu vb.) ----------------------------

    # -- ariza oku / sil ---------------------------------------------------

    def read_faults(self) -> list[dict]:
        """Bagli beynin arizalarini okunabilir listeyle dondurur."""
        dtcs = self.uds.read_dtcs()
        if not dtcs:
            self.log("ariza yok (temiz)")
        for d in dtcs:
            self.log(f"  {d['code']}  [{', '.join(d['flags']) or '-'}]")
        return dtcs

    def clear_faults(self) -> None:
        self.uds.clear_dtc()
        self.log("arizalar silindi (14 FF FF FF)")

    # -- tanitma / kalibrasyon rutinleri ----------------------------------

    def run_routine(self, routine: Routine) -> bytes:
        """Bir tanitma/kalibrasyon rutinini calistirir (RoutineControl 0x31)."""
        self.ensure_security(routine.security_level)
        data = bytes.fromhex(routine.data_hex) if routine.data_hex else b""
        self.log(f"tanitma calistiriliyor: {routine.title} "
                 f"(rid {routine.routine_id:#06x})")
        resp = self.uds.routine_control(routine.control, routine.routine_id, data)
        self.log(f"  sonuc: {resp.hex() or '(bos pozitif)'}")
        return resp

    def clear_and_reteach(self, routine: Routine) -> bytes:
        """Once arizalari siler, sonra tanitma rutinini calistirir.

        Beyin/parca degisimi sonrasi tipik akis: temizle + tanit.
        """
        self.clear_faults()
        res = self.run_routine(routine)
        # tanitmadan sonra tekrar oku ki kalan ariza gorunurse bilinsin
        self.read_faults()
        return res

    # -- hazir ozellik uygulama (AMG menu vb.) ----------------------------

    def apply_feature(self, feature: Feature, enable: bool = True,
                      verify: bool = True, backup_path: str | None = None
                      ) -> bool:
        """Bir Feature'i tek cagrida uygular (ac/kapat).

        enable=True ise feature.changes, False ise feature.disable_changes
        (bos ise tum ilgili alanlar 0) yazilir.
        """
        block = self.block_by_name(feature.block)
        if enable:
            changes = dict(feature.changes)
        elif feature.disable_changes:
            changes = dict(feature.disable_changes)
        else:
            changes = {k: 0 for k in feature.changes}
        self.log(f"ozellik {'AC' if enable else 'KAPAT'}: {feature.title}")
        if feature.requires_hardware:
            self.log(f"  donanim onsarti: {feature.requires_hardware}")
        return self.set_fields(block, changes, verify=verify,
                               backup_path=backup_path)

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
