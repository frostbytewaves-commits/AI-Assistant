' Creates "AI Assistant" desktop shortcut (double-click to run)
Option Explicit

Dim fso, shell, root, desktop, linkPath, vbsPath, link
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

root = fso.GetParentFolderName(WScript.ScriptFullName)
desktop = shell.SpecialFolders("Desktop")
linkPath = desktop & "\AI Assistant.lnk"
vbsPath = root & "\Game Assistant.vbs"

Set link = shell.CreateShortcut(linkPath)
link.TargetPath = "wscript.exe"
link.Arguments = """" & vbsPath & """"
link.WorkingDirectory = root
link.WindowStyle = 1
link.Description = "AI Assistant (desktop + games)"
link.IconLocation = "shell32.dll, 238"
link.Save

MsgBox "Shortcut created on Desktop:" & vbCrLf & vbCrLf & _
       "AI Assistant" & vbCrLf & vbCrLf & _
       "General desktop helper with strong game expertise." & vbCrLf & _
       "No UAC — F8 / F9 / F10 work without admin.", _
       vbInformation, "AI Assistant"
