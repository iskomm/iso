"""
Tanim kutuphanesi - butun Mercedes platformlari icin tanimlari toplar.

defs/ klasorundeki tum *.json tanimlarini yukler, platform/model/beyin
adina gore indeksler, VIN'den otomatik aday secer ve tum ozellikleri
(AMG menu dahil) kategorilere ayirir.

Uygulama bununla acilista tum modelleri bir dropdown'da gosterebilir;
kullanici modelini secer, OpenPort'a baglanir, ozellikleri uygular.
"""

from __future__ import annotations

import os
import re
import glob

from .cbf import CodingDefinition, Feature


# bu dosyanin yanindaki ../defs klasoru (gomulu kutuphane)
_DEFAULT_DEFS = os.path.join(os.path.dirname(__file__), "..", "defs")


class DefinitionLibrary:
    def __init__(self, definitions: list[CodingDefinition] | None = None):
        self.definitions: list[CodingDefinition] = definitions or []

    # -- yukleme -----------------------------------------------------------

    @classmethod
    def load(cls, root: str | None = None) -> "DefinitionLibrary":
        """defs/ (ve alt klasorleri) altindaki tum JSON tanimlarini yukler."""
        root = os.path.abspath(root or _DEFAULT_DEFS)
        defs = []
        for path in sorted(glob.glob(os.path.join(root, "**", "*.json"),
                                     recursive=True)):
            try:
                defs.append(CodingDefinition.from_json(path))
            except Exception as e:
                # bozuk bir tanim tum kutuphaneyi dusurmesin
                print(f"[uyari] tanim yuklenemedi {path}: {e}")
        return cls(defs)

    # -- sorgular ----------------------------------------------------------

    def platforms(self) -> list[str]:
        seen = []
        for d in self.definitions:
            if d.platform and d.platform not in seen:
                seen.append(d.platform)
        return seen

    def models(self) -> list[tuple[str, CodingDefinition]]:
        """(gorunen ad, tanim) listesi - dropdown icin."""
        out = []
        for d in self.definitions:
            label = d.model_name or f"{d.platform} {d.ecu_name}".strip()
            out.append((f"{label} — {d.ecu_name}", d))
        return out

    def by_ecu(self, ecu_name: str) -> CodingDefinition | None:
        return next((d for d in self.definitions if d.ecu_name == ecu_name), None)

    def for_platform(self, platform: str) -> list[CodingDefinition]:
        return [d for d in self.definitions if d.platform == platform]

    def match_vin(self, vin: str) -> list[CodingDefinition]:
        """VIN'e uyan tanim adaylarini dondurur (vin_patterns regex ile)."""
        vin = (vin or "").upper().strip()
        hits = []
        for d in self.definitions:
            for pat in d.vin_patterns:
                try:
                    if re.search(pat, vin):
                        hits.append(d)
                        break
                except re.error:
                    continue
        return hits

    # -- ozellik katalogu --------------------------------------------------

    def features_by_category(self, defn: CodingDefinition
                             ) -> dict[str, list[Feature]]:
        cats: dict[str, list[Feature]] = {}
        for f in defn.features:
            cats.setdefault(f.category, []).append(f)
        return cats

    def find_feature_everywhere(self, name: str
                                ) -> list[tuple[CodingDefinition, Feature]]:
        """Belirli bir ozelligi (orn. 'amg_menu') destekleyen tum modeller."""
        out = []
        for d in self.definitions:
            f = d.feature_by_name(name)
            if f:
                out.append((d, f))
        return out
