$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath("Desktop")
$vbs = Join-Path $root "Game Assistant.vbs"
$link = Join-Path $desktop "AI Assistant.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)
$shortcut.TargetPath = "wscript.exe"
$shortcut.Arguments = "`"$vbs`""
$shortcut.WorkingDirectory = $root
$shortcut.Description = "AI Assistant (desktop + games)"
$shortcut.IconLocation = "shell32.dll,238"
$shortcut.Save()

Write-Host ""
Write-Host " Ярлык создан на рабочем столе: AI Assistant"
Write-Host " Универсальный ассистент (игры — сильная сторона). UAC не нужен."
Write-Host ""
