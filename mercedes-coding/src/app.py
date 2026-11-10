"""
Mercedes-Benz Kodlama Uygulamasi - Tkinter GUI (direkt calisan uygulama).

Acilista gomulu tanim kutuphanesini (defs/) yukler; butun Mercedes
platformlari bir listede gelir. Kullanici:
  1. Modelini secer (ya da 'VIN ile Tani' ile otomatik)
  2. OpenPort'a baglanir, oturum acar
  3. OZELLIKLER sekmesinden tek tikla ozellik uygular (AMG Menu dahil)
  4. ya da GELISMIS sekmesinden blok/alan bazli okur-yazar

Is mantigi CodingSession/DefinitionLibrary icinde; GUI incedir.
Baslatma:  python -m src.app   (ya da kokteki mercedes_coding.py)
"""

from __future__ import annotations

import threading
import traceback

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except Exception:
    tk = None

from .library import DefinitionLibrary
from .uds import UdsClient, Session
from .coding import CodingSession, Backup
from .security import SecurityProfile, XorKey, DllSeedKey
from .cbf import CbfFile


class App:
    def __init__(self, root):
        self.root = root
        root.title("Mercedes-Benz Kodlama — OpenPort 2.0")
        root.geometry("960x720")

        self.library = DefinitionLibrary.load()
        self.device = None
        self.session: CodingSession | None = None
        self.defn = None
        self.current_block = None
        self.field_vars: dict[str, tk.StringVar] = {}

        self._build_top()
        self._build_tabs()
        self._build_log()
        self._refresh_models()

    # ---- ust panel: model secimi + baglanti ------------------------------

    def _build_top(self):
        top = ttk.Frame(self.root, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="Model:").pack(side="left")
        self.model_combo = ttk.Combobox(top, state="readonly", width=42)
        self.model_combo.pack(side="left", padx=4)
        self.model_combo.bind("<<ComboboxSelected>>", lambda e: self._select_model())

        ttk.Button(top, text="Baglan", command=self.connect).pack(side="left", padx=2)
        ttk.Button(top, text="Oturum Ac", command=self.start_session).pack(side="left", padx=2)
        ttk.Button(top, text="VIN ile Tani", command=self.identify).pack(side="left", padx=2)
        ttk.Button(top, text="CBF Tara", command=self.scan_cbf).pack(side="left", padx=2)
        ttk.Button(top, text="Tanim Yukle", command=self.load_external).pack(side="left", padx=2)

        self.status = ttk.Label(top, text="● bagli degil", foreground="#b00")
        self.status.pack(side="right")

    def _build_tabs(self):
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=6, pady=4)

        # --- Ozellikler sekmesi (tek tik) ---
        self.feat_tab = ttk.Frame(self.nb)
        self.nb.add(self.feat_tab, text="Özellikler")
        self.feat_canvas = tk.Canvas(self.feat_tab, highlightthickness=0)
        self.feat_inner = ttk.Frame(self.feat_canvas)
        sb = ttk.Scrollbar(self.feat_tab, orient="vertical",
                           command=self.feat_canvas.yview)
        self.feat_canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.feat_canvas.pack(side="left", fill="both", expand=True)
        self.feat_canvas.create_window((0, 0), window=self.feat_inner, anchor="nw")
        self.feat_inner.bind("<Configure>", lambda e: self.feat_canvas.configure(
            scrollregion=self.feat_canvas.bbox("all")))

        # --- CBF Eslestir sekmesi (okuma-only) ---
        self.mtab = ttk.Frame(self.nb)
        self.nb.add(self.mtab, text="CBF Eşleştir")
        mbar = ttk.Frame(self.mtab, padding=4)
        mbar.pack(fill="x")
        ttk.Button(mbar, text="CBF Klasörü Seç", command=self.pick_cbf_folder).pack(side="left", padx=2)
        ttk.Button(mbar, text="Araçtan Oku & Eşleştir", command=self.match_car).pack(side="left", padx=2)
        ttk.Label(mbar, text="  ipucu:").pack(side="left")
        self.hint_entry = ttk.Entry(mbar, width=12)
        self.hint_entry.pack(side="left")
        self.match_text = tk.Text(self.mtab, height=16, font=("Courier", 9))
        self.match_text.pack(fill="both", expand=True, padx=6, pady=4)
        self._catalog = None

        # --- Ariza & Tanitma sekmesi ---
        self.dtc_tab = ttk.Frame(self.nb)
        self.nb.add(self.dtc_tab, text="Arıza & Tanıtma")
        dbar = ttk.Frame(self.dtc_tab, padding=4)
        dbar.pack(fill="x")
        ttk.Button(dbar, text="Arızaları Oku", command=self.read_faults).pack(side="left", padx=2)
        ttk.Button(dbar, text="Arızaları Sil", command=self.clear_faults).pack(side="left", padx=2)
        ttk.Button(dbar, text="Sil + Tekrar Tanıt", command=self.clear_and_reteach).pack(side="left", padx=2)
        ttk.Label(dbar, text="  Tanıtma:").pack(side="left")
        self.routine_combo = ttk.Combobox(dbar, state="readonly", width=34)
        self.routine_combo.pack(side="left", padx=2)
        ttk.Button(dbar, text="Çalıştır", command=self.run_routine).pack(side="left", padx=2)
        self.dtc_list = tk.Text(self.dtc_tab, height=14, font=("Courier", 10))
        self.dtc_list.pack(fill="both", expand=True, padx=6, pady=4)

        # --- Gelismis sekmesi (blok/alan) ---
        self.adv_tab = ttk.Frame(self.nb)
        self.nb.add(self.adv_tab, text="Gelişmiş (blok/alan)")
        bar = ttk.Frame(self.adv_tab, padding=4)
        bar.pack(fill="x")
        ttk.Label(bar, text="Blok:").pack(side="left")
        self.block_combo = ttk.Combobox(bar, state="readonly", width=24)
        self.block_combo.pack(side="left", padx=4)
        ttk.Button(bar, text="Oku", command=self.read_block).pack(side="left", padx=2)
        ttk.Button(bar, text="Yaz", command=self.write_block).pack(side="left", padx=2)
        ttk.Button(bar, text="Security Aç", command=self.unlock).pack(side="left", padx=2)
        ttk.Button(bar, text="Yedekle", command=self.backup).pack(side="left", padx=2)
        ttk.Button(bar, text="Geri Yükle", command=self.restore).pack(side="left", padx=2)
        ttk.Button(bar, text="DTC Oku", command=self.read_dtc).pack(side="left", padx=2)
        ttk.Button(bar, text="DTC Sil", command=self.clear_dtc).pack(side="left", padx=2)
        self.fields_frame = ttk.Frame(self.adv_tab, padding=6)
        self.fields_frame.pack(fill="both", expand=True)

    def _build_log(self):
        wrap = ttk.LabelFrame(self.root, text="Log", padding=4)
        wrap.pack(fill="both", expand=False, padx=6, pady=4)
        self.log_text = tk.Text(wrap, height=9, wrap="none", font=("Courier", 9))
        self.log_text.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(wrap, command=self.log_text.yview)
        sb.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=sb.set)

    # ---- yardimcilar -----------------------------------------------------

    def log(self, msg):
        self.log_text.insert("end", str(msg) + "\n")
        self.log_text.see("end")
        self.root.update_idletasks()

    def _run(self, fn):
        def wrapper():
            try:
                fn()
            except Exception as e:
                self.log(f"HATA: {e}")
                self.log(traceback.format_exc())
                messagebox.showerror("Hata", str(e))
        threading.Thread(target=wrapper, daemon=True).start()

    def _refresh_models(self):
        self._models = self.library.models()
        self.model_combo["values"] = [label for label, _ in self._models]
        if self._models:
            self.model_combo.current(0)
            self._select_model()

    def _select_model(self):
        idx = self.model_combo.current()
        if idx < 0:
            return
        self.defn = self._models[idx][1]
        self.block_combo["values"] = [b.name for b in self.defn.blocks]
        if self.defn.blocks:
            self.block_combo.current(0)
        self._routines = list(self.defn.routines)
        self.routine_combo["values"] = [r.title for r in self._routines]
        if self._routines:
            self.routine_combo.current(0)
        self.log(f"model/beyin: {self.defn.model_name or ''} "
                 f"[{self.defn.ecu_name} / {self.defn.ecu_role or '-'}]")
        self._render_features()
        # yeni model secilince mevcut oturumu sifirla
        self.session = None
        self.status.config(text="● bagli degil (model degisti)", foreground="#b00")

    def _security_profile(self) -> SecurityProfile:
        prof = SecurityProfile()
        sk = getattr(self.defn, "seedkey", {}) or {}
        lvl = sk.get("level", 1)
        if sk.get("dll"):
            prof.register(lvl, DllSeedKey(sk["dll"], sk.get("func", "GenerateKeyEx")))
        elif sk.get("xor_mask"):
            prof.register(lvl, XorKey(bytes.fromhex(sk["xor_mask"])))
        return prof

    def _need_session(self) -> bool:
        if not self.session:
            messagebox.showwarning("Uyari", "Önce Bağlan + Oturum Aç yapın.")
            return False
        return True

    # ---- OZELLIKLER sekmesi ---------------------------------------------

    def _render_features(self):
        for w in self.feat_inner.winfo_children():
            w.destroy()
        if not self.defn or not self.defn.features:
            ttk.Label(self.feat_inner,
                      text="Bu model için tanımlı özellik yok.").pack(anchor="w")
            return
        cats = self.library.features_by_category(self.defn)
        for cat, feats in cats.items():
            box = ttk.LabelFrame(self.feat_inner, text=cat.upper(), padding=6)
            box.pack(fill="x", padx=6, pady=4, anchor="n")
            for f in feats:
                row = ttk.Frame(box)
                row.pack(fill="x", pady=2)
                title = f.title
                if f.name == "amg_menu":
                    title = "★ " + title
                ttk.Label(row, text=title, width=34,
                          font=("TkDefaultFont", 9, "bold")).pack(side="left")
                ttk.Button(row, text="Aç",
                           command=lambda ff=f: self._apply_feature(ff, True)
                           ).pack(side="left", padx=2)
                ttk.Button(row, text="Kapat",
                           command=lambda ff=f: self._apply_feature(ff, False)
                           ).pack(side="left", padx=2)
                if f.description:
                    ttk.Label(row, text=f.description, foreground="#555",
                              wraplength=420).pack(side="left", padx=8)

    def _apply_feature(self, feature, enable):
        if not self._need_session():
            return
        action = "açılacak" if enable else "kapatılacak"
        if not messagebox.askyesno(
                "Onay",
                f"'{feature.title}' {action}. ECU'ya yazılacak ve otomatik "
                f"yedek alınacak.\n\nUYARI: Değerler kendi CBF'inizle "
                f"doğrulanmalıdır. Devam edilsin mi?"):
            return

        def job():
            path = filedialog.asksaveasfilename(
                title="Yazmadan önce yedek", defaultextension=".json",
                filetypes=[("JSON", "*.json")])
            ok = self.session.apply_feature(feature, enable=enable,
                                            verify=True, backup_path=path or None)
            self.log("SONUÇ: " + ("BAŞARILI" if ok else "DOĞRULAMA FARKLI"))
            self.root.after(0, lambda: messagebox.showinfo(
                "Sonuç", f"{feature.title}: " +
                ("tamam" if ok else "doğrulama farklı — logu inceleyin")))
        self._run(job)

    # ---- baglanti / oturum ----------------------------------------------

    def connect(self):
        if not self.defn:
            messagebox.showwarning("Uyari", "Önce model seçin.")
            return

        def job():
            from .j2534 import J2534Device, CanConfig
            self.device = J2534Device().open()
            self.device.connect(CanConfig(
                request_id=self.defn.request_id,
                response_id=self.defn.response_id,
                baudrate=self.defn.baudrate,
                extended_id=self.defn.extended_id))
            uds = UdsClient(self.device)
            self.session = CodingSession(uds, self.defn,
                                         self._security_profile(), log=self.log)
            self.status.config(text="● bağlı", foreground="#070")
            self.log("OpenPort bağlandı")
        self._run(job)

    def start_session(self):
        if self._need_session():
            self._run(lambda: self.session.start(Session.EXTENDED))

    def identify(self):
        if not self._need_session():
            return

        def job():
            info = self.session.identify()
            vin = info.get("vin", "")
            self.log(f"VIN: {vin or '(okunamadı)'}")
            hits = self.library.match_vin(vin) if vin else []
            if hits:
                target = hits[0]
                labels = [lbl for lbl, d in self._models if d is target]
                if labels:
                    self.root.after(0, lambda: self.model_combo.set(labels[0]))
                    self.log(f"otomatik eşleşme: {target.model_name}")
            else:
                self.log("VIN ile otomatik eşleşme bulunamadı; modeli elle seçin.")
        self._run(job)

    def scan_cbf(self):
        path = filedialog.askopenfilename(filetypes=[("CBF", "*.cbf *.cff"),
                                                     ("Tüm", "*.*")])
        if not path:
            return
        scan = CbfFile(path).scan()
        self.log(f"CBF: {scan.size} byte, magic={scan.magic}")
        self.log(f"beyinler: {', '.join(scan.ecu_names) or '(yok)'}")
        for s in scan.did_labels[:30]:
            self.log(f"   {s}")

    def load_external(self):
        from .cbf import CodingDefinition
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        d = CodingDefinition.from_json(path)
        self.library.definitions.append(d)
        self._refresh_models()
        self.log(f"dış tanım eklendi: {d.ecu_name}")

    # ---- CBF Eslestir (okuma-only) --------------------------------------

    def pick_cbf_folder(self):
        from .matcher import CbfCatalog
        folder = filedialog.askdirectory(title="CBF dosyalarının olduğu klasör")
        if not folder:
            return
        def job():
            self._catalog = CbfCatalog.from_folder(folder)
            self.match_text.delete("1.0", "end")
            self.match_text.insert("end", f"{len(self._catalog.entries)} CBF tanındı:\n\n")
            for e in self._catalog.entries:
                brs = ",".join(b[2:] for b in e.baumuster)
                self.match_text.insert(
                    "end", f"  {e.ecu_name or '?':12s} v{e.version or '?':16s} "
                           f"BR:{brs}\n     {e.filename}\n")
        self._run(job)

    def match_car(self):
        if not self._need_session():
            return
        if not self._catalog:
            messagebox.showinfo("Bilgi", "Önce CBF klasörü seçin.")
            return
        from .matcher import baumuster_from_vin
        def job():
            info, tokens = self.session.read_identity_tokens()
            vin = info.get("DID_F190", "")
            br = baumuster_from_vin(vin)
            hint = self.hint_entry.get().strip()
            results = self._catalog.match(tokens, car_baumuster=br, ecu_hint=hint)
            def show():
                self.match_text.delete("1.0", "end")
                self.match_text.insert("end", "ARAÇ KİMLİĞİ (okundu, yazılmadı):\n")
                for k, v in info.items():
                    self.match_text.insert("end", f"  {k}: {v}\n")
                self.match_text.insert("end", f"  Baumuster (VIN): {br or '?'}\n\n")
                self.match_text.insert("end", "EN OLASI DOĞRU CBF (puan sırası):\n")
                for r in results[:8]:
                    self.match_text.insert(
                        "end", f"  [{r.score:4.0f}] {r.entry.ecu_name:10s} "
                               f"v{r.entry.version}\n       {r.entry.filename}\n"
                               f"       → {'; '.join(r.reasons) or '-'}\n")
                self.match_text.insert(
                    "end", "\nNOT: Son sürüm teyidini sen yap (tam eşleşme CBF "
                           "ikili tablosunda).\n")
            self.root.after(0, show)
        self._run(job)

    # ---- Ariza & Tanitma -------------------------------------------------

    def _show_dtcs(self, faults):
        self.dtc_list.delete("1.0", "end")
        hdr = f"=== {self.defn.ecu_name} ({self.defn.ecu_role or '-'}) ===\n"
        self.dtc_list.insert("end", hdr)
        if not faults:
            self.dtc_list.insert("end", "Arıza yok (temiz).\n")
            return
        for d in faults:
            durum = ", ".join(d["flags"]) or "-"
            isaret = "●" if d["active"] else "○"
            self.dtc_list.insert("end", f"{isaret} {d['code']:<12} [{durum}]\n")

    def read_faults(self):
        if not self._need_session():
            return
        def job():
            faults = self.session.read_faults()
            self.root.after(0, lambda: self._show_dtcs(faults))
        self._run(job)

    def clear_faults(self):
        if not self._need_session():
            return
        if not messagebox.askyesno("Onay", "Bu beynin arızaları silinsin mi?"):
            return
        def job():
            self.session.clear_faults()
            self.root.after(0, lambda: self._show_dtcs(self.session.read_faults()))
        self._run(job)

    def _selected_routine(self):
        i = self.routine_combo.current()
        return self._routines[i] if 0 <= i < len(self._routines) else None

    def run_routine(self):
        if not self._need_session():
            return
        r = self._selected_routine()
        if not r:
            messagebox.showinfo("Bilgi", "Bu beyin için tanıtma tanımlı değil.")
            return
        if not messagebox.askyesno("Onay", f"'{r.title}' çalıştırılsın mı?"):
            return
        self._run(lambda: self.session.run_routine(r))

    def clear_and_reteach(self):
        if not self._need_session():
            return
        r = self._selected_routine()
        if not r:
            messagebox.showinfo("Bilgi", "Bu beyin için tanıtma tanımlı değil.")
            return
        if not messagebox.askyesno(
                "Onay", f"Arızalar silinip '{r.title}' çalıştırılacak. Devam?"):
            return
        def job():
            self.session.clear_and_reteach(r)
            self.root.after(0, lambda: self._show_dtcs(self.session.read_faults()))
        self._run(job)

    # ---- gelismis: blok/alan --------------------------------------------

    def unlock(self):
        if not self._need_session() or not self.current_block:
            messagebox.showinfo("Bilgi", "Önce blok okuyun.")
            return
        lvl = self.current_block.security_level or (self.defn.seedkey or {}).get("level", 1)
        self._run(lambda: self.session.ensure_security(lvl))

    def read_block(self):
        if not self._need_session():
            return
        name = self.block_combo.get()
        if not name:
            return

        def job():
            block = self.session.block_by_name(name)
            self.current_block = block
            decoded = self.session.decode_block(block)
            self.root.after(0, lambda: self._render_fields(block, decoded))
        self._run(job)

    def _render_fields(self, block, decoded):
        for w in self.fields_frame.winfo_children():
            w.destroy()
        self.field_vars.clear()
        for r, f in enumerate(block.fields):
            ttk.Label(self.fields_frame, text=f.name, width=26).grid(
                row=r, column=0, sticky="w", pady=1)
            var = tk.StringVar(value=str(decoded[f.name]["value"]))
            self.field_vars[f.name] = var
            if f.options:
                labels = [f"{k} - {v}" for k, v in sorted(f.options.items())]
                cb = ttk.Combobox(self.fields_frame, values=labels,
                                  state="readonly", width=26)
                cur = decoded[f.name]["value"]
                cb.set(f"{cur} - {f.options.get(cur, cur)}")
                cb.grid(row=r, column=1, sticky="w")
                cb.bind("<<ComboboxSelected>>",
                        lambda e, v=var, c=cb: v.set(c.get().split(" - ")[0]))
            else:
                ttk.Entry(self.fields_frame, textvariable=var, width=28).grid(
                    row=r, column=1, sticky="w")
            if f.description:
                ttk.Label(self.fields_frame, text=f.description,
                          foreground="#666").grid(row=r, column=2, sticky="w", padx=6)

    def write_block(self):
        if not self._need_session() or not self.current_block:
            return
        if not messagebox.askyesno("Onay", "Seçili değerler ECU'ya yazılacak. Devam?"):
            return
        changes = {name: int(var.get(), 0) for name, var in self.field_vars.items()}

        def job():
            path = filedialog.asksaveasfilename(
                title="Yazmadan önce yedek", defaultextension=".json",
                filetypes=[("JSON", "*.json")])
            ok = self.session.set_fields(self.current_block, changes,
                                         verify=True, backup_path=path or None)
            self.log("YAZIM: " + ("OK" if ok else "DOĞRULAMA FARKLI"))
        self._run(job)

    def backup(self):
        if not self._need_session() or not self.current_block:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("JSON", "*.json")])
        if path:
            self._run(lambda: self.session.backup(self.current_block, path))

    def restore(self):
        if not self._need_session():
            return
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if path:
            self._run(lambda: self.session.restore(Backup.load(path)))

    def read_dtc(self):
        if self._need_session():
            self._run(lambda: self.log("DTC: " + self.session.uds.read_dtc().hex()))

    def clear_dtc(self):
        if self._need_session() and messagebox.askyesno("Onay", "Arızalar silinsin mi?"):
            self._run(lambda: (self.session.uds.clear_dtc(), self.log("DTC silindi")))


def main():
    if tk is None:
        print("Tkinter/ekran yok. GUI yerine 'python -m src.cli' kullanın.")
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
