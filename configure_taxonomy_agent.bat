@echo off
setlocal
if not exist .venv\Scripts\python.exe (
  py -m venv .venv || exit /b 1
  call .venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -e . || exit /b 1
) else (
  call .venv\Scripts\activate.bat
)
python launcher.py --configure-only
