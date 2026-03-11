@echo off
setlocal

cd /d "%~dp0"

REM Preferred: set ZROK_TOKEN in your shell or user environment.
REM Fallback: paste the token into the console when prompted.
REM Do not save a real token in this file if you plan to commit it.

set "NAME=kaggle_client"
set "SERVER_NAME=kaggle_server"
set "WORKSPACE=/kaggle/working"

set "PATH=%CD%;%PATH%"

set "PYTHON_EXE="
if exist "%CD%\.venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python311\python.exe"

if not defined PYTHON_EXE (
    where py >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=py"
)

if not defined PYTHON_EXE (
    where python >nul 2>nul
    if not errorlevel 1 set "PYTHON_EXE=python"
)

if not defined PYTHON_EXE (
    echo Python not found. Please install Python 3.11+ or create .venv first.
    pause
    exit /b 1
)

set "ZROK_EXE=%ZROK_BIN%"
if defined ZROK_EXE if exist "%ZROK_EXE%" (
    for %%I in ("%ZROK_EXE%") do set "PATH=%%~dpI;%PATH%"
) else (
    set "ZROK_EXE="
)

if not defined ZROK_EXE (
    where zrok >nul 2>nul
    if not errorlevel 1 set "ZROK_EXE=zrok"
)

if not defined ZROK_EXE (
    echo zrok not found.
    echo.
    echo Option 1:
    echo   Install zrok and make sure `zrok` is available in PATH.
    echo   https://docs.zrok.io/docs/guides/install/
    echo.
    echo Option 2:
    echo   Set environment variable ZROK_BIN to the full path of zrok.exe
    echo   Example:
    echo   setx ZROK_BIN "C:\path\to\zrok.exe"
    echo.
    pause
    exit /b 1
)

set "TOKEN=%ZROK_TOKEN%"
if not defined TOKEN set /p TOKEN=Enter your zrok token:
if not defined TOKEN (
    echo Token is required.
    pause
    exit /b 1
)

"%PYTHON_EXE%" zrok_client.py --token "%TOKEN%" --name "%NAME%" --server_name "%SERVER_NAME%" --workspace "%WORKSPACE%"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo Client startup failed. Exit code: %EXIT_CODE%
    pause
    exit /b %EXIT_CODE%
)

echo.
echo Client startup finished.
pause
