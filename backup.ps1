param(
    [Parameter(Mandatory = $true)]
    [string]$Destination
)

$ErrorActionPreference = "Stop"

$projectRoot = "C:\AI-Assistant"
$dataRoot = "C:\AI-Assistant-Data"

function Copy-Project {
    param(
        [string]$Source,
        [string]$Target
    )

    if (-not (Test-Path -LiteralPath $Source)) {
        Write-Warning "Source does not exist: $Source"
        return
    }

    New-Item -ItemType Directory -Force -Path $Target | Out-Null

    robocopy $Source $Target /MIR `
        /XD "__pycache__" ".venv" "venv" "env" ".git" ".vscode" ".idea" "data\logs" "data\screenshots" "data\audio" "build" "dist" ".pytest_cache" ".mypy_cache" ".ruff_cache" `
        /XF "*.pyc" "*.pyo" "local_config.json" "Thumbs.db" "Desktop.ini"

    $exitCode = $LASTEXITCODE
    if ($exitCode -ge 8) {
        throw "Robocopy failed for $Source with exit code $exitCode"
    }
}

$backupRoot = Join-Path $Destination ("AI-Assistant-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
$backupProject = Join-Path $backupRoot "AI-Assistant"
$backupData = Join-Path $backupRoot "AI-Assistant-Data"

New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null

Copy-Project -Source $projectRoot -Target $backupProject
Copy-Project -Source $dataRoot -Target $backupData

$restoreNote = @"
AI-Assistant backup created at: $backupRoot

Restore folders to:
- C:\AI-Assistant
- C:\AI-Assistant-Data

Then run:
cd C:\AI-Assistant
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
"@

$restoreNote | Set-Content -Encoding UTF8 -Path (Join-Path $backupRoot "RESTORE.txt")

Write-Host ""
Write-Host "Backup complete:"
Write-Host $backupRoot
Write-Host ""
Write-Host "Check RESTORE.txt inside the backup folder."
