# Как восстановить AI-Assistant на ноуте

Репозиторий GitHub:

```text
https://github.com/frostbytewaves-commits/AI-Assistant
```

## 1. Скачать проект

Вариант через Git:

```powershell
cd C:\
git clone https://github.com/frostbytewaves-commits/AI-Assistant.git
cd C:\AI-Assistant
```

Вариант без Git:

1. Открой `https://github.com/frostbytewaves-commits/AI-Assistant`.
2. Нажми `Code`.
3. Нажми `Download ZIP`.
4. Распакуй архив так, чтобы проект лежал в `C:\AI-Assistant`.

## 2. Установить Python-зависимости

```powershell
cd C:\AI-Assistant
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Если команда `python` не работает, установи Python с сайта:

```text
https://www.python.org/downloads/windows/
```

При установке включи галочку `Add python.exe to PATH`.

## 3. Восстановить базу данных ассистента

Если в репозитории есть папка `AI-Assistant-Data`, скопируй ее в корень диска `C:\`:

```powershell
robocopy C:\AI-Assistant\AI-Assistant-Data C:\AI-Assistant-Data /MIR
```

После этого должны существовать обе папки:

```text
C:\AI-Assistant
C:\AI-Assistant-Data
```

## 4. Установить Ollama и модели

Установи Ollama:

```text
https://ollama.com/download
```

Потом в PowerShell скачай модели:

```powershell
ollama pull qwen3:14b
ollama pull qwen2.5vl:7b
ollama pull qwen3:8b
ollama pull moondream
```

## 5. Установить Tesseract OCR

Установи Tesseract OCR для Windows.

Ассистент ожидает путь:

```text
C:\Program Files\Tesseract-OCR\tesseract.exe
```

Если Tesseract установлен в другое место, нужно поменять путь в:

```text
C:\AI-Assistant\assistant\config.py
```

Параметр:

```text
tesseract_cmd
```

## 6. Запуск ассистента

Из папки проекта:

```powershell
cd C:\AI-Assistant
.\.venv\Scripts\Activate.ps1
python run_assistant.py
```

Также можно использовать файлы запуска из проекта:

```text
Game Assistant.bat
Game Assistant.vbs
Install Desktop Shortcut.bat
```

## Что не переносится автоматически

GitHub хранит код и данные проекта, но не устанавливает программы на новый компьютер.

На ноуте все равно нужно установить:

- Python
- зависимости из `requirements.txt`
- Ollama
- модели Ollama
- Tesseract OCR

Если папка `AI-Assistant-Data` не была загружена на GitHub, ассистент запустится, но часть игровой базы знаний может отсутствовать.
