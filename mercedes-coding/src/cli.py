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
from .library import DefinitionLibrary
from .uds import UdsClient
from .coding import CodingSession, Backup
from .security import SecurityProfile, DllSeedKey, XorKey


def _resolve_definition(args) -> CodingDefinition:
    """--ecu (kutuphaneden) ya da pozitif definition yolundan tanim getirir."""
    if getattr(args, "ecu", None):
        lib = DefinitionLibrary.load()
        d = lib.by_ecu(args.ecu)
        if not d:
            print(f"beyin bulunamadi: {args.ecu}")
            print("mevcut:", ", ".join(x.ecu_name for x in lib.definitions))
            sys.exit(1)
        return d
    return CodingDefinition.from_json(args.definition)


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
    print(f"boyut      : {scan.size} byte   magic: {scan.magic}")
    print(f"BEYIN      : {scan.ecu_name or '(XML yok)'}")
    print(f"versiyon   : {scan.version or '-'}")
    print(f"kodlama    : {', '.join(scan.coding_classes) or '(belirsiz)'}")
    print(f"varyantlar ({len(scan.variants)}):")
    for v in scan.variants[:60]:
        print(f"  - {v}")
    if len(scan.variants) > 60:
        print(f"  ... (+{len(scan.variants) - 60} tane daha)")
    # ComParam etiketleri (CAN ID, baud vb. isimleri)
    cps = [s for s in scan.did_labels if s.startswith("CP_")]
    print(f"\nComParam ({len(cps)}): {', '.join(cps[:20])}")


def cmd_devices(args):
    from .j2534 import find_openport_dll, J2534Error
    try:
        print("OpenPort DLL:", find_openport_dll())
    except J2534Error as e:
        print("hata:", e)
        sys.exit(1)


def cmd_index(args):
    from .matcher import CbfCatalog
    cat = CbfCatalog.from_folder(args.folder)
    print(f"{len(cat.entries)} CBF bulundu:")
    for e in cat.entries:
        print(f"  {e.filename:34s} -> {e.ecu_name or '?':12s} "
              f"v{e.version or '?':14s} BR:{','.join(b[2:] for b in e.baumuster)}")


def cmd_match(args):
    from .matcher import CbfCatalog, baumuster_from_vin
    cat = CbfCatalog.from_folder(args.folder)
    if not cat.entries:
        print("klasorde CBF yok:", args.folder)
        sys.exit(1)
    # araca baglan ve kimligi oku (SADECE OKUMA)
    defn = _resolve_definition(args) if (args.ecu or args.definition) else None
    if defn is None:
        print("araca baglanmak icin --ecu ya da bir tanim gerekli "
              "(CAN ID'leri icin). Yalnizca indeks icin 'index' kullanin.")
        sys.exit(1)
    dev, uds = _connect(defn)
    try:
        sess = CodingSession(uds, defn, _build_security(args), log=_log)
        sess.start()
        info, tokens = sess.read_identity_tokens()
        vin = info.get(f"DID_F190", "")
        br = baumuster_from_vin(vin)
        print(f"\narac kimligi: {info}")
        print(f"Baumuster (VIN'den): {br or '?'}\n")
        results = cat.match(tokens, car_baumuster=br, ecu_hint=args.hint or "")
        print("EN OLASI CBF (puan sirasi):")
        for r in results[:8]:
            print(f"  [{r.score:4.0f}] {r.entry.filename:34s} "
                  f"{r.entry.ecu_name}  — {'; '.join(r.reasons) or '-'}")
        print("\nNOT: Son surum teyidini insan yapmali (tam eslesme CBF ikili "
              "tablosunda).")
    finally:
        dev.close()


def cmd_coding(args):
    cbf = CbfFile(args.file)
    opts = cbf.extract_coding_options()
    print(f"kodlama secenekleri ({len(opts)}) — KATALOG (byte/bit DEGIL):")
    for o in opts:
        al = f"  [{', '.join(o['aliases'])}]" if len(o["aliases"]) > 1 else ""
        print(f"  {o['short']:28s} {o['label']}{al}")
    print("\nNOT: Tam byte/bit konumu icin CaesarSuite ile dogrulayin.")


def cmd_models(args):
    lib = DefinitionLibrary.load()
    for d in lib.definitions:
        feats = ", ".join(f.name for f in d.features) or "-"
        print(f"{d.ecu_name:20s} [{d.platform:5s} {d.ecu_role:14s}] "
              f"ozellik: {feats}")


def cmd_faults(args):
    defn = _resolve_definition(args)
    dev, uds = _connect(defn)
    try:
        sess = CodingSession(uds, defn, _build_security(args), log=_log)
        sess.start()
        if args.clear:
            sess.clear_faults()
        faults = sess.read_faults()
        for d in faults:
            print(f"  {d['code']:<12} [{', '.join(d['flags']) or '-'}]")
        if not faults:
            print("  (temiz)")
    finally:
        dev.close()


def cmd_feature(args):
    defn = _resolve_definition(args)
    feat = defn.feature_by_name(args.name)
    if not feat:
        print(f"ozellik yok: {args.name}")
        print("mevcut:", ", ".join(f.name for f in defn.features))
        sys.exit(1)
    dev, uds = _connect(defn)
    try:
        sess = CodingSession(uds, defn, _build_security(args), log=_log)
        sess.start()
        ok = sess.apply_feature(feat, enable=not args.disable, verify=True,
                                backup_path=args.backup)
        print("SONUC:", "BASARILI" if ok else "DOGRULAMA FARKLI")
        sys.exit(0 if ok else 2)
    finally:
        dev.close()


def cmd_routine(args):
    defn = _resolve_definition(args)
    rout = defn.routine_by_name(args.name)
    if not rout:
        print(f"tanitma yok: {args.name}")
        print("mevcut:", ", ".join(r.name for r in defn.routines))
        sys.exit(1)
    dev, uds = _connect(defn)
    try:
        sess = CodingSession(uds, defn, _build_security(args), log=_log)
        sess.start()
        if args.clear_first:
            sess.clear_and_reteach(rout)
        else:
            sess.run_routine(rout)
        print("SONUC: tamam")
    finally:
        dev.close()


def cmd_read(args):
    defn = _resolve_definition(args)
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
    defn = _resolve_definition(args)
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
    defn = _resolve_definition(args)
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


def _add_target(p):
    """Hedef beyin: ya kutuphaneden --ecu ya da pozitif definition yolu."""
    p.add_argument("definition", nargs="?",
                   help="tanim JSON yolu (--ecu verilirse gerekmez)")
    p.add_argument("--ecu", help="kutuphaneden beyin adi (bkz. 'models')")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mercedes-coding",
                                 description="Mercedes CBF kodlama araci")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="CBF dosyasini incele")
    s.add_argument("file")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("devices", help="OpenPort surucusunu bul")
    s.set_defaults(func=cmd_devices)

    s = sub.add_parser("coding", help="CBF'teki kodlama secenek katalogu")
    s.add_argument("file")
    s.set_defaults(func=cmd_coding)

    s = sub.add_parser("index", help="klasordeki CBF'leri tanimla/indexle")
    s.add_argument("folder")
    s.set_defaults(func=cmd_index)

    s = sub.add_parser("match", help="araca baglanip dogru CBF'i bul (okuma)")
    s.add_argument("folder", help="CBF klasoru")
    s.add_argument("--ecu", help="baglanti icin kutuphane beyni")
    s.add_argument("--def", dest="definition", help="baglanti icin tanim JSON")
    s.add_argument("--hint", help="beklenen beyin adi ipucu (orn. SAM)")
    _add_security_args(s)
    s.set_defaults(func=cmd_match)

    s = sub.add_parser("models", help="kutuphanedeki tum beyinleri listele")
    s.set_defaults(func=cmd_models)

    s = sub.add_parser("read", help="kodlama blogunu oku")
    _add_target(s)
    s.add_argument("--block", required=True)
    _add_security_args(s)
    s.set_defaults(func=cmd_read)

    s = sub.add_parser("set", help="kodlama alanlarini degistir")
    _add_target(s)
    s.add_argument("--block", required=True)
    s.add_argument("--field", action="append", default=[],
                   help="alan=deger (birden fazla olabilir)")
    s.add_argument("--backup", help="yazmadan once yedek dosyasi")
    _add_security_args(s)
    s.set_defaults(func=cmd_set)

    s = sub.add_parser("feature", help="hazir ozellik uygula (orn. amg_menu)")
    _add_target(s)
    s.add_argument("name", help="ozellik adi (orn. amg_menu)")
    s.add_argument("--disable", action="store_true", help="ac yerine kapat")
    s.add_argument("--backup", help="yazmadan once yedek dosyasi")
    _add_security_args(s)
    s.set_defaults(func=cmd_feature)

    s = sub.add_parser("faults", help="arizalari oku (ve istege bagli sil)")
    _add_target(s)
    s.add_argument("--clear", action="store_true", help="once arizalari sil")
    _add_security_args(s)
    s.set_defaults(func=cmd_faults)

    s = sub.add_parser("routine", help="tanitma/kalibrasyon rutini calistir")
    _add_target(s)
    s.add_argument("name", help="rutin adi (orn. far_tanitma)")
    s.add_argument("--clear-first", action="store_true",
                   help="once arizalari sil, sonra tanit")
    _add_security_args(s)
    s.set_defaults(func=cmd_routine)

    s = sub.add_parser("restore", help="yedekten geri yukle")
    s.add_argument("backup", help="yedek JSON dosyasi")
    s.add_argument("--ecu", help="kutuphaneden beyin adi")
    s.add_argument("--def", dest="definition", help="tanim JSON yolu")
    _add_security_args(s)
    s.set_defaults(func=cmd_restore)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
