' Aurentis AI — Silent launcher (no console window)
' Double-click this to start the bot and open the dashboard in your browser.

Dim WshShell, fso, dir, python, cmd
Set WshShell = CreateObject("WScript.Shell")
Set fso      = CreateObject("Scripting.FileSystemObject")

' Get the folder this script lives in
dir    = fso.GetParentFolderName(WScript.ScriptFullName)
python = "C:\Users\Alex\AppData\Local\Programs\Python\Python311\python.exe"

' Check Python exists
If Not fso.FileExists(python) Then
    MsgBox "Python 3.11 not found at:" & Chr(13) & python & Chr(13) & Chr(13) & _
           "Please install Python 3.11 or update the path in this script.", _
           vbCritical, "Aurentis AI"
    WScript.Quit
End If

' Kill any old instance on port 8000
WshShell.Run "cmd /c taskkill /F /IM python.exe /T >nul 2>&1", 0, True

' Start the bot silently (window hidden = 0)
cmd = Chr(34) & python & Chr(34) & " -m src.main"
WshShell.Run "cmd /c cd /d """ & dir & """ && " & cmd, 0, False

' Wait for server to boot
WScript.Sleep 8000

' Open dashboard in default browser
WshShell.Run "http://localhost:8000", 1, False

' Done — bot keeps running in background
WScript.Quit
