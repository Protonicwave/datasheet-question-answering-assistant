@echo off
rem Starts the datasheet assistant at http://127.0.0.1:8000, first installing
rem whatever is missing: uv (which brings Python), Node.js, the dependencies,
rem the built web page and the datasheets. Steps already done are skipped.
setlocal
cd /d "%~dp0"
set "URL=http://127.0.0.1:8000"
set "MIN_NODE_MAJOR=22"

call :ensure_uv || goto failed
call :ensure_node || goto failed
call :ensure_api_key || goto failed

echo Installing Python and its packages where missing...
call uv sync --frozen
if errorlevel 1 goto failed

call :build_web || goto failed
call :ensure_datasheets || goto failed

echo.
echo Starting the assistant at %URL%. Close this window or press Ctrl+C to stop it.
rem The browser opens after a short wait so the server is listening by then.
start "" /b powershell -NoProfile -Command "Start-Sleep -Seconds 4; Start-Process '%URL%'"
call uv run --frozen datasheet-assistant serve
if errorlevel 1 goto failed
exit /b 0


:ensure_uv
where uv >nul 2>nul && exit /b 0
echo uv was not found. Installing it with its official installer...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
if errorlevel 1 exit /b 1
rem The installer puts uv here; this window does not see the new PATH yet.
set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul && exit /b 0
echo uv was installed but cannot be found. Open a new window and run this again.
exit /b 1


:ensure_node
where node >nul 2>nul && goto check_node_version
where winget >nul 2>nul
if errorlevel 1 (
  echo Node.js %MIN_NODE_MAJOR% or later is needed. Install the LTS version from https://nodejs.org and run this again.
  exit /b 1
)
echo Node.js was not found. Installing the LTS version with winget...
winget install --id OpenJS.NodeJS.LTS --exact --accept-source-agreements --accept-package-agreements
if errorlevel 1 exit /b 1
set "PATH=%ProgramFiles%\nodejs;%PATH%"
where node >nul 2>nul && goto check_node_version
echo Node.js was installed but cannot be found. Open a new window and run this again.
exit /b 1

:check_node_version
for /f "tokens=1 delims=." %%v in ('node --version') do set "NODE_MAJOR=%%v"
set "NODE_MAJOR=%NODE_MAJOR:v=%"
if %NODE_MAJOR% GEQ %MIN_NODE_MAJOR% exit /b 0
echo Node.js %NODE_MAJOR% is installed, but %MIN_NODE_MAJOR% or later is needed. Update it from https://nodejs.org and run this again.
exit /b 1


:ensure_api_key
if defined ANTHROPIC_API_KEY exit /b 0
echo ANTHROPIC_API_KEY is not set. Paste your Anthropic API key; it is not shown as you type.
for /f "usebackq delims=" %%k in (`powershell -NoProfile -Command "$key = Read-Host 'API key' -AsSecureString; [Runtime.InteropServices.Marshal]::PtrToStringBSTR([Runtime.InteropServices.Marshal]::SecureStringToBSTR($key))"`) do set "ANTHROPIC_API_KEY=%%k"
if not defined ANTHROPIC_API_KEY (
  echo No key was entered.
  exit /b 1
)
choice /c YN /m "Save the key in your user environment so later runs do not ask"
if errorlevel 2 exit /b 0
setx ANTHROPIC_API_KEY "%ANTHROPIC_API_KEY%" >nul
exit /b 0


:build_web
echo Building the web page...
pushd web
if not exist node_modules (
  call npm ci --no-audit --no-fund
  if errorlevel 1 goto build_web_failed
)
call npm run build
if errorlevel 1 goto build_web_failed
popd
exit /b 0

:build_web_failed
popd
exit /b 1


:ensure_datasheets
rem Ingest reuses PDFs already downloaded, so an interrupted earlier run is finished here.
if exist "data\pages\*.json" if exist "data\pdfs\*.pdf" exit /b 0
echo Downloading the datasheets and extracting their text...
call uv run --frozen datasheet-assistant ingest
exit /b %errorlevel%


:failed
echo.
echo The assistant did not start. See the message above.
pause
exit /b 1
