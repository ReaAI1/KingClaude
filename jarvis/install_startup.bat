@echo off
echo.
echo ==========================================
echo   Installing Jarvis as Windows startup app
echo ==========================================
echo.

:: Get the current directory (jarvis folder)
set JARVIS_DIR=%~dp0

:: Create VBScript to make a shortcut
set VBS_PATH=%TEMP%\make_jarvis_shortcut.vbs
echo Set WS = CreateObject("WScript.Shell") > "%VBS_PATH%"
echo StartupFolder = WS.SpecialFolders("Startup") >> "%VBS_PATH%"
echo Set Shortcut = WS.CreateShortcut(StartupFolder ^& "\Jarvis.lnk") >> "%VBS_PATH%"
echo Shortcut.TargetPath = "python" >> "%VBS_PATH%"
echo Shortcut.Arguments = """" ^& "%JARVIS_DIR%launcher.py" ^& """" >> "%VBS_PATH%"
echo Shortcut.WorkingDirectory = "%JARVIS_DIR%" >> "%VBS_PATH%"
echo Shortcut.Description = "J.A.R.V.I.S. Voice Assistant" >> "%VBS_PATH%"
echo Shortcut.Save >> "%VBS_PATH%"
cscript //nologo "%VBS_PATH%"
del "%VBS_PATH%"

echo.
echo Done! Jarvis will now start automatically when Windows starts.
echo.
echo IMPORTANT: Make sure your .env file has your API key:
echo   %JARVIS_DIR%.env
echo.
echo To start Jarvis right now, run:
echo   python "%JARVIS_DIR%launcher.py"
echo.
pause
