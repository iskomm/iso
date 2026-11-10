"""
CBF <-> arac eslestirme (okuma-only, GUVENLI).

Kullanici kendi CBF dosyalarini bir klasore koyar. Bu modul:
  1. Klasordeki tum CBF/CFF dosyalarini indeksler (beyin adi, versiyon,
     Baumuster, varyantlar).
  2. Araca baglanip beynin KIMLIGINI okur (parca no, yazilim versiyonu,
     VIN, sistem adi) -- sadece okuma, hicbir sey yazilmaz.
  3. Okunan kimlik tokenlarini her CBF ile karsilastirip puanlar ve en
     olasi dogru CBF'i gosterir.

DURUSTLUK: Tam surum/parca eslesmesi (hangi CBF'in tam bu yazilim
surumunu kapsadigi) CBF'in ikili varyant tablosunda saklanir; bu modul
token ortusmesiyle SIRALAR ve araci kimligini yan yana gosterir, boylece
son karari insan verir. Yanlis CBF'i "kesin dogru" diye isaretlemez.
"""

from __future__ import annotations

import os
import re
import glob
from dataclasses import dataclass, field

from .cbf import CbfFile


def normalize_tokens(*texts: str) -> set[str]:
    """Metinlerden eslestirme tokenlari uretir: kelimeler + salt-rakam
    gruplari (parca/surum no karsilastirmasi icin)."""
    toks: set[str] = set()
    for t in texts:
        if not t:
            continue
        t = t.upper()
        for w in re.findall(r"[A-Z0-9]{3,}", t):
            toks.add(w)
        # salt rakam dizisi (bosluk/noktalama kaldirilmis) -- parca/surum no
        digits = re.sub(r"\D", "", t)
        if len(digits) >= 6:
            toks.add(digits)
    return toks


@dataclass
class CbfEntry:
    path: str
    ecu_name: str
    version: str
    baumuster: list[str] = field(default_factory=list)
    variants: list[str] = field(default_factory=list)
    tokens: set[str] = field(default_factory=set)

    @property
    def filename(self) -> str:
        return os.path.basename(self.path)


@dataclass
class MatchResult:
    entry: CbfEntry
    score: float
    reasons: list[str] = field(default_factory=list)


class CbfCatalog:
    """Bir klasordeki CBF dosyalarinin indeksi."""

    def __init__(self, entries: list[CbfEntry] | None = None):
        self.entries = entries or []

    @classmethod
    def from_folder(cls, folder: str) -> "CbfCatalog":
        paths = []
        for ext in ("*.cbf", "*.CBF", "*.cff", "*.CFF"):
            paths += glob.glob(os.path.join(folder, "**", ext), recursive=True)
        return cls.from_paths(sorted(set(paths)))

    @classmethod
    def from_paths(cls, paths: list[str]) -> "CbfCatalog":
        entries = []
        for p in paths:
            try:
                ident = CbfFile(p).identity()
            except Exception:
                continue
            toks = normalize_tokens(ident["ecu_name"], ident["version"],
                                    *ident["baumuster"], *ident["variants"])
            entries.append(CbfEntry(
                path=p, ecu_name=ident["ecu_name"], version=ident["version"],
                baumuster=ident["baumuster"], variants=ident["variants"],
                tokens=toks))
        return cls(entries)

    # -- eslestirme --------------------------------------------------------

    def match(self, car_tokens: set[str], car_baumuster: str = "",
              ecu_hint: str = "") -> list[MatchResult]:
        """Araç kimlik tokenlarini her CBF ile karsilastirir, puanlar.

        car_baumuster: arac serisi (orn. 'BR204') -- varsa guclu sinyal.
        ecu_hint: beklenen beyin adi (orn. 'SAM') -- varsa one cikarir.
        """
        car_tokens = {t.upper() for t in car_tokens}
        bm = car_baumuster.upper().replace(" ", "")
        hint = ecu_hint.upper()
        results = []
        for e in self.entries:
            score = 0.0
            reasons = []
            # Baumuster eslesmesi (en guvenilir otomatik sinyal)
            if bm and bm in [b.upper() for b in e.baumuster]:
                score += 5
                reasons.append(f"Baumuster {bm} destekleniyor")
            # beyin adi ipucu
            if hint and hint in e.ecu_name.upper():
                score += 4
                reasons.append(f"beyin adi '{ecu_hint}' ile eslesiyor")
            # token ortusmesi (parca/surum/varyant)
            common = car_tokens & e.tokens
            if common:
                score += len(common)
                reasons.append(f"ortak token: {', '.join(sorted(common)[:6])}")
            # sayisal surum/parca ortusmesi (alt-dize): arac '060128' <-> CBF
            # '204060128' gibi
            for ct in car_tokens:
                if ct.isdigit() and len(ct) >= 5 and ct not in common:
                    for et in e.tokens:
                        if et.isdigit() and (ct in et or et in ct):
                            score += 1.5
                            reasons.append(f"surum ortak: {ct}")
                            break
            results.append(MatchResult(e, score, reasons))
        results.sort(key=lambda r: r.score, reverse=True)
        return results


# VIN'den Baumuster tahmini (kaba): Mercedes VIN 4-9 arasi model kodunu
# icerir; tam cozum karmasik oldugu icin yaygin W-kasa eslesmeleri verilir.
_VIN_BR = [
    (r"WDD204|WDC204", "BR204"),
    (r"WDD212|WDD207", "BR212"),
    (r"WDD218", "BR218"),
    (r"WDD205|W1K205", "BR205"),
    (r"WDD213|W1K213", "BR213"),
    (r"WDD222", "BR222"),
    (r"WDD176|WDC176", "BR176"),
    (r"W1K177|WDD177", "BR177"),
]


def baumuster_from_vin(vin: str) -> str:
    vin = (vin or "").upper()
    for pat, br in _VIN_BR:
        if re.search(pat, vin):
            return br
    return ""
