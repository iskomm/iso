@echo off
REM Mercedes Kodlama uygulamasini baslatir (Windows).
REM OpenPort 2.0 surucusu 32-bit oldugu icin 32-bit Python onerilir.
cd /d "%~dp0"
python mercedes_coding.py
if errorlevel 1 (
  echo.
  echo Python bulunamadi ya da hata olustu. Python 3 kurulu olmali.
  pause
)
