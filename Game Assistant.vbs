' Launch AI Assistant — без UAC (hotkey через Win32)
Option Explicit

Dim fso, shell, root, bat
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("Shell.Application")
root = fso.GetParentFolderName(WScript.ScriptFullName)
bat = root & "\Game Assistant.bat"

shell.ShellExecute bat, "", root, "", 0
