@echo off
rem Sestaví dist\EanAgent\ (aplikace) a z ní instalátor dist\EanAgent-Setup-<verze>.exe.
cd /d "%~dp0"
if not exist .venv (
  python -m venv .venv || exit /b 1
)
.venv\Scripts\python -m pip install -q -r agent\requirements.txt || exit /b 1
.venv\Scripts\python tools\make_icons.py || exit /b 1
.venv\Scripts\pyinstaller --noconfirm --onedir --noconsole --name EanAgent ^
  --icon agent\app.ico ^
  --paths agent ^
  --add-data "pwa\icons;pwa\icons" ^
  --add-data "agent\app.ico;agent" ^
  --hidden-import pystray._win32 ^
  agent\main.py || exit /b 1

set PYTHONPATH=agent
for /f %%v in ('.venv\Scripts\python -c "from version import __version__; print(__version__)"') do set VERSION=%%v
set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
%ISCC% /Q /DAppVersion=%VERSION% installer\EanAgent.iss || exit /b 1
echo.
echo Hotovo: dist\EanAgent-Setup-%VERSION%.exe
