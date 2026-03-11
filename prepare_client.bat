@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0"

set "TOKEN_CACHE_DIR=%USERPROFILE%\.kaggle_remote_zrok"
set "TOKEN_CACHE_FILE=%TOKEN_CACHE_DIR%\zrok_token.txt"
set "SSH_DIR=%USERPROFILE%\.ssh"
set "KAGGLE_KEY=%SSH_DIR%\kaggle_rsa"
set "KAGGLE_PUBKEY=%SSH_DIR%\kaggle_rsa.pub"
set "NEW_KAGGLE_KEY="

set "TOKEN=%ZROK_TOKEN%"
if not defined TOKEN if exist "%TOKEN_CACHE_FILE%" set /p TOKEN=<"%TOKEN_CACHE_FILE%"
if not defined TOKEN set /p TOKEN=Enter your zrok token:
if not defined TOKEN (
    echo Token is required.
    pause
    exit /b 1
)

if not exist "%TOKEN_CACHE_DIR%" mkdir "%TOKEN_CACHE_DIR%" >nul 2>nul
> "%TOKEN_CACHE_FILE%" (
    echo %TOKEN%
)

if not exist "%KAGGLE_KEY%" (
    where ssh-keygen >nul 2>nul
    if errorlevel 1 (
        echo ssh-keygen not found. Install OpenSSH Client first.
        pause
        exit /b 1
    )

    if not exist "%SSH_DIR%" mkdir "%SSH_DIR%" >nul 2>nul
    echo Generating SSH key for Kaggle at "%KAGGLE_KEY%"...
    ssh-keygen -t rsa -b 4096 -f "%KAGGLE_KEY%" -N "" >nul
    if errorlevel 1 (
        echo Failed to generate SSH key.
        pause
        exit /b 1
    )
    set "NEW_KAGGLE_KEY=1"
)

if not exist "%KAGGLE_PUBKEY%" (
    echo Public key file not found: "%KAGGLE_PUBKEY%"
    pause
    exit /b 1
)

set /p PUBLIC_KEY=<"%KAGGLE_PUBKEY%"

echo.
if defined NEW_KAGGLE_KEY (
    echo Generated new SSH key pair for Kaggle.
) else (
    echo Reusing existing SSH key pair for Kaggle.
)
echo.
echo Public key:
type "%KAGGLE_PUBKEY%"
echo.
echo Kaggle first-time init command:
echo !python3 zrok_server.py --init --token "%TOKEN%" --authorized_key "!PUBLIC_KEY!"
echo.
echo Kaggle later-start command:
echo !python3 zrok_server.py --start
echo.
pause
