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
