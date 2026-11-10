"""
Security Access (UDS 0x27) seed/key cercevesi.

ONEMLI: Mercedes'in gercek, beyne-ozel seed/key algoritmalari CBF
dosyasinin ICINDE DEGILDIR; genelde ayri imzali DLL'lerde (SGE/seed-key
kutuphaneleri) bulunur. Bu yuzden dogru mimari su:

  1. SeedKeyAlgorithm arabirimi (seed -> key).
  2. Saf-Python ornek/jenerik algoritmalar (test edilebilir, bazi eski
     beyinlerde ise yarar; cogunda yalnizca sablondur).
  3. DllSeedKey: Mercedes'in orijinal seed/key DLL'ini yukleyip onun
     GenerateKey fonksiyonunu cagirir. GERCEK kullanim yolu budur.

Her algoritma bir "level" (27 01, 27 03, 27 05 ...) ile eslesebilir;
boylece farkli security seviyeleri desteklenir.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Callable


class SeedKeyError(Exception):
    pass


class SeedKeyAlgorithm:
    """Taban sinif: seed (bytes) -> key (bytes)."""
    name = "base"

    def compute(self, seed: bytes, level: int) -> bytes:
        raise NotImplementedError

    def __call__(self, seed: bytes, level: int = 1) -> bytes:
        return self.compute(seed, level)


# -- ornek / jenerik algoritmalar (test edilebilir) ------------------------

class ConstantKey(SeedKeyAlgorithm):
    """Sadece test icin: sabit anahtar dondurur."""
    name = "constant"

    def __init__(self, key: bytes):
        self.key = key

    def compute(self, seed: bytes, level: int) -> bytes:
        return self.key


class XorKey(SeedKeyAlgorithm):
    """key = seed XOR mask. Basit beyinlerde gorulen sablon."""
    name = "xor"

    def __init__(self, mask: bytes):
        self.mask = mask

    def compute(self, seed: bytes, level: int) -> bytes:
        if len(self.mask) != len(seed):
            raise SeedKeyError("mask uzunlugu seed ile ayni olmali")
        return bytes(s ^ m for s, m in zip(seed, self.mask))


class AddConstantKey(SeedKeyAlgorithm):
    """key = (seed_as_int + sabit) mod 2^(8*n). Yaygin bir KWP sablonu."""
    name = "add"

    def __init__(self, constant: int):
        self.constant = constant

    def compute(self, seed: bytes, level: int) -> bytes:
        n = len(seed)
        val = (int.from_bytes(seed, "big") + self.constant) % (1 << (8 * n))
        return val.to_bytes(n, "big")


class LfsrRotateKey(SeedKeyAlgorithm):
    """Klasik shift-register tabanli sablon (bazi eski Mercedes KWP beyinleri
    bu aileye benzer bir donusum kullanir). Her tur icin:
        key = rotl(seed ^ k1, r) + k2  (32-bit)
    Parametreler beyne gore degisir; dogru degerler bilinmiyorsa DllSeedKey
    kullanin. Burada deterministik ve test edilebilir bir ornek sunulur.
    """
    name = "lfsr"

    def __init__(self, k1: int = 0x5A5A5A5A, k2: int = 0x3F1C,
                 rounds: int = 5, rot: int = 7):
        self.k1, self.k2, self.rounds, self.rot = k1, k2, rounds, rot

    @staticmethod
    def _rotl32(v: int, r: int) -> int:
        r &= 31
        return ((v << r) | (v >> (32 - r))) & 0xFFFFFFFF

    def compute(self, seed: bytes, level: int) -> bytes:
        v = int.from_bytes(seed[:4].ljust(4, b"\x00"), "big")
        for _ in range(self.rounds):
            v = self._rotl32(v ^ self.k1, self.rot)
            v = (v + self.k2) & 0xFFFFFFFF
        return v.to_bytes(4, "big")


# -- Mercedes orijinal DLL kopru -------------------------------------------

class DllSeedKey(SeedKeyAlgorithm):
    """Harici seed/key DLL'ini (Mercedes orijinal algoritmasi) yukler.

    OEM/J2534 uygulamalarinda yaygin imza:
        int GenerateKeyEx(unsigned char* seed, unsigned int seedLen,
                          const char* secParam,
                          unsigned char* key, unsigned int* keyLen)
    Donus 0 = basari. Fonksiyon adi DLL'e gore degisebilir, o yuzden
    parametre olarak alinir.
    """
    name = "dll"

    def __init__(self, dll_path: str, func_name: str = "GenerateKeyEx",
                 sec_param: bytes = b""):
        self.dll_path = dll_path
        self.func_name = func_name
        self.sec_param = sec_param
        self._fn = None

    def _load(self):
        if sys.platform != "win32":
            raise SeedKeyError("seed/key DLL yalnizca Windows'ta yuklenebilir")
        import ctypes
        from ctypes import c_int, c_uint, c_char_p, c_void_p, POINTER, byref
        dll = ctypes.WinDLL(self.dll_path)
        fn = getattr(dll, self.func_name)
        fn.restype = c_int
        fn.argtypes = [c_void_p, c_uint, c_char_p, c_void_p, POINTER(c_uint)]
        self._fn = fn
        self._ctypes = (ctypes, c_uint, byref)

    def compute(self, seed: bytes, level: int) -> bytes:
        if self._fn is None:
            self._load()
        ctypes, c_uint, byref = self._ctypes
        seed_buf = (ctypes.c_ubyte * len(seed)).from_buffer_copy(seed)
        key_buf = (ctypes.c_ubyte * 32)()
        key_len = c_uint(len(key_buf))
        rc = self._fn(seed_buf, len(seed), self.sec_param, key_buf,
                      byref(key_len))
        if rc != 0:
            raise SeedKeyError(f"{self.func_name} hata dondurdu (kod={rc})")
        return bytes(key_buf[:key_len.value])


# -- seviye -> algoritma kaydi ---------------------------------------------

@dataclass
class SecurityProfile:
    """Bir ECU icin security seviyelerini ve algoritmalarini tutar.

    Ornek: {1: XorKey(...), 3: DllSeedKey(...)} -> 27 01 ve 27 03 destekli.
    """
    algorithms: dict[int, SeedKeyAlgorithm] = field(default_factory=dict)

    def register(self, level: int, algo: SeedKeyAlgorithm):
        self.algorithms[level] = algo
        return self

    def key_for(self, level: int, seed: bytes) -> bytes:
        if level not in self.algorithms:
            raise SeedKeyError(f"seviye {level} icin algoritma tanimli degil")
        return self.algorithms[level].compute(seed, level)


def unlock(uds_client, profile: SecurityProfile, level: int = 1,
           log: Callable[[str], None] = lambda m: None) -> bool:
    """Tam seed/key el sikismasi: 27<level> -> hesapla -> 27<level+1>.

    seed tamamen sifirsa ECU zaten acik demektir; True doner.
    Pozitif cevap gelirse True, aksi halde UdsNegativeResponse yukselir.
    """
    seed = uds_client.request_seed(level)
    log(f"seed ({len(seed)} byte): {seed.hex()}")
    if all(b == 0 for b in seed):
        log("ECU zaten acik (seed=0)")
        return True
    key = profile.key_for(level, seed)
    log(f"key: {key.hex()}")
    uds_client.send_key(level, key)
    log(f"security seviye {level} acildi")
    return True
