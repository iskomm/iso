"""
Komut satiri arayuzu - GUI olmadan kodlama ve CBF inceleme.

Ornekler:
  python -m src.cli scan araba.cbf
  python -m src.cli devices
  python -m src.cli read  defs/w176_sam.json --block konfor
  python -m src.cli set   defs/w176_sam.json --block konfor \
                          --field coming_home=1 --field flasor_sayisi=3 \
                          --backup yedek.json
  python -m src.cli restore defs/w176_sam.json yedek.json
"""

from __future__ import annotations

import argparse
import sys

from .cbf import CbfFile, CodingDefinition
from .uds import UdsClient
from .coding import CodingSession, Backup
from .security import SecurityProfile, DllSeedKey, XorKey


def _log(m):
    print(m, flush=True)


def _connect(defn: CodingDefinition):
    """Tanimdaki parametrelerle OpenPort uzerinden UdsClient kurar."""
    from .j2534 import J2534Device, CanConfig
    dev = J2534Device().open()
    dev.connect(CanConfig(request_id=defn.request_id,
                          response_id=defn.response_id,
                          baudrate=defn.baudrate,
                          extended_id=defn.extended_id))
    return dev, UdsClient(dev)


def _build_security(args) -> SecurityProfile:
    prof = SecurityProfile()
    if args.seedkey_dll:
        # orn: --seedkey-dll yol.dll --seedkey-func GenerateKeyEx --level 3
        prof.register(args.level, DllSeedKey(args.seedkey_dll,
                                             args.seedkey_func))
    if args.xor_mask:
        prof.register(args.level, XorKey(bytes.fromhex(args.xor_mask)))
    return prof


def cmd_scan(args):
    scan = CbfFile(args.file).scan()
    print(f"dosya      : {scan.path}")
    print(f"boyut      : {scan.size} byte")
    print(f"magic      : {scan.magic}")
    print(f"beyinler   : {', '.join(scan.ecu_names) or '(bulunamadi)'}")
    print(f"kodlama etiketleri ({len(scan.did_labels)}):")
    for s in scan.did_labels[:40]:
        print(f"  - {s}")


def cmd_devices(args):
    from .j2534 import find_openport_dll, J2534Error
    try:
        print("OpenPort DLL:", find_openport_dll())
    except J2534Error as e:
        print("hata:", e)
        sys.exit(1)


def cmd_read(args):
    defn = CodingDefinition.from_json(args.definition)
    dev, uds = _connect(defn)
    try:
        sess = CodingSession(uds, defn, _build_security(args), log=_log)
        sess.start()
        block = sess.block_by_name(args.block)
        decoded = sess.decode_block(block)
        print(f"\n== {block.name} (DID {block.did:#06x}) ==")
        for name, info in decoded.items():
            print(f"  {name:24s} = {info['value']:<6} {info['label']}")
    finally:
        dev.close()


def cmd_set(args):
    defn = CodingDefinition.from_json(args.definition)
    changes = {}
    for item in args.field:
        k, v = item.split("=", 1)
        changes[k] = int(v, 0)
    dev, uds = _connect(defn)
    try:
        sess = CodingSession(uds, defn, _build_security(args), log=_log)
        sess.start()
        block = sess.block_by_name(args.block)
        ok = sess.set_fields(block, changes, verify=True,
                             backup_path=args.backup)
        print("SONUC:", "BASARILI" if ok else "DOGRULAMA BASARISIZ")
        sys.exit(0 if ok else 2)
    finally:
        dev.close()


def cmd_restore(args):
    defn = CodingDefinition.from_json(args.definition)
    bk = Backup.load(args.backup)
    dev, uds = _connect(defn)
    try:
        sess = CodingSession(uds, defn, _build_security(args), log=_log)
        sess.start()
        ok = sess.restore(bk, verify=True)
        print("SONUC:", "BASARILI" if ok else "DOGRULAMA BASARISIZ")
        sys.exit(0 if ok else 2)
    finally:
        dev.close()


def _add_security_args(p):
    p.add_argument("--level", type=int, default=1,
                   help="security access seviyesi (27 <level>)")
    p.add_argument("--seedkey-dll", help="Mercedes orijinal seed/key DLL yolu")
    p.add_argument("--seedkey-func", default="GenerateKeyEx",
                   help="DLL icindeki anahtar uretme fonksiyonu")
    p.add_argument("--xor-mask", help="basit XOR algoritmasi icin hex maske")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mercedes-coding",
                                 description="Mercedes CBF kodlama araci")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="CBF dosyasini incele")
    s.add_argument("file")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("devices", help="OpenPort surucusunu bul")
    s.set_defaults(func=cmd_devices)

    s = sub.add_parser("read", help="kodlama blogunu oku")
    s.add_argument("definition")
    s.add_argument("--block", required=True)
    _add_security_args(s)
    s.set_defaults(func=cmd_read)

    s = sub.add_parser("set", help="kodlama alanlarini degistir")
    s.add_argument("definition")
    s.add_argument("--block", required=True)
    s.add_argument("--field", action="append", default=[],
                   help="alan=deger (birden fazla olabilir)")
    s.add_argument("--backup", help="yazmadan once yedek dosyasi")
    _add_security_args(s)
    s.set_defaults(func=cmd_set)

    s = sub.add_parser("restore", help="yedekten geri yukle")
    s.add_argument("definition")
    s.add_argument("backup")
    _add_security_args(s)
    s.set_defaults(func=cmd_restore)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
