@echo off
title Aurentis AI - Auto-Start Setup
color 0B
cd /d "%~dp0"

echo.
echo  ================================================================
echo   Aurentis AI - Windows Task Scheduler Setup
echo   The bot will start automatically when you log in
echo  ================================================================
echo.

set SCRIPT_DIR=%~dp0
set PYTHON_EXE=C:\Users\Alex\AppData\Local\Programs\Python\Python311\python.exe
set TASK_NAME=Aurentis AI Trading System

:: Remove old task if exists
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

:: Create new task that runs on login
schtasks /create ^
  /tn "%TASK_NAME%" ^
  /tr "\"%PYTHON_EXE%\" -m src.main" ^
  /sc ONLOGON ^
  /rl HIGHEST ^
  /sd 01/01/2024 ^
  /st 00:00 ^
  /f ^
  /it ^
  /ru "%USERNAME%" ^
  /rp "" ^
  /delay 0002:00 ^
  /sd 01/01/2024

:: Change working directory for the task
schtasks /change /tn "%TASK_NAME%" /tr "\"%PYTHON_EXE%\" -m src.main" >nul 2>&1

if %ERRORLEVEL% EQU 0 (
    echo  [OK] Task "%TASK_NAME%" created successfully!
    echo.
    echo  The trading system will now start automatically
    echo  every time you log into Windows.
    echo.
    echo  To remove: schtasks /delete /tn "%TASK_NAME%" /f
) else (
    echo  [!] Could not create task automatically.
    echo      Try running this file as Administrator.
)

echo.
pause
