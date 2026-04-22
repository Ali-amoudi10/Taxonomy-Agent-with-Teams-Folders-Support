@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo [1/6] Locating Python...
set "PY_CMD="
where py >nul 2>nul && set "PY_CMD=py -3.11"
if not defined PY_CMD where python >nul 2>nul && set "PY_CMD=python"
if not defined PY_CMD (
  echo Python was not found. Install Python 3.11 and rerun this script.
  pause
  exit /b 1
)

echo [2/6] Creating build environment...
if exist ".venv-build" rmdir /s /q ".venv-build"
call %PY_CMD% -m venv ".venv-build"
if errorlevel 1 (
  echo Failed to create build virtual environment.
  pause
  exit /b 1
)

call ".venv-build\Scripts\activate.bat"
if errorlevel 1 (
  echo Failed to activate build virtual environment.
  pause
  exit /b 1
)

echo [3/6] Installing build dependencies...
python -m pip install --upgrade pip setuptools wheel
if errorlevel 1 goto :pipfail
python -m pip install . pyinstaller
if errorlevel 1 goto :pipfail

echo [4/6] Building Windows application bundle...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
pyinstaller --noconfirm TaxonomyAgent.spec
if errorlevel 1 (
  echo PyInstaller build failed.
  pause
  exit /b 1
)

echo [5/6] Locating Inno Setup...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
  echo Inno Setup 6 was not found.
  echo The app bundle was created in dist\Taxonomy Agent\
  echo Install Inno Setup 6, then run:
  echo    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\TaxonomyAgent.iss
  pause
  exit /b 0
)

echo [6/6] Building installer...
set "ISS_SRC=installer\TaxonomyAgent.iss"
set "ISS_TMP=installer\TaxonomyAgent.build.iss"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$src = Join-Path (Get-Location) 'installer\TaxonomyAgent.iss'; $dst = Join-Path (Get-Location) 'installer\TaxonomyAgent.build.iss'; $lines = Get-Content -LiteralPath $src; $out = New-Object System.Collections.Generic.List[string]; $inSetup = $false; $done = $false; foreach ($line in $lines) { if ($line -match '^\[Setup\]$') { $inSetup = $true; $out.Add($line); continue } if ($inSetup -and -not $done -and $line -match '^DisableDirPage=') { $out.Add('DisableDirPage=no'); $done = $true; continue } if ($inSetup -and -not $done -and $line -match '^\[') { $out.Add('DisableDirPage=no'); $done = $true } $out.Add($line) } if ($inSetup -and -not $done) { $out.Add('DisableDirPage=no') } Set-Content -LiteralPath $dst -Value $out -Encoding ASCII"
if errorlevel 1 (
  echo Failed to prepare installer script.
  pause
  exit /b 1
)
"%ISCC%" "%ISS_TMP%"
if errorlevel 1 (
  echo Inno Setup compilation failed.
  pause
  exit /b 1
)
if exist "%ISS_TMP%" del /q "%ISS_TMP%"

echo.
echo Done.
echo Installer created at:
echo    installer\output\TaxonomyAgentSetup.exe
echo.
echo NOTE: On first launch, the app will ask for Azure configuration if it is missing.
pause
exit /b 0

:pipfail
echo Failed to install Python dependencies needed for the build.
pause
exit /b 1
