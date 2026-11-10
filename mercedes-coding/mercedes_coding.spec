# PyInstaller spec - tek dosya Windows uygulamasi (.exe) uretir.
# Kullanim:  pyinstaller mercedes_coding.spec
# Cikti:     dist/MercedesKodlama.exe  (gomulu defs/ kutuphanesiyle)

block_cipher = None

a = Analysis(
    ['mercedes_coding.py'],
    pathex=[],
    binaries=[],
    datas=[('defs', 'defs')],            # tanim kutuphanesini icine goml
    hiddenimports=['tkinter'],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='MercedesKodlama',
    debug=False,
    strip=False,
    upx=True,
    console=False,                       # GUI uygulamasi (konsol penceresi yok)
    disable_windowed_traceback=False,
)
