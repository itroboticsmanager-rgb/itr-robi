Option Explicit

Dim shell, releaseLauncher
Set shell = CreateObject("WScript.Shell")
releaseLauncher = Left(WScript.ScriptFullName, Len(WScript.ScriptFullName) - Len(WScript.ScriptName)) & "launch-kiosk-test.cmd"
shell.Run Chr(34) & releaseLauncher & Chr(34), 0, False
