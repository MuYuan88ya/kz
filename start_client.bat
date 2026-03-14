@echo off
setlocal

cd /d "%~dp0"

REM -- Configuration --
set "NAME=kaggle_client"
set "SERVER_NAME=kaggle_server"
set "WORKSPACE=/kaggle/working"
set "TOKEN_CACHE_DIR=%USERPROFILE%\.kaggle_remote_zrok"
set "TOKEN_CACHE_FILE=%TOKEN_CACHE_DIR%\zrok_token.txt"
set "SSH_DIR=%USERPROFILE%\.ssh"
set "KAGGLE_KEY=%SSH_DIR%\kaggle_rsa"
set "KAGGLE_PUBKEY=%SSH_DIR%\kaggle_rsa.pub"
set "NEW_KAGGLE_KEY="

set "PATH=%CD%;%PATH%"

REM -- Find Python --
set "PYTHON_EXE="
if exist "%CD%\.venv\Scripts\python.exe" set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
if not defined PYTHON_EXE if exist "%LocalAppData%\Programs\Python\Python311\python.exe" set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python311\python.exe"
if not defined PYTHON_EXE (where py >nul 2>nul && set "PYTHON_EXE=py")
if not defined PYTHON_EXE (where python >nul 2>nul && set "PYTHON_EXE=python")

if not defined PYTHON_EXE (
    echo Python not found. Please install Python 3.11+ or create .venv first.
    pause
    exit /b 1
)

REM -- Find zrok --
set "ZROK_EXE="
where zrok >nul 2>nul && set "ZROK_EXE=zrok"
if not defined ZROK_EXE if exist "%CD%\zrok.exe" set "ZROK_EXE=%CD%\zrok.exe"
if not defined ZROK_EXE if defined ZROK_BIN if exist "%ZROK_BIN%" set "ZROK_EXE=%ZROK_BIN%"

if defined ZROK_EXE if /I not "%ZROK_EXE%"=="zrok" if exist "%ZROK_EXE%" (
    for %%I in ("%ZROK_EXE%") do set "PATH=%%~dpI;%PATH%"
)

if not defined ZROK_EXE (
    echo zrok not found.
    echo.
    echo Install zrok from https://docs.zrok.io/docs/guides/install/
    echo Ensure `zrok` is in PATH, or set ZROK_BIN to the full path of zrok.exe
    pause
    exit /b 1
)

REM -- Generate SSH key if needed --
if not exist "%KAGGLE_KEY%" (
    where ssh-keygen >nul 2>nul
    if not errorlevel 1 (
        if not exist "%SSH_DIR%" mkdir "%SSH_DIR%" >nul 2>nul
        echo Generating SSH key for Kaggle at "%KAGGLE_KEY%"...
        ssh-keygen -t rsa -b 4096 -f "%KAGGLE_KEY%" -N "" >nul
        if not errorlevel 1 set "NEW_KAGGLE_KEY=1"
    )
)

REM -- Get token --
set "TOKEN=%ZROK_TOKEN%"
if not defined TOKEN if exist "%TOKEN_CACHE_FILE%" set /p TOKEN=<"%TOKEN_CACHE_FILE%"
if not defined TOKEN set /p TOKEN=Enter your zrok token:
if not defined TOKEN (
    echo Token is required.
    pause
    exit /b 1
)

if not exist "%TOKEN_CACHE_DIR%" mkdir "%TOKEN_CACHE_DIR%" >nul 2>nul
> "%TOKEN_CACHE_FILE%" (echo %TOKEN%)

if defined NEW_KAGGLE_KEY if exist "%KAGGLE_PUBKEY%" (
    echo.
    echo New local Kaggle public key:
    type "%KAGGLE_PUBKEY%"
    echo.
)

REM -- Launch client --
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
