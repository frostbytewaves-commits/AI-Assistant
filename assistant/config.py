from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from game_data.paths import resolve_games_dir, DEFAULT_MINECRAFT_PLAY_VERSION
from .language import LANGUAGE_MATCH_RULE


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"
SCREENSHOT_DIR = DATA_DIR / "screenshots"
AUDIO_DIR = DATA_DIR / "audio"
MEMORY_PATH = DATA_DIR / "memory.json"
LOCAL_CONFIG_PATH = BASE_DIR / "local_config.json"

OLLAMA_URL = "http://localhost:11434"

# Профили (см. docs/JARVIS_ARCHITECTURE.md):
#   laptop  — ноут / отпуск: qwen3:14b + thinking
#   desktop — домПК 16GB VRAM: qwen3:30b-a3b + thinking (fallback → 14b)
#   deep    — максимум рассуждения: deepseek-r1:14b
# Алиасы: gaming / balance / quality — для совместимости
_DEFAULT_MODEL_PROFILE = "laptop"

_PROFILES: dict[str, dict[str, object]] = {
    "laptop": {
        # Vacation / iGPU-CPU: smaller text model + thinking; don't load vision until Screen.
        "text": "qwen3:8b",
        "text_fallbacks": ("qwen3:8b", "qwen3:14b", "qwen2.5:7b"),
        "vision": "moondream",
        "vision_fallbacks": ("moondream", "qwen2.5vl:7b", "llava:7b"),
        "use_intent_router": True,
        "enable_thinking": True,
        "text_timeout_sec": 240,
        "warmup_vision": False,
    },
    "desktop": {
        "text": "qwen3:30b-a3b",
        "text_fallbacks": ("qwen3:30b-a3b", "qwen3:14b", "qwen3:8b"),
        "vision": "qwen2.5vl:7b",
        "vision_fallbacks": ("qwen2.5vl:7b", "minicpm-v", "llava:7b", "moondream"),
        "use_intent_router": True,
        "enable_thinking": True,
        "text_timeout_sec": 360,
        "warmup_vision": True,
    },
    "deep": {
        "text": "deepseek-r1:14b",
        "text_fallbacks": ("deepseek-r1:14b", "qwen3:14b", "qwen3:8b"),
        "vision": "qwen2.5vl:7b",
        "vision_fallbacks": ("qwen2.5vl:7b", "moondream", "llava:7b"),
        "use_intent_router": True,
        "enable_thinking": True,
        "text_timeout_sec": 420,
        "warmup_vision": False,
    },
    "gaming": {
        "text": "qwen3:8b",
        "text_fallbacks": ("qwen3:8b", "qwen2.5:7b"),
        "vision": "moondream",
        "vision_fallbacks": ("moondream", "llava:7b", "qwen2.5vl:7b"),
        "use_intent_router": False,
        "enable_thinking": False,
        "text_timeout_sec": 180,
        "warmup_vision": False,
    },
    "balance": {
        "text": "qwen3:8b",
        "text_fallbacks": ("qwen3:8b", "qwen2.5:7b"),
        "vision": "minicpm-v",
        "vision_fallbacks": ("minicpm-v", "llava:7b", "moondream", "qwen2.5vl:7b"),
        "use_intent_router": False,
        "enable_thinking": False,
        "text_timeout_sec": 180,
        "warmup_vision": False,
    },
    # legacy alias → laptop-like smart chat with 14b when GPU allows
    "quality": {
        "text": "qwen3:14b",
        "text_fallbacks": ("qwen3:14b", "qwen3:8b", "qwen2.5:7b"),
        "vision": "qwen2.5vl:7b",
        "vision_fallbacks": ("qwen2.5vl:7b", "minicpm-v", "llava:13b", "llava:7b", "moondream"),
        "use_intent_router": True,
        "enable_thinking": True,
        "text_timeout_sec": 300,
        "warmup_vision": False,
    },
}


def _read_local_config() -> dict:
    if not LOCAL_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def resolve_model_profile() -> str:
    env = (os.environ.get("AI_ASSISTANT_PROFILE") or "").strip().lower()
    if env:
        return env
    local = _read_local_config()
    local_profile = str(local.get("model_profile") or "").strip().lower()
    if local_profile:
        return local_profile
    return _DEFAULT_MODEL_PROFILE


MODEL_PROFILE = resolve_model_profile()
_active = _PROFILES.get(MODEL_PROFILE, _PROFILES["laptop"])

TEXT_MODEL = str(_active["text"])
TEXT_MODEL_FALLBACKS = tuple(_active["text_fallbacks"])  # type: ignore[arg-type]
VISION_MODEL = str(_active["vision"])
VISION_MODEL_FALLBACKS = tuple(_active["vision_fallbacks"])  # type: ignore[arg-type]
_DEFAULT_USE_INTENT_ROUTER = bool(_active["use_intent_router"])
_DEFAULT_ENABLE_THINKING = bool(_active.get("enable_thinking", False))
_DEFAULT_TEXT_TIMEOUT_SEC = int(_active.get("text_timeout_sec", 180))
_DEFAULT_WARMUP_VISION = bool(_active.get("warmup_vision", False))

STT_MODEL = "whisper"

TTS_VOICE = "en-US-GuyNeural"

HOTKEY_SCREEN = "f8"
HOTKEY_VOICE = "f9"
HOTKEY_TOGGLE_SPEAK = "f10"

SYSTEM_PROMPT = (
    "You are a smart universal AI assistant on the user's computer — like a knowledgeable friend chatting, "
    "not a search-engine brief and not a Wiki page. "
    "You help with everyday questions, the desktop, software, and (when relevant) games. "
    + LANGUAGE_MATCH_RULE
    + " "
    "Infer what the user actually means from wording and context; do not latch onto an "
    "unlikely technical reading when a natural everyday reading fits better. "
    "DEFAULT LENGTH for casual asks (who/what/is X, quick facts): STRICTLY 2–4 short sentences. "
    "Say what it is, one or two memorable details (people/dates/why famous), then stop. "
    "Do not write a long packed paragraph; do not list every hit, era, or reunion unless asked. "
    "If they want more, they can say 'tell me more'. "
    "Go longer ONLY when they clearly ask to explain, compare, plan, solve, or give a full guide. "
    "Use general knowledge, Host context (open windows/apps), screen/OCR, and web search when provided. "
    "When Host context lists open windows, use it to answer what is open or running — do not ask for a screenshot for that. "
    "Use a screenshot only when visual content matters. "
    "Do not invent facts: if information is missing or freshness matters and no search result is available, say so. "
    "Describe the screen honestly. Do not invent game elements when it is not a game. "
    "Only apply game-specific assumptions (vanilla/DLC/mods/platform) when the user is clearly talking about a game "
    "or a supported game is open."
)

MINECRAFT_SYSTEM_PROMPT = (
    "Minecraft is currently open or the question is clearly about Minecraft. "
    "Answer as a game specialist for this title. "
    "For drops and recipes, use only the Game Database block, not memory. "
    "HUD: hearts mean health and drumstick icons mean hunger, but mention them only when visible and relevant. "
    "For farms, derive the answer from spawn/generation rules, player action, transport, kill/processing, collection, and bottlenecks. "
    "Default to vanilla/base-game advice first. Do not include mods, datapacks, or server-specific mechanics unless the user confirmed them. "
    "Mention Java/Bedrock/version uncertainty when it affects a farm. "
    "Do not give exact numbers unless they come from provided database/search context."
)

ONI_SYSTEM_PROMPT = (
    "The user is playing or clearly asking about Oxygen Not Included — a complex colony management simulation. "
    "Act as an expert ONI advisor who understands systems design: gases, liquids, power, heat, "
    "food, morale, ranching, automation, and duplicant needs. "
    "Qualify advice by tech stage, DLC/planetoid, and available resources when they matter. "
    "Default to base-game advice first unless DLC is confirmed. "
    "Do not give exact numbers unless they come from provided database/search context."
)

ONI_FACT_ADDENDUM = (
    "For exact building stats, element properties, and research names, use ONLY numbers from the Game Database block."
)

# Used only when a supported game context is active (window or explicit game topic).
GAME_ADVISORY_BRIEF_ADDENDUM = (
    "Game strategy / how-to question — this is the FIRST (brief) pass only.\n"
    "Answer in 2-4 sentences: the core idea and where to start. "
    "If several valid approaches exist (designs, farms, setups), name them briefly — "
    "do NOT give step-by-step guides or long bullet lists yet.\n"
    "Choose options by mechanic families, not by memorized answer templates. "
    "If the game/version/mod context is ambiguous, state the assumed default in one short phrase. "
    "For item farming/acquisition, only list actual sources: crafting output, block/mob drops, loot, trading/bartering, or explicit salvage; never infer reverse-crafting. "
    "End your reply with exactly this block (3-4 options; titles in the user's language):\n"
    "---options---\n"
    "1|Short title|One-line teaser shown to the user\n"
    "2|Short title|One-line teaser\n"
    "---end---\n"
    "Each option = one concrete variant the user can pick for a full build guide. "
    "Nothing after ---end---. "
    "The ---options--- block is REQUIRED — without it the UI cannot show choices.\n"
    "If the user asked about Minecraft XP, options must be XP/orb mob farms — not crop farms. "
    "For Minecraft XP use these exact titles when possible: "
    "Zombified Piglin Farm, Guardian Farm, Blaze / Mob Grinder, Enderman Farm. "
    "Never echo the user's words back without adding useful game advice."
)

ADVISORY_BRIEF_ADDENDUM = GAME_ADVISORY_BRIEF_ADDENDUM

GAME_ADVISORY_EXPAND_ADDENDUM = (
    "The user selected ONE follow-up option from your previous brief game answer. "
    "Give the COMPLETE detailed guide for ONLY that variant: step-by-step build/setup, "
    "materials, layout, redstone/automation if relevant, trade-offs, and common mistakes. "
    "Derive the guide from the Game Mechanics Formula Layer: source, trigger, transport, processing, collection, bottlenecks. "
    "Use the Game Database for exact item names, recipes, mob drops, and block stats when available. "
    "For item acquisition, prove that the selected method actually outputs the requested item; do not use recipes where the requested item is only an ingredient. "
    "If exact dimensions or numbers are not sourced, label them as typical/approximate or omit them. "
    "Use headers and bullet lists. Do NOT repeat the brief overview. "
    "Do NOT add another ---options--- block."
)

ADVISORY_EXPAND_ADDENDUM = GAME_ADVISORY_EXPAND_ADDENDUM

MINECRAFT_XP_EXPAND_FACTS = (
    "Minecraft XP facts (never contradict these):\n"
    "- XP drops as green orbs on the ground; ONLY the player collects them by walking into them.\n"
    "- Hoppers, chests, and furnaces do NOT collect mob XP orbs.\n"
    "- Furnaces only store XP from items smelted through that specific furnace.\n"
    "- Never place torches ON a monster spawner block — it stops spawning.\n"
    "- Soul torches reduce spawn rates nearby — do not surround a spawner with them.\n"
    "- For spawner farms: light other caves within 128 blocks; keep spawner room dark.\n"
    "- Typical drop height for spawner XP: ~22 blocks leaves mobs at half a heart for a player kill.\n"
    "- Lava kills fast but can destroy drops; it does not store XP."
)

# Backward-compatible aliases
ONI_ADVISORY_BRIEF_ADDENDUM = ADVISORY_BRIEF_ADDENDUM
ONI_ADVISORY_EXPAND_ADDENDUM = ADVISORY_EXPAND_ADDENDUM
ONI_ADVISORY_ADDENDUM = ADVISORY_BRIEF_ADDENDUM

VISION_DESCRIBE_PROMPT = (
    "Screenshot. Describe only what is clearly visible. "
    "Do not assume Minecraft or any game unless blocky gameplay is obvious. English OK."
)


@dataclass
class AssistantConfig:
    base_dir: Path = BASE_DIR
    screenshot_dir: Path = SCREENSHOT_DIR
    audio_dir: Path = AUDIO_DIR
    memory_path: Path = MEMORY_PATH
    ollama_url: str = OLLAMA_URL
    text_model: str = TEXT_MODEL
    text_model_fallbacks: tuple[str, ...] = TEXT_MODEL_FALLBACKS
    vision_model: str = VISION_MODEL
    vision_model_fallbacks: tuple[str, ...] = VISION_MODEL_FALLBACKS
    stt_model: str = STT_MODEL
    tts_voice: str = TTS_VOICE
    hotkey_screen: str = HOTKEY_SCREEN
    hotkey_voice: str = HOTKEY_VOICE
    hotkey_toggle_speak: str = HOTKEY_TOGGLE_SPEAK
    system_prompt: str = SYSTEM_PROMPT
    minecraft_system_prompt: str = MINECRAFT_SYSTEM_PROMPT
    oni_system_prompt: str = ONI_SYSTEM_PROMPT
    vision_describe_prompt: str = VISION_DESCRIBE_PROMPT
    speak_answers: bool = True
    use_vision: bool = True
    use_two_stage: bool = True
    web_search_enabled: bool = True
    web_search_max_results: int = 5
    use_faster_whisper: bool = True
    whisper_model_size: str = "small"
    whisper_language: str | None = None  # None = auto-detect; better for RU/EN mixed phrases
    reply_language: str = "auto"  # auto | en | ru — auto mirrors the user's question language
    whisper_vad_filter: bool = True
    min_voice_duration_sec: float = 0.45
    min_voice_rms: int = 350
    input_device: str | int | None = None  # None = авто; имя (часть) или индекс
    streaming: bool = True
    ollama_keep_alive: str = "30m"
    sample_rate: int = 16000
    capture_delay_sec: float = 0.35  # extra margin after hide before grab
    always_capture_screen: bool = False
    ocr_lang: str = "rus+eng"
    ocr_max_chars: int = 2500
    skip_vision_if_ocr_chars: int = 400
    max_tokens: int = 2048
    vision_max_tokens: int = 512
    vision_timeout_sec: int = 120
    text_timeout_sec: int = _DEFAULT_TEXT_TIMEOUT_SEC
    fast_mode: bool = True
    use_intent_router: bool = _DEFAULT_USE_INTENT_ROUTER
    enable_thinking: bool = _DEFAULT_ENABLE_THINKING
    warmup_vision: bool = _DEFAULT_WARMUP_VISION
    use_game_database: bool = True
    default_game_id: str = ""  # empty = no forced game; set only when a game is detected

    minecraft_play_version: str = DEFAULT_MINECRAFT_PLAY_VERSION
    games_data_dir: Path = field(default_factory=resolve_games_dir)
    tools_enabled: bool = True
    intent_timeout_sec: int = 30
    tesseract_cmd: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

    def ensure_dirs(self) -> None:
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self.memory_path.parent.mkdir(parents=True, exist_ok=True)
