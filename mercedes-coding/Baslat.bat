@echo off
REM Mercedes Kodlama uygulamasini baslatir (Windows).
REM OpenPort 2.0 surucusu 32-bit oldugu icin cihaza baglanirken 32-bit Python onerilir.
cd /d "%~dp0"

REM 1) once 'python' komutunu dene
where python >nul 2>nul
if %errorlevel%==0 (
  python mercedes_coding.py
  goto :done
)

REM 2) olmazsa 'py' (Python launcher / manager) dene
where py >nul 2>nul
if %errorlevel%==0 (
  REM py var ama runtime yoksa kur
  py --version >nul 2>nul
  if not %errorlevel%==0 (
    echo Python runtime bulunamadi, kuruluyor...
    py install default
  )
  py mercedes_coding.py
  goto :done
)

echo.
echo Python 3 bulunamadi.
echo Kurulum: https://www.python.org/downloads/  ("Add python.exe to PATH" isaretle)
echo Ya da Komut Isteminde:  py install default
pause
exit /b 1

:done
if errorlevel 1 (
  echo.
  echo Uygulama bir hata ile kapandi. Yukaridaki mesaji kontrol edin.
  pause
)
