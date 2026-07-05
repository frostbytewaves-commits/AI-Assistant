# Backup and Restore

This project has two important folders:

- `C:\AI-Assistant` - source code, scripts, examples, and small bundled data.
- `C:\AI-Assistant-Data` - active game knowledge base used by the assistant.

## Cheapest Backup

Use an external drive, USB stick, OneDrive, Google Drive, or any folder with enough free space.

From PowerShell:

```powershell
.\backup.ps1 -Destination "E:\AI-Assistant-Backup"
```

Replace `E:\AI-Assistant-Backup` with your real backup path.

The script copies:

- source code from `C:\AI-Assistant`
- active data from `C:\AI-Assistant-Data`

The script skips:

- `__pycache__`
- virtual environments
- logs
- screenshots
- audio captures
- editor/cache/build folders

## Restore On Another PC

Copy folders back to:

- `C:\AI-Assistant`
- `C:\AI-Assistant-Data`

Install Python dependencies:

```powershell
cd C:\AI-Assistant
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

External programs/models are not included in the backup. Reinstall them separately if needed:

- Python
- Tesseract OCR at `C:\Program Files\Tesseract-OCR\tesseract.exe`
- Ollama
- Ollama models used in `assistant\config.py`

Useful model commands:

```powershell
ollama pull qwen3:14b
ollama pull qwen2.5vl:7b
ollama pull qwen3:8b
ollama pull moondream
```

## Optional Git Backup

If you want an online copy, create a private GitHub repository and run:

```powershell
cd C:\AI-Assistant
git init
git add .
git commit -m "Backup AI assistant project"
git branch -M main
git remote add origin <your-private-repo-url>
git push -u origin main
```

Do not put private secrets into Git. This project currently uses `local_config.json.example`; keep any real `local_config.json` private.
