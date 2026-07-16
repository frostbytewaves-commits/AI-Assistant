# Build windowed AI-Assistant.exe (PyInstaller onedir).
# Usage: powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$py = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    throw "Missing .venv - create venv and install requirements.txt first."
}

Write-Host "Installing PyInstaller if needed..."
& $py -m pip install -q "pyinstaller>=6.3"

Write-Host "Cleaning old build/dist..."
$oldBuild = Join-Path $root "build\AI-Assistant"
$oldDist = Join-Path $root "dist\AI-Assistant"
if (Test-Path $oldBuild) { Remove-Item -Recurse -Force $oldBuild }
if (Test-Path $oldDist) { Remove-Item -Recurse -Force $oldDist }

Write-Host "Building windowed onedir (several minutes)..."
$spec = Join-Path $root "AI-Assistant.spec"
& $py -m PyInstaller --noconfirm --clean $spec
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$exe = Join-Path $root "dist\AI-Assistant\AI-Assistant.exe"
if (-not (Test-Path $exe)) {
    throw "Build finished but exe not found: $exe"
}

$cfg = Join-Path $root "dist\AI-Assistant\local_config.json"
$example = Join-Path $root "local_config.json.example"
$repoCfg = Join-Path $root "local_config.json"
if (-not (Test-Path $cfg)) {
    if (Test-Path $repoCfg) {
        Copy-Item $repoCfg $cfg
    }
    elseif (Test-Path $example) {
        Copy-Item $example $cfg
    }
}

Write-Host ""
Write-Host "OK: $exe"
Write-Host "Run that exe (Ollama must be running separately)."
Write-Host "Writable data/ and local_config.json live next to the exe."
