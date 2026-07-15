# JARVIS Architecture Plan

**Проект:** AI-Assistant → персональный локальный ассистент уровня «Джарвис»  
**Целевое железо:** RTX 5070 Ti 16GB · 64GB RAM · Intel Core Ultra 7 265KF  
**Статус:** конспект-план (не спецификация реализации)  
**Обновлено:** учтён внешний архитектурный аудит (Core API, Plugin API, MemoryBackend)

---

## 1. Vision

Ассистент, который:

- отвечает голосом и текстом с низкой задержкой;
- понимает контекст ПК (окна, игры, приложения);
- выполняет разрешённые действия одной фразой («включи музыку», «запусти Minecraft»);
- помнит предпочтения и историю;
- позже может вести долгие сценарии (farm / grind) как **отдельный продукт**, не «ещё один if в чате».

**Не цель:** копия фильма (полный автономный контроль ОС без ограничений).  
**Цель:** надёжный локальный помощник с стабильным ядром (Core API) и расширяемыми слоями поверх.

---

## 2. Принцип разработки (анти-правила)

### 2.1 Главный закон

> **Модель думает. Код даёт инструменты. Не пишем словари на каждый случай языка.**

Запрещено расширять ассистента бесконечными keyword-листами вида:

- `if "who is" in q` / `if "who are" in q` / …
- отдельные regex на каждый синоним намерения;
- «ещё одно правило, и точно заработает».

### 2.2 Второй закон (анти–God Object)

> **Orchestrator тонкий. Работа в именованных компонентах с интерфейсами.**

Запрещено складывать в один файл/класс: голос, память, плагины, routing, vision, TTS, planning, game agents.

### 2.3 Что разрешено в коде

| Тип | Примеры | Зачем |
|-----|---------|--------|
| **Инфраструктура** | захват экрана, список окон, запуск процесса | физические возможности |
| **Контракты инструментов** | JSON schema action: `launch_app`, `play_music` | модель выбирает tool |
| **Политика безопасности** | whitelist приложений, confirm на опасное | защита пользователя |
| **Короткие системные принципы** | «понимай замысел, не цепляйся к редкому техчтению» | как у ChatGPT, не чеклист |
| **Hard overrides только для железа** | hotkey F8/F9, single-instance | UX/ОС, не NLP |
| **Интерфейсы / backends** | `MemoryBackend`, `ScreenProvider` | смена реализации без сноса ядра |

### 2.4 Как принимать решения в PR / чате

Перед добавлением логики спросить:

1. Это **инструмент** или **попытка угадать язык**?
2. Справится ли **роутер/LLM с thinking**, если дать tool + контекст?
3. Не размножаем ли мы `if "…"` под новый синоним?
4. Не раздуваем ли **Orchestrator / overlay.py** вместо нового модуля?

Если «угадываем язык» → **не мержить**.  
Если «ещё одна ответственность в оркестратор» → вынести в компонент.

### 2.5 Закрепление в репозитории

- Cursor rule: `.cursor/rules/model-first-reasoning.mdc` (всегда активен)
- Этот документ: источник правды по архитектуре

---

## 3. Целевая схема слоёв

```text
┌──────────────────────────────────────────────────────────────┐
│  UX: Overlay · Voice · Wake-word · Status ("Ready")          │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│  ORCHESTRATOR  (тонкий)                                      │
│  context = builder.build()                                   │
│  plan    = planner.plan(context, utterance)                  │
│  result  = executor.execute(plan)                            │
│  memory.store(...) · ux.emit(...)                            │
└───┬──────────┬──────────┬──────────┬──────────┬──────────────┘
    │          │          │          │          │
┌───▼───┐  ┌───▼───┐  ┌───▼────┐ ┌───▼───┐  ┌──▼──────────┐
│ SENSE │→│CONTEXT│→│ REASON │→│PLANNER│→│ ACT / Tools │
│providers│ │Manager│ │ (LLM)  │ │(1..N) │  │ + Plugins   │
└───────┘  └───────┘  └────────┘ └───────┘  └──────┬───────┘
     ▲                                              │
     │         ┌────────────┐                       │
     └─────────┤  MEMORY    │◄──────────────────────┘
               │  (backend) │
               └────────────┘

Отдельный контур (НЕ в assistant/):
  game_agents/   ← Minecraft Agent и т.п. — другой продукт
  plugins/       ← spotify, steam, discord, obs, browser
```

**Sense / Reason / Act / Memory** остаются стержнем.  
Между ними явно:

| Слой | Зачем |
|------|--------|
| **Context** | один снимок мира для модели (окно, игра, apps, память, время) |
| **Planner** | одна команда **или цепочка** (`Steam → Minecraft → музыка`) |
| **Capabilities** | динамический список доступных tools для модели |
| **Event Bus** *(фаза Core+)* | A не вызывает B напрямую — подписчики реагируют на события |

---

## 4. Core API — устойчивое ядро

Цель: ядро почти не переписывается годами. Всё новое — плагины и providers.

### 4.1 Компоненты ядра (интерфейсы)

| Компонент | Ответственность | Не делает |
|-----------|-----------------|-----------|
| **ContextBuilder / ContextManager** | собирает единый `AssistantContext` | не вызывает LLM |
| **Planner** | план: answer / tool / screen / search / multi-step | не жмёт клавиши |
| **ToolExecutor** | валидация schema + whitelist + выполнение | не парсит русский |
| **MemoryManager** | facade над `MemoryBackend` | не знает про Spotify |
| **ConversationManager** | история диалога в сессии | не знает про OCR |
| **SessionManager** | lifecycle сессии, cancel, kill-switch | не бизнес-логика игр |
| **Orchestrator** | склеивает цикл выше (≤ тонкий glue) | God Object запрещён |
| **CapabilityRegistry** | «что доступно сейчас» для промпта/tools | не `if spotify:` в роутере |

Идеальный оркестратор по сути:

```text
context = builder.build()
plan    = planner.plan(context, utterance)
result  = executor.execute(plan)
memory.store(result)
ux.emit(result)
```

### 4.2 Sense providers (не привязывать Vision к «скриншоту»)

| Provider | Роль |
|----------|------|
| **WindowProvider** | активное окно, title, process, game detect |
| **ScreenProvider** | сырой кадр (monitor / region) |
| **OCRProvider** | текст с кадра |
| **VisionProvider** | VL-модель → описание |
| **AudioIn / AudioOut** | STT / TTS |
| **HostInventoryProvider** | Steam / Discord / плеер запущены? |

Меняем движок OCR/Vision — меняем provider, не Orchestrator.

### 4.3 Event Bus (рекомендация аудита)

Постепенно переходить с прямых вызовов на события:

- `UserUtterance`, `ContextUpdated`, `PlanReady`
- `ActionRequested`, `ActionCompleted`, `ActionFailed`
- `SpeechStarted`, `KillSwitch`

Это спасает проект через 1–2 года от паутины `A→B→C`.

---

## 5. Модули по доменам

### 5.1 Context — «суперсила»

Один объект на запрос (пример полей):

```text
AssistantContext
├── window / process / title
├── active_game (если есть)
├── running_apps (inventory)
├── media_session (что играет)
├── clipboard (опц., с политикой privacy)
├── memory_slice (preferences + recent facts)
├── time / locale
└── capabilities[]  ← что модель может вызвать прямо сейчас
```

**Требование:** Context — структурированный JSON для модели, не простыня эвристик.

---

### 5.2 Reason — «мозг»

| Модуль | Назначение |
|--------|------------|
| **ModelRouter** | профиль: laptop / desktop / deep / fast-act |
| **ChatBrain** | основной ответ (thinking на desktop) |
| **VisionBrain** | через VisionProvider |
| **SearchTool** | web — решение модели, не keyword |
| **GameKB** | факты игр (данные ≠ правила языка) |

#### Профили моделей (RTX 5070 Ti 16GB)

| Профиль | Текст | Vision | Режим |
|---------|-------|--------|-------|
| `laptop` | qwen3:8b / 14b | moondream / qwen2.5vl:7b | think опционально |
| `desktop` | **qwen3:30b-a3b** | qwen2.5vl:7b | **think on** |
| `deep` | deepseek-r1:14b | — | всегда рассуждает |
| `fast-act` | компактная для tool-call | — | только команды |

---

### 5.3 Planner — отдельно от «просто ответить»

| Сценарий | План |
|----------|------|
| Вопрос «who are KISS» | `search?` → `answer` |
| «открой Discord» | один step: `launch_app` |
| «запусти Steam, потом Minecraft, потом музыку» | **цепочка** steps |

Planner выдаёт структуру вроде:

```json
{
  "steps": [
    {"type": "tool", "action": "launch_app", "args": {"id": "steam"}},
    {"type": "tool", "action": "launch_app", "args": {"id": "minecraft"}},
    {"type": "tool", "action": "media_play", "args": {}}
  ]
}
```

Reason (LLM) **предлагает**; ToolExecutor **проверяет и выполняет**.

---

### 5.4 Act + Plugin API (не свалка actions)

**Запрещено:** один огромный `ActionRegistry` на все приложения мира.

**Сделано так:**

```text
plugins/
  windows/     # focus, minimize (осторожно)
  games/       # steam app-id, launchers
  media/       # spotify / OS media keys
  system/      # volume, screenshots (safe subset)
  browser/     # опционально позже
  network/     # опционально позже
```

Каждый плагин:

- объявляет **capabilities** + JSON schema;
- проходит **whitelist / ConfirmGate**;
- регистрируется в `CapabilityRegistry` без правки ядра.

Базовый контракт действия:

```json
{
  "action": "launch_app",
  "args": { "id": "minecraft" },
  "confidence": 0.86,
  "needs_confirm": false
}
```

---

### 5.5 Memory — интерфейс с первого дня

Сейчас реализация может остаться JSON. **API — уже backend-agnostic.**

```text
MemoryBackend (interface)
├── JsonMemoryBackend      ← сейчас
├── SqliteMemoryBackend    ← когда JSON тесен
├── ChromaMemoryBackend    ← семантика / long-term (фаза 5+)
└── QdrantMemoryBackend    ← только если реально нужен; не MVP
```

Домены памяти (логические, не «ещё файлы вразброс»):

| Домен | Содержание |
|-------|------------|
| Preferences | стиль, язык, wake-word, «не трогай античит» |
| Episodic | короткий диалог |
| HostFacts | установленные игры, любимый плеер |
| Corrections | явные поправки пользователя |
| Summaries *(позже)* | сжатие длинных сессий |

**Neo4j / тяжёлый RAG:** не в Core. Только если появится задача, которой JSON/SQLite/Chroma не хватает (см. аудит RejuveBio — другой продукт).

---

### 5.6 Game Agents — отдельный продукт

```text
assistant/        ← чат + Sense + Reason + Act (помощник)
game_agents/      ← долгоживущие сценарии (farm), свой runtime
plugins/          ← интеграции приложений
```

**Не смешивать.** Chat Assistant ≠ Minecraft Agent.  
Общее: Context / Memory / Event Bus / kill-switch.  
Разное: зависимости, цикл, ToS, логирование, риск бана.

---

### 5.7 UX

| Элемент | Требование |
|---------|------------|
| Overlay | статус tools («Launching…», «Listening…») |
| Wake-word | опционально |
| One-shot | голос → action без длинного чата |
| Kill-switch | глобальный хоткей «стоп всё» |

---

## 6. Целевой layout репозитория

```text
assistant/           # ядро помощника (тонкий)
  core/              # ContextBuilder, Planner, Executor, Session, EventBus
  sense/             # providers
  reason/            # llm, router, search
  memory/            # MemoryManager + backends
  ux/                # overlay, hotkeys
plugins/             # spotify, steam, discord, …
game_agents/         # автономные игровые агенты
docs/                # этот план
AGENTS.md
.cursor/rules/
```

Переезд кода — **постепенный** (не big-bang). Сначала интерфейсы, потом вынос из жирного `overlay.py` / `llm.py`.

---

## 7. Roadmap

Совмещены исходные фазы и версия аудита v0.2–v1.0.

| Версия | Содержание | Критерий готовности |
|--------|------------|---------------------|
| **v0.1 / Phase 0** | Профили laptop/desktop/deep; thinking policy; model-first закреплён | десктоп думает; нет новых keyword-list PR |
| **v0.2** | WindowProvider + **ContextManager**; ActionRegistry v1 (мало actions) | «что у меня открыто?» без F8 |
| **v0.3** | **Plugin API**; MemoryBackend interface (JSON impl); тонкий Orchestrator | плагин подключается без правки ядра |
| **v0.4** | Voice pipeline; wake-word; streaming TTS | разговор без обязательного F9 |
| **v0.5** | Screen/OCR/Vision providers; Event Bus v1 | смена OCR/VL без сноса Orchestrator |
| **v0.6** | Plugins: Steam / media / Discord / OBS (по необходимости) | ≥5 whitelist-действий с голоса |
| **v0.7** | Multi-step Planner; long-term memory backend; kill-switch зрелый | цепочка Steam→игра→музыка |
| **v1.0** | Локальный Джарвис: ПК-контекст + apps + голос + офлайн + плагины | см. §9 |
| **позже** | `game_agents/` SDK; autonomous grind (ToS!) | один осознанный сценарий, не «бот для всего» |

### Ближайший конкретный шаг (после утверждения)

1. Профили моделей + thinking на desktop.  
2. **ContextManager** + WindowProvider.  
3. Контракт **Plugin / Action** (schema первых 5 действий).  
4. **MemoryBackend** interface поверх текущего JSON (без смены хранения).

Порядок 2–4 можно менять; законы §2.1–2.2 — нет.

---

## 8. Нефункциональные требования

| Требование | Цель |
|------------|------|
| Latency (desktop, warm) | первый токен ~1.5–3 с |
| Privacy | локально по умолчанию; web / clipboard — явно |
| Safety | нет произвольного shell от модели |
| Reliability | single-instance, логи, kill-switch |
| Extensibility | плагин без правки Core |
| Switchability | модель = профиль; память = backend; vision = provider |

---

## 9. Definition of Done — «хороший помощник» (не фильм)

1. Неоднозначные вопросы **без** новых regex.  
2. Знает активное приложение/игру без скрина.  
3. ≥5 whitelist-действий с голоса/текста через Plugin API.  
4. Desktop: thinking + приемлемая скорость.  
5. Kill-switch работает.  
6. Orchestrator остаётся тонким (нет God Object на 4k LOC).

Киношный уровень — горизонт, не спринт.

---

## 10. Риски

| Риск | Митигация |
|------|-----------|
| Keyword-NLP sprawl | §2.1 + Cursor rule |
| Orchestrator God Object | §2.2 + Core interfaces |
| ActionRegistry dump | Plugin API по категориям |
| Смешение chat и game agent | пакет `game_agents/` отдельно |
| Memory JSON ад через год | `MemoryBackend` с v0.3 |
| Vision зашит в screenshot path | Sense providers |
| 16GB VRAM / 32B | 30b-a3b / R1:14b |
| Бан за автоигру | ToS, kill-switch, только осознанные сценарии |
| Тяжёлый RAG раньше времени | Qdrant/Neo4j не в MVP |

---

## 11. Связь с внешним аудитом RejuveBio

RejuveBio (Flask + OpenAI/Gemini + Neo4j + Qdrant) — **облачный RAG API**, другой продукт.  
Оттуда берём практики (тесты, контракты, обновление deps), **не** стек как основу десктоп-Джарвиса.

---

*Документ живой. Не плодить параллельные «уставы» — править этот файл.*
