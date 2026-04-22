@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "PY_EXE="
if exist ".venv\Scripts\python.exe" goto USE_VENV

py -3.11 -V >nul 2>&1
if not errorlevel 1 set "PY_EXE=py -3.11"

if not defined PY_EXE (
    python --version >nul 2>&1
    if not errorlevel 1 set "PY_EXE=python"
)

if not defined PY_EXE (
    winget --version >nul 2>&1
    if errorlevel 1 (
        echo Python is not installed, and winget is not available.
        pause
        exit /b 1
    )

    echo Python 3.11 not found. Installing it with winget...
    winget install -e --id Python.Python.3.11 ^
        --accept-package-agreements ^
        --accept-source-agreements ^
        --log "%TEMP%\taxonomyagent_python_install.log"

    if errorlevel 1 (
        echo Python installation failed.
        pause
        exit /b 1
    )

    rem Re-detect Python after install
    py -3.11 -V >nul 2>&1
    if not errorlevel 1 set "PY_EXE=py -3.11"

    if not defined PY_EXE (
        python --version >nul 2>&1
        if not errorlevel 1 set "PY_EXE=python"
    )

    if not defined PY_EXE (
        echo Python was installed, but was not detected in this session.
        echo Please close this window and run the script again.
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating local virtual environment...
    %PY_EXE% -m venv .venv
    if errorlevel 1 (
        echo Could not create virtual environment.
        pause
        exit /b 1
    )

    call ".venv\Scripts\activate.bat"
    python -m pip install --upgrade pip
    python -m pip install .
    if errorlevel 1 (
        echo Dependency installation failed.
        pause
        exit /b 1
    )
    goto RUN_APP
)

:USE_VENV
call ".venv\Scripts\activate.bat"

:RUN_APP
python launcher.py