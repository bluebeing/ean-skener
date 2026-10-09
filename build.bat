@echo off
rem Sestaví dist\EanAgent.exe (jeden soubor, bez konzole).
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv || exit /b 1
)
.venv\Scripts\python -m pip install -q -r agent\requirements.txt || exit /b 1
.venv\Scripts\python tools\make_icons.py || exit /b 1
.venv\Scripts\pyinstaller --noconfirm --onefile --noconsole --name EanAgent ^
  --icon agent\app.ico ^
  --paths agent ^
  --add-data "pwa\icons;pwa\icons" ^
  --add-data "agent\app.ico;agent" ^
  --hidden-import pystray._win32 ^
  agent\main.py || exit /b 1
echo.
echo Hotovo: dist\EanAgent.exe
