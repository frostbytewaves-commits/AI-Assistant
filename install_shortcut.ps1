$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath("Desktop")
$link = Join-Path $desktop "AI Assistant.lnk"

$exe = Join-Path $root "dist\AI-Assistant\AI-Assistant.exe"
$vbs = Join-Path $root "Game Assistant.vbs"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($link)

if (Test-Path $exe) {
    $shortcut.TargetPath = $exe
    $shortcut.Arguments = ""
    $shortcut.WorkingDirectory = (Split-Path -Parent $exe)
    $shortcut.Description = "AI Assistant (packaged exe)"
} else {
    $shortcut.TargetPath = "wscript.exe"
    $shortcut.Arguments = "`"$vbs`""
    $shortcut.WorkingDirectory = $root
    $shortcut.Description = "AI Assistant (desktop + games)"
}

$shortcut.IconLocation = "shell32.dll,238"
$shortcut.Save()

Write-Host ""
if (Test-Path $exe) {
    Write-Host "Shortcut points to packaged exe:"
    Write-Host " $exe"
} else {
    Write-Host "Packaged exe not found; shortcut uses VBS launcher."
    Write-Host "Build with: powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1"
}
Write-Host "Desktop: AI Assistant.lnk"
Write-Host ""

