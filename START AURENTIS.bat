@echo off
title Aurentis AI Trading System v2.0
color 0A
mode con: cols=160 lines=50
cd /d "%~dp0"

echo.
echo  ================================================================
echo   Aurentis AI Trading System  v2.0
echo   Paper Trading on Hyperliquid Perpetuals
echo  ================================================================
echo.

:: Check Python
"C:\Users\Alex\AppData\Local\Programs\Python\Python311\python.exe" --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo  [ERROR] Python 3.11 not found at expected path.
    echo  Please check your Python installation.
    pause
    exit /b 1
)

:: Install / upgrade dependencies silently
echo  Checking dependencies...
"C:\Users\Alex\AppData\Local\Programs\Python\Python311\python.exe" -m pip install -r requirements.txt -q --no-warn-script-location
echo  Dependencies OK.
echo.

:: Copy .env.example -> .env if .env doesn't exist
if not exist .env (
    echo  [SETUP] No .env found. Creating from .env.example...
    copy .env.example .env >nul
    echo  [SETUP] Please edit .env with your credentials, then restart.
    echo.
    notepad .env
    pause
    exit /b 0
)

:: Show local IP for easy access from other devices
echo  ----------------------------------------------------------------
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4"') do (
    set IP=%%a
    goto :showip
)
:showip
set IP=%IP: =%
echo   Dashboard URL: http://%IP%:8000
echo   (open this from your phone or tablet!)
echo  ----------------------------------------------------------------
echo.

:start
echo  Starting Aurentis AI...
echo  Press Ctrl+C to stop.
echo.
"C:\Users\Alex\AppData\Local\Programs\Python\Python311\python.exe" -m src.main
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo  [!] System stopped with error code %ERRORLEVEL%.
    echo      Restarting in 15 seconds... (Ctrl+C to cancel)
    timeout /t 15 /nobreak
    goto start
)
pause > nul
