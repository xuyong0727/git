@echo off
REM Windows build script for scan_control.exe (run on Windows 10+)
setlocal
python -m venv .venv
call .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
IF NOT EXIST p.ico (
  echo Warning: p.ico not found in repo. The built exe will have no embedded icon.
)
IF NOT EXIST config.ini (
  echo Warning: config.ini not found; runtime will use defaults.
)
pyinstaller --clean --onefile --noconsole --icon=p.ico --add-data "config.ini;." scan_control.py
IF %ERRORLEVEL% NEQ 0 (
  echo PyInstaller failed with %ERRORLEVEL%
  exit /b %ERRORLEVEL%
)
echo Build complete. Output: dist\scan_control.exe
endlocal
