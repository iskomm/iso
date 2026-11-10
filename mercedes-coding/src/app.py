"""
Tkinter GUI - Mercedes CBF kodlama uygulamasi.

Ozellikler:
  - OpenPort baglantisi, oturum acma
  - Tanim (JSON) yukleme, CBF tarama
  - Secili blogu okuma -> alanlari acilir menu/checkbox olarak gosterme
  - Degisiklikleri yazma (otomatik yedek), yedekten geri yukleme
  - Security access (seed/key) ile kilit acma
  - DTC oku/sil
  - Alt tarafta canli log

GUI yalnizca ekran olan ortamda calisir; donanimsiz is icin src/cli.py
kullanin. Is mantigi tamamen CodingSession icinde oldugundan GUI incedir.
"""

from __future__ import annotations

import threading
import traceback

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except Exception:  # basliksiz ortam
    tk = None

from .cbf import CbfFile, CodingDefinition
from .uds import UdsClient, Session
from .coding import CodingSession, Backup
from .security import SecurityProfile, XorKey, DllSeedKey


class App:
    def __init__(self, root):
        self.root = root
        root.title("Mercedes-Benz Kodlama (OpenPort 2.0)")
        root.geometry("900x680")

        self.device = None
        self.session: CodingSession | None = None
        self.defn: CodingDefinition | None = None
        self.field_vars: dict[str, tk.StringVar] = {}
        self.current_block = None

        self._build_toolbar()
        self._build_block_panel()
        self._build_log()

    # -- arayuz kurulumu ---------------------------------------------------

    def _build_toolbar(self):
        bar = ttk.Frame(self.root, padding=6)
        bar.pack(fill="x")
        ttk.Button(bar, text="Tanim Yukle (JSON)",
                   command=self.load_definition).pack(side="left", padx=2)
        ttk.Button(bar, text="CBF Tara",
                   command=self.scan_cbf).pack(side="left", padx=2)
        ttk.Button(bar, text="Baglan",
                   command=self.connect).pack(side="left", padx=2)
        ttk.Button(bar, text="Oturum Ac",
                   command=self.start_session).pack(side="left", padx=2)

        self.block_combo = ttk.Combobox(bar, state="readonly", width=22)
        self.block_combo.pack(side="left", padx=8)
        self.block_combo.bind("<<ComboboxSelected>>", lambda e: self.read_block())

        ttk.Button(bar, text="Oku",
                   command=self.read_block).pack(side="left", padx=2)
        ttk.Button(bar, text="Yaz",
                   command=self.write_block).pack(side="left", padx=2)

        bar2 = ttk.Frame(self.root, padding=(6, 0))
        bar2.pack(fill="x")
        ttk.Button(bar2, text="Security Ac (seed/key)",
                   command=self.unlock).pack(side="left", padx=2)
        ttk.Button(bar2, text="Yedekle",
                   command=self.backup).pack(side="left", padx=2)
        ttk.Button(bar2, text="Yedekten Yukle",
                   command=self.restore).pack(side="left", padx=2)
        ttk.Button(bar2, text="DTC Oku",
                   command=self.read_dtc).pack(side="left", padx=2)
        ttk.Button(bar2, text="DTC Sil",
                   command=self.clear_dtc).pack(side="left", padx=2)
        self.status = ttk.Label(bar2, text="bagli degil", foreground="#b00")
        self.status.pack(side="right", padx=6)

    def _build_block_panel(self):
        wrap = ttk.LabelFrame(self.root, text="Kodlama Alanlari", padding=6)
        wrap.pack(fill="both", expand=False, padx=6, pady=4)
        self.fields_frame = ttk.Frame(wrap)
        self.fields_frame.pack(fill="both", expand=True)

    def _build_log(self):
        wrap = ttk.LabelFrame(self.root, text="Log", padding=4)
        wrap.pack(fill="both", expand=True, padx=6, pady=4)
        self.log_text = tk.Text(wrap, height=12, wrap="none",
                                font=("Courier", 9))
        self.log_text.pack(fill="both", expand=True, side="left")
        sb = ttk.Scrollbar(wrap, command=self.log_text.yview)
        sb.pack(side="right", fill="y")
        self.log_text.config(yscrollcommand=sb.set)

    # -- yardimcilar -------------------------------------------------------

    def log(self, msg):
        self.log_text.insert("end", str(msg) + "\n")
        self.log_text.see("end")
        self.root.update_idletasks()

    def _run(self, fn):
        """Donanim cagrilarini ayri thread'de calistirip GUI'yi dondurmaz."""
        def wrapper():
            try:
                fn()
            except Exception as e:
                self.log(f"HATA: {e}")
                self.log(traceback.format_exc())
                messagebox.showerror("Hata", str(e))
        threading.Thread(target=wrapper, daemon=True).start()

    def _security_profile(self) -> SecurityProfile:
        # Pratikte DllSeedKey ile Mercedes orijinal algoritmasi baglanir.
        # Burada tanimda 'seedkey' alani varsa onu kurar; yoksa bos profil.
        prof = SecurityProfile()
        sk = getattr(self.defn, "seedkey", None)
        if isinstance(sk, dict):
            lvl = sk.get("level", 1)
            if sk.get("dll"):
                prof.register(lvl, DllSeedKey(sk["dll"],
                                              sk.get("func", "GenerateKeyEx")))
            elif sk.get("xor_mask"):
                prof.register(lvl, XorKey(bytes.fromhex(sk["xor_mask"])))
        return prof

    # -- eylemler ----------------------------------------------------------

    def load_definition(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        self.defn = CodingDefinition.from_json(path)
        self.block_combo["values"] = [b.name for b in self.defn.blocks]
        if self.defn.blocks:
            self.block_combo.current(0)
        self.log(f"tanim yuklendi: {self.defn.ecu_name} "
                 f"({len(self.defn.blocks)} blok)")

    def scan_cbf(self):
        path = filedialog.askopenfilename(filetypes=[("CBF", "*.cbf *.cff"),
                                                     ("Tum", "*.*")])
        if not path:
            return
        scan = CbfFile(path).scan()
        self.log(f"CBF: {scan.size} byte, magic={scan.magic}")
        self.log(f"beyinler: {', '.join(scan.ecu_names) or '(yok)'}")
        self.log(f"kodlama etiketleri: {len(scan.did_labels)} adet")
        for s in scan.did_labels[:30]:
            self.log(f"   {s}")

    def connect(self):
        if self.defn is None:
            messagebox.showwarning("Uyari", "Once tanim (JSON) yukleyin")
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
            self.status.config(text="bagli", foreground="#070")
            self.log("OpenPort baglandi")
        self._run(job)

    def start_session(self):
        if not self.session:
            return
        self._run(lambda: self.session.start(Session.EXTENDED))

    def unlock(self):
        if not self.session or not self.current_block:
            messagebox.showinfo("Bilgi", "Once blok secip okuyun")
            return
        lvl = self.current_block.security_level or 1
        self._run(lambda: self.session.ensure_security(lvl))

    def read_block(self):
        if not self.session:
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
            ttk.Label(self.fields_frame, text=f.name,
                      width=26).grid(row=r, column=0, sticky="w", pady=1)
            var = tk.StringVar(value=str(decoded[f.name]["value"]))
            self.field_vars[f.name] = var
            if f.options:
                labels = [f"{k} - {v}" for k, v in sorted(f.options.items())]
                cb = ttk.Combobox(self.fields_frame, values=labels,
                                  state="readonly", width=28)
                cur = decoded[f.name]["value"]
                cb.set(f"{cur} - {f.options.get(cur, cur)}")
                cb.grid(row=r, column=1, sticky="w")
                cb.bind("<<ComboboxSelected>>",
                        lambda e, v=var, c=cb: v.set(c.get().split(" - ")[0]))
            else:
                ttk.Entry(self.fields_frame, textvariable=var,
                          width=30).grid(row=r, column=1, sticky="w")
            if f.description:
                ttk.Label(self.fields_frame, text=f.description,
                          foreground="#666").grid(row=r, column=2, sticky="w",
                                                   padx=6)

    def write_block(self):
        if not self.session or not self.current_block:
            return
        if not messagebox.askyesno("Onay",
                                   "Secili degerler ECU'ya yazilacak. "
                                   "Once yedek alindigindan emin olun. Devam?"):
            return
        changes = {name: int(var.get(), 0)
                   for name, var in self.field_vars.items()}

        def job():
            path = filedialog.asksaveasfilename(
                title="Yazmadan once yedek", defaultextension=".json",
                filetypes=[("JSON", "*.json")])
            ok = self.session.set_fields(self.current_block, changes,
                                         verify=True, backup_path=path or None)
            self.log("YAZIM SONUCU: " + ("OK" if ok else "DOGRULAMA FARKLI"))
        self._run(job)

    def backup(self):
        if not self.session or not self.current_block:
            return
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("JSON", "*.json")])
        if path:
            self._run(lambda: self.session.backup(self.current_block, path))

    def restore(self):
        if not self.session:
            return
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        self._run(lambda: self.session.restore(Backup.load(path)))

    def read_dtc(self):
        if not self.session:
            return
        self._run(lambda: self.log("DTC: " +
                                   self.session.uds.read_dtc().hex()))

    def clear_dtc(self):
        if not self.session:
            return
        if messagebox.askyesno("Onay", "Tum arizalar silinsin mi?"):
            self._run(lambda: (self.session.uds.clear_dtc(),
                               self.log("DTC silindi")))


def main():
    if tk is None:
        print("Tkinter yok / ekran yok. GUI yerine 'python -m src.cli' kullanin.")
        return
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
