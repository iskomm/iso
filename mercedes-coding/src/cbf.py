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
    # gomulu Diogenes XML metadata'sindan:
    ecu_name: str = ""
    version: str = ""
    variants: list[str] = field(default_factory=list)
    coding_classes: list[str] = field(default_factory=list)


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
        meta = self.extract_metadata()
        ecu_names = self._guess_ecu_names(strings)
        # XML'den gelen gercek beyin adi varsa one al
        if meta["ecu_name"] and meta["ecu_name"] not in ecu_names:
            ecu_names.insert(0, meta["ecu_name"])
        did_labels = self._guess_did_labels(strings)
        return CbfScan(
            path=self.path,
            size=len(data),
            magic=magic,
            strings=strings,
            ecu_names=ecu_names,
            did_labels=did_labels,
            ecu_name=meta["ecu_name"],
            version=meta["version"],
            variants=meta["variants"],
            coding_classes=meta["coding_classes"],
        )

    def extract_coding_options(self) -> list[dict]:
        """CBF'teki 'Globale Kodierungen' seceneklerini (etiket + kisa ad)
        cikarir. Bu bir KATALOGtur: hangi ozelliklerin kodlanabildigini
        gosterir. DIKKAT: her secenegin tam byte/bit konumu bu listede YOKTUR
        (o bilgi Caesar ikili parametre tablosunda; CaesarSuite ile dogrulanir).
        """
        text = self.data.decode("latin-1", "ignore")
        out, seen = [], set()
        pat = re.compile(r"Globale Kodierungen:\s*([^\x00\r\n]+)")
        for m in pat.finditer(text):
            line = m.group(1).strip()
            if not line or len(line) > 120:
                continue
            mm = re.match(r"(.*?)\s*\((.*)\)\s*$", line)
            if mm:
                label = mm.group(1).strip()
                shorts = re.findall(r"[A-Za-z0-9_]+", mm.group(2))
            else:
                label, shorts = line, []
            key = shorts[0] if shorts else label
            if key in seen:
                continue
            seen.add(key)
            out.append({"label": label, "short": key, "aliases": shorts})
        return out

    def extract_metadata(self) -> dict:
        """CBF'e gomulu Diogenes 'SelectionConfiguration' XML'inden beyin
        adi, versiyon ve varyant listesini cikarir. Bu XML her CBF'de
        bulunur ve beynin gercek kimligini verir."""
        # ikili veri icinde UTF-8 XML pasajlarini metne cevir
        text = self.data.decode("latin-1", "ignore")
        ecu = re.search(r"<EcuName>(.*?)</EcuName>", text)
        ver = re.search(r"<VersionName>(.*?)</VersionName>", text)
        variants = []
        seen = set()
        for m in re.finditer(r"<VariantName>(.*?)</VariantName>", text):
            v = m.group(1).strip()
            if v and v not in seen:
                seen.add(v)
                variants.append(v)
        # kodlama ile ilgili diagnoz siniflari (Variantenkodierung vb.)
        coding = []
        for kw in ("Variantenkodierung", "Variantencodierung", "Codierung",
                   "Kodierung", "VariantCoding"):
            if kw.lower() in text.lower() and kw not in coding:
                coding.append(kw)
        # desteklenen Baumuster (arac serisi): BR204, BR212 ...
        baumuster = sorted(set(re.findall(r"BR\d{3}", text)))
        return {
            "ecu_name": ecu.group(1).strip() if ecu else "",
            "version": ver.group(1).strip() if ver else "",
            "variants": variants,
            "coding_classes": coding,
            "baumuster": baumuster,
        }

    def identity(self) -> dict:
        """Eslestirme icin ozet kimlik: beyin adi, versiyon, Baumuster,
        varyant sayisi. Dosya yolu dahil."""
        m = self.extract_metadata()
        return {
            "path": self.path,
            "ecu_name": m["ecu_name"],
            "version": m["version"],
            "baumuster": m["baumuster"],
            "variants": m["variants"],
        }

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
        """Alani blok icine yazar (yerinde degistirir). LSB-first.

        GUVENLIK: byte_offset < 0 ise alan 'eslenmemis' sayilir (byte/bit
        konumu CBF'ten dogrulanmamis). Boyle bir alana yazim ENGELLENIR,
        cunku yanlis konuma yazmak beyni bozar.
        """
        if self.byte_offset < 0:
            raise ValueError(
                f"{self.name}: alan eslenmemis (byte/bit bilinmiyor). "
                f"Yazim guvenlik geregi engellendi; once CBF'ten dogrula.")
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
class Feature:
    """Tek tikla uygulanan hazir ozellik (orn. 'AMG Menu Aktivasyonu').

    Bir blogun bir ya da birden fazla alanini belirli degerlere ayarlar.
    disable_changes verilirse 'kapat' icin kullanilir; yoksa tum alanlar 0.
    """
    name: str                    # dahili ad: "amg_menu"
    title: str                   # gorunen ad: "AMG Menu Aktivasyonu"
    block: str                   # hangi kodlama blogu
    changes: dict[str, int] = field(default_factory=dict)   # acmak icin
    disable_changes: dict[str, int] = field(default_factory=dict)  # kapatmak
    category: str = "genel"      # gruplama: isik, multimedya, gosterge...
    description: str = ""
    requires_hardware: str = ""  # donanim onsarti notu


@dataclass
class Routine:
    """RoutineControl (0x31) ile calistirilan tanitma/kalibrasyon islemi.

    Orn: beyin degisimi sonrasi 'tanitma', far ayari, konfor normalizasyonu,
    SRS/kemer sifirlamasi haricindeki guvenli rutinler.
    """
    name: str
    title: str
    routine_id: int
    control: int = 0x01          # 0x01 start, 0x02 stop, 0x03 sonuc
    data_hex: str = ""           # rutine gonderilecek ek veri (hex)
    security_level: int = 0
    category: str = "tanitma"
    description: str = ""


@dataclass
class CodingDefinition:
    """Bir beyin icin tam kodlama tanimi. Uygulamanin tukettigi birim."""
    ecu_name: str
    platform: str = ""           # W176, W205, W213, W222, W177 ...
    model_name: str = ""         # gorunen ad: "A-Serisi (W176)"
    vin_patterns: list[str] = field(default_factory=list)  # VIN regex ipuclari
    request_id: int = 0x7E0
    response_id: int = 0x7E8
    baudrate: int = 500000
    extended_id: bool = False
    protocol: str = "UDS"   # "UDS" veya "KWP2000"
    # seedkey: {"level":3, "dll":"yol.dll", "func":"GenerateKeyEx"} veya
    #          {"level":1, "xor_mask":"aabbccdd"}
    seedkey: dict = field(default_factory=dict)
    ecu_role: str = ""           # "far_beyni", "konfor_beyni", "gosterge"...
    blocks: list[CodingBlock] = field(default_factory=list)
    features: list[Feature] = field(default_factory=list)
    routines: list[Routine] = field(default_factory=list)

    def feature_by_name(self, name: str) -> "Feature | None":
        return next((f for f in self.features if f.name == name), None)

    def routine_by_name(self, name: str) -> "Routine | None":
        return next((r for r in self.routines if r.name == name), None)

    def block_by_name(self, name: str) -> "CodingBlock | None":
        return next((b for b in self.blocks if b.name == name), None)

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
        feat_keys = {f.name for f in Feature.__dataclass_fields__.values()}
        rout_keys = {f.name for f in Routine.__dataclass_fields__.values()}
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
        features = [Feature(**_clean(fe, feat_keys))
                    for fe in d.get("features", [])]
        routines = [Routine(**_clean(ro, rout_keys))
                    for ro in d.get("routines", [])]
        d = {**_clean(d, def_keys), "blocks": blocks, "features": features,
             "routines": routines}
        return cls(**d)
