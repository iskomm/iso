"""
CBF (Caesar) dosya okuyucu + kodlama tanim modeli.

DURUSTLUK NOTU
--------------
CBF/CFF, Mercedes DAS/Vediamo'nun kullandigi, bit-bayrakli ve ic ice
bloklu, KARMASIK bir ikili formattir. Tam semantik ayristirma (tum
variant'lar, servisler, presentation/scaling formulleri) devasa bir istir;
en iyi acik referans jglim/CaesarSuite'tir.

Bu modul iki seviye sunar:

  1. CbfFile: en-iyi-caba yapisal tarama. Dosya basligini, string havuzunu
     ve okunabilir isimleri (beyin adi, varyant, DID etiketleri) cikarir.
     Hangi beyin/varyant oldugunu tanimak ve DID adaylarini gormek icin
     yeterli, ama tam servis cozumu GARANTI DEGIL.

  2. CodingDefinition: uygulamanin ASIL tukettigi tanim. CaesarSuite ile
     export edilebilen ya da elle yazilabilen, net bir JSON semasi. Kodlama
     okuma/yazma bunun uzerinden guvenle yapilir (bkz. coding.py).

Boylece uygulama CBF ayristirmasi eksik olsa bile hemen kullanilabilir.
"""

from __future__ import annotations

import json
import re
import struct
from dataclasses import dataclass, field, asdict


# ============================ 1. CBF ikili tarama ==========================

# Caesar/CBF dosyalari genelde su imza ile baslar (kucuk-endian sihir).
_CBF_MAGICS = (b"\xef\xdd", b"CBF", b"CFF")

_PRINTABLE = re.compile(rb"[ -~]{3,}")  # en az 3 karakterlik ASCII dizisi


@dataclass
class CbfScan:
    path: str
    size: int
    magic: str
    strings: list[str] = field(default_factory=list)
    ecu_names: list[str] = field(default_factory=list)
    did_labels: list[str] = field(default_factory=list)


class CbfFile:
    """CBF dosyasini bellege alir ve yapisal ipuclari cikarir."""

    def __init__(self, path: str):
        self.path = path
        with open(path, "rb") as f:
            self.data = f.read()

    def scan(self) -> CbfScan:
        data = self.data
        magic = data[:4].hex()
        strings = self._extract_strings()
        ecu_names = self._guess_ecu_names(strings)
        did_labels = self._guess_did_labels(strings)
        return CbfScan(
            path=self.path,
            size=len(data),
            magic=magic,
            strings=strings,
            ecu_names=ecu_names,
            did_labels=did_labels,
        )

    def _extract_strings(self) -> list[str]:
        out, seen = [], set()
        for m in _PRINTABLE.finditer(self.data):
            s = m.group().decode("ascii", "ignore").strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out

    @staticmethod
    def _guess_ecu_names(strings: list[str]) -> list[str]:
        # Mercedes beyin kisaltmalari: KI, SAM, EZS, HU, ME, CDI, ESP ...
        pat = re.compile(r"^(KI|SAM|EZS|HU|ME|CDI|ESP|EGS|ISM|OCP|PSM|TCM|ECM"
                         r"|DCM|AAM|SRS|ETC|GW|CGW)[0-9A-Z_\-]*$")
        return [s for s in strings if pat.match(s)]

    @staticmethod
    def _guess_did_labels(strings: list[str]) -> list[str]:
        # Kodlama/konfig ile ilgili olasi etiketler
        kw = ("CODING", "VARIANT", "CONFIG", "KONFIG", "KODIER", "PARAM",
              "OPTION", "SA_", "CP_", "DID")
        return [s for s in strings if any(k in s.upper() for k in kw)]


# ====================== 2. Kodlama tanim modeli ============================

@dataclass
class CodingField:
    """Kodlama bloğu icindeki tek bir ayarlanabilir alan.

    byte_offset/bit_offset: blok icindeki konum.
    bit_length: alanin bit uzunlugu.
    options: ham deger -> okunur etiket (orn. {0:"kapali", 1:"acik"}).
    """
    name: str
    byte_offset: int
    bit_offset: int = 0
    bit_length: int = 1
    description: str = ""
    options: dict[int, str] = field(default_factory=dict)

    def read(self, block: bytes) -> int:
        """Ham blok icinden bu alanin tam sayi degerini cikarir.

        Konvansiyon: LSB-first. bit_offset=0 -> byte_offset'teki byte'in en
        dusuk anlamli biti. Alanin ilk biti sonucun en dusuk anlamli bitidir;
        alan byte sinirini asarsa sonraki byte'in LSB'sinden devam eder.
        """
        val = 0
        for i in range(self.bit_length):
            bit = self.bit_offset + i
            byte_i = self.byte_offset + (bit // 8)
            bit_i = bit % 8
            b = block[byte_i] if byte_i < len(block) else 0
            val |= ((b >> bit_i) & 1) << i
        return val

    def write(self, block: bytearray, value: int) -> None:
        """Alani blok icine yazar (yerinde degistirir). LSB-first."""
        if value >= (1 << self.bit_length):
            raise ValueError(f"{self.name}: deger {self.bit_length} bite sigmaz")
        for i in range(self.bit_length):
            bit = self.bit_offset + i
            byte_i = self.byte_offset + (bit // 8)
            bit_i = bit % 8
            while byte_i >= len(block):
                block.append(0)
            src_bit = (value >> i) & 1
            if src_bit:
                block[byte_i] |= (1 << bit_i)
            else:
                block[byte_i] &= ~(1 << bit_i) & 0xFF


@dataclass
class CodingBlock:
    """Bir DID (ya da KWP local-id) ile okunan/yazilan kodlama blogu."""
    name: str
    did: int
    read_sid: int = 0x22
    write_sid: int = 0x2E
    security_level: int = 0   # 0 = gerekmiyor; >0 ise once unlock
    length: int = 0
    fields: list[CodingField] = field(default_factory=list)

    def decode(self, block: bytes) -> dict:
        return {f.name: self._label(f, f.read(block)) for f in self.fields}

    @staticmethod
    def _label(f: CodingField, val: int):
        return {"value": val, "label": f.options.get(val, str(val))}


@dataclass
class CodingDefinition:
    """Bir beyin icin tam kodlama tanimi. Uygulamanin tukettigi birim."""
    ecu_name: str
    request_id: int = 0x7E0
    response_id: int = 0x7E8
    baudrate: int = 500000
    extended_id: bool = False
    protocol: str = "UDS"   # "UDS" veya "KWP2000"
    # seedkey: {"level":3, "dll":"yol.dll", "func":"GenerateKeyEx"} veya
    #          {"level":1, "xor_mask":"aabbccdd"}
    seedkey: dict = field(default_factory=dict)
    blocks: list[CodingBlock] = field(default_factory=list)

    # -- JSON serilestirme -------------------------------------------------

    def to_json(self, path: str | None = None) -> str:
        txt = json.dumps(asdict(self), indent=2, ensure_ascii=False)
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(txt)
        return txt

    @classmethod
    def from_json(cls, path: str) -> "CodingDefinition":
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        field_keys = {f.name for f in CodingField.__dataclass_fields__.values()}
        block_keys = {f.name for f in CodingBlock.__dataclass_fields__.values()}
        def_keys = {f.name for f in cls.__dataclass_fields__.values()}

        def _clean(src: dict, allowed: set) -> dict:
            # "_" ile baslayan yorum anahtarlarini ve bilinmeyenleri at
            return {k: v for k, v in src.items() if k in allowed}

        blocks = []
        for b in d.get("blocks", []):
            fields = []
            for fd in b.get("fields", []):
                fd = _clean(fd, field_keys)
                fd["options"] = {int(k): v
                                 for k, v in fd.get("options", {}).items()}
                fields.append(CodingField(**fd))
            b = {**_clean(b, block_keys), "fields": fields}
            blocks.append(CodingBlock(**b))
        d = {**_clean(d, def_keys), "blocks": blocks}
        return cls(**d)
