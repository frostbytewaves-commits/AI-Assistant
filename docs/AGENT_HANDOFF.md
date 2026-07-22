# AGENT_HANDOFF — «сознание» проекта для Cursor

**Читать первым** при любой новой сессии на любом ПК.  
Обновлено: 2026-07-22. Источник правды по архитектуре: `docs/JARVIS_ARCHITECTURE.md`. Законы: `.cursor/rules/model-first-reasoning.mdc`, `AGENTS.md`.

---

## 1. Что это за проект

Локальный Windows JARVIS-подобный ассистент (`C:\AI-Assistant` → GitHub `frostbytewaves-commits/AI-Assistant`).

- Стек: Python + Tk overlay + Ollama (текст/vision) + plugins
- Игры (Minecraft / ONI) — сильная специализация, но продукт = **универсальный десктоп-ассистент**
- Целевой ПК: RTX 5070 Ti 16GB + 64GB RAM; есть профиль `laptop` для отпуска

Цикл: `Sense → Context → Reason → Planner → Act → Memory`.

---

## 2. Законы (не нарушать)

1. **Model-first** — не чинить понимание языка словарями/`if "who is"` / regex-маркерами. Улучшать промпты, tools, Context.
2. **Thin Orchestrator** — не раздувать `overlay.py` / `llm.py`. Новое → `assistant/core/`, `assistant/act/`, `plugins/`, providers.
3. **Chat ≠ game agents** — автономный grind только в `game_agents/` (отдельно).
4. **Safety** — whitelist tools, ConfirmGate; нет произвольного shell от модели.

---

## 3. Приоритет владельца (важно)

| Сейчас | Потом |
|--------|--------|
| Рабочая **начинка** (voice, tools, memory, надёжность) | Большой UI rewrite |
| Tk-overlay как временный shell | Apple Intelligence–like UI |

**UI later (запомнить, не начинать без явной просьбы):**
- Реф: центральный mesh-орб + glass pill-input («Ask anything…»)
- Стек: **B** pywebview+HTML или **C** Tauri (предпочтительно) / Electron + мост к Python
- Зафиксировано в `JARVIS_ARCHITECTURE.md` §5.7 и `AGENTS.md`

Мелкий polish Tk (орб PIL) уже есть — **не** вкладываться в Tk-glass/WebGL.

---

## 4. Roadmap: где мы

| Версия | Статус |
|--------|--------|
| v0.1 профили + thinking | ✅ |
| v0.2 ContextManager + WindowProvider + ActionRegistry v1 | ✅ |
| v0.3 MemoryBackend + тонкий Orchestrator + Plugin API | ✅ |
| **v0.4 Voice pipeline** | 🟡 **v0.4-mini сделан; дальше hardening/wake-word** |
| v0.5 Screen/OCR/Vision providers + Event Bus | очередь |
| v0.6 Steam/media/Discord plugins | очередь |
| UI Tauri/pywebview | после начинки |

Последние daily pushes:
- `a572772` — *Daily patch: MemoryBackend, thin Orchestrator, Plugin API, and packaged exe.*
- `31f0d4b` — *Daily patch: Voice pipeline coordinator and 32B desktop profile.*

---

## 5. Что уже сделано (конкретика)

### Core
- `assistant/core/context.py` — ContextManager, inventory окон («что открыто?» без F8)
- `assistant/core/orchestrator.py` — `handle_turn`: context → plan → capture → execute
- `assistant/core/voice_pipeline.py` — UI-free voice turn lifecycle: record → STT → Orchestrator → optional TTS
- Overlay дергает Orchestrator, сам UI/capture/hotkeys

### Voice
- `VoiceEngine` (`assistant/voice.py`) оставлен за низкоуровневые record/STT/TTS/playback
- `VoiceTurnCoordinator` держит состояния `idle/listening/transcribing/thinking/speaking/error`
- `PushToTalkActivation` — текущая F9/button activation; `VoiceActivationProvider` — задел под wake-word
- `assistant/overlay.py` больше не держит весь voice lifecycle вручную; голосовой путь сходится в `Orchestrator.handle_turn()`

### Memory
- `assistant/memory/` — `MemoryBackend`, `JsonMemoryBackend`, `InMemoryBackend`, `MemoryManager`
- Старый `assistant/memory.py` удалён (логика в `manager.py`)

### Act / Plugins
- `assistant/act/` — registry, executor, planner, prompts
- `assistant/act/plugin.py` — **discovery**: любой `plugins/<name>/` с `register(registry)` без правки ядра
- `plugins/system/` — launch/focus/close/url/media/list_apps + hooks (`normalize_request`, `planner_notes`, …)
- Фильтр: `enabled_plugins` в `local_config.json`

### Models / Ollama
- Профили: `laptop` | `desktop` | `deep` (+ legacy gaming/balance/quality)
- `desktop` теперь целится в `qwen3:32b` на домПК; fallback: `qwen3:30b-a3b` → `qwen3:14b` → `qwen3:8b`
- `num_ctx` в API options (не только слайдер Ollama GUI): laptop 8k, desktop 16k; override в `local_config.json`

### Packaging
- PyInstaller onedir: `tools/build_exe.ps1` → `dist/AI-Assistant/AI-Assistant.exe`
- `assistant/runtime_paths.py` — `app_root()` vs `bundle_dir()` для frozen
- Ярлык: `install_shortcut.ps1` (предпочитает exe, иначе VBS)
- Ollama / Tesseract / Whisper-модели — **снаружи** exe

### UX (временно)
- Мягкая dark-палитра Apple-like в `markdown_ui.py`
- `assistant/orb.py` — mesh-орб (cyan/indigo/pink), пульс idle/listening/busy
- Это **не** финальный дизайн

### Tests
- `pytest` — memory, orchestrator, plugin API, voice pipeline, num_ctx, intent gates, normalize, planner
- `requirements-dev.txt`, `pytest.ini`
- Последняя ручная проверка на Windows PowerShell: `49 passed in 0.91s`

---

## 6. Ключевые пути

```text
assistant/core/orchestrator.py   # ход диалога
assistant/core/voice_pipeline.py # voice lifecycle без Tk/UI
assistant/llm.py                 # Ollama + try_tool_action
assistant/act/plugin.py          # discovery плагинов
assistant/memory/                # память
assistant/voice.py               # record/STT/TTS/playback plumbing
assistant/overlay.py             # Tk UI (держать тонким)
plugins/system/                  # whitelist actions
docs/JARVIS_ARCHITECTURE.md      # архитектура
local_config.json.example        # пример конфига
tools/build_exe.ps1              # сборка exe
```

Данные игр снаружи: обычно `C:\AI-Assistant-Data\games` (см. `local_config`).

---

## 7. Как запускать

Из исходников (для разработки — предпочтительно):

```powershell
cd C:\AI-Assistant
.\.venv\Scripts\pythonw.exe run_assistant.py
```

Или exe: `dist\AI-Assistant\AI-Assistant.exe` (нужна пересборка после изменений кода).

Нужны: Ollama с моделями, при OCR — Tesseract.

Тесты:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

---

## 8. Следующая работа (v0.4 Voice) — что осталось

v0.4-mini уже сделал базовую развязку: voice lifecycle вынесен из Tk overlay в `VoiceTurnCoordinator`, добавлены тесты без микрофона/Ollama/Tk.

Дальше имеет смысл улучшить (не раздувая NLP):
- стабильность hold-to-talk / release
- транскрипция (faster-whisper), язык RU/EN
- реальная ручная проверка F9/mic/TTS/Ollama runtime
- streaming TTS
- wake-word provider поверх `VoiceActivationProvider`

Не делать в том же PR: Tauri UI, keyword-роутинг, смешение game_agents в chat.

---

## 9. Предпочтения владельца

- Ответы ассистенту (Cursor) — по делу, по-русски, коротко
- После бага: кратко **почему** + **как** починили
- Коммит/пуш — когда просят; «на сегодня всё» / «хватит» ≈ daily patch + push
- Не обновлять `git config`; при отсутствии identity — author через env (как в daily patches)
- Не force-push на main без явной просьбы

---

## 10. Анти-паттерны (уже отвергнуты)

- Расширять synonym lists / marker tuples под каждую фразу
- Класть Steam/Discord/голос/vision всё в один orchestrator-файл
- Большой UI rewrite до рабочей начинки
- Зависимость только от GUI Ollama Context length без `num_ctx` в API

---

## 11. Чеклист новой сессии на другом ПК

1. `git pull`
2. Прочитать **этот файл** + `AGENTS.md`
3. Не предлагать Tauri/Electron UI, пока пользователь сам не попросит
4. Следующий фичи-шаг по умолчанию: **v0.4 Voice hardening / wake-word**
5. Перед коммитом — только по просьбе; daily patch — по «на сегодня»

---

*Живой документ. При крупных решениях — обновлять вместе с `JARVIS_ARCHITECTURE.md`.*
