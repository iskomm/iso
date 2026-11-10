@echo off
REM Windows'ta tek dosya .exe uretir (dist\MercedesKodlama.exe).
REM OpenPort 2.0 surucusu 32-bit oldugu icin 32-bit Python ile derleyin.
cd /d "%~dp0"
python -m pip install --upgrade pyinstaller || goto :err
python -m PyInstaller --noconfirm mercedes_coding.spec || goto :err
echo.
echo TAMAM: dist\MercedesKodlama.exe hazir.
pause
exit /b 0
:err
echo.
echo HATA: Python 3 ve internet gerekli (pyinstaller kurulumu icin).
pause
exit /b 1
