import base64
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout, as_completed
from pathlib import Path
from typing import Callable

import requests

from .config import (
    AssistantConfig,
    MODEL_PROFILE,
    ADVISORY_BRIEF_ADDENDUM,
    ADVISORY_EXPAND_ADDENDUM,
    MINECRAFT_XP_EXPAND_FACTS,
    ONI_FACT_ADDENDUM,
)
from .game_db import GAME_DETECT_PROMPT, GameKnowledgeBase
from .game_mechanics import build_mechanics_context, infer_mechanics_game, looks_like_game_question
from .intent import (
    FOCUS_VISION_PROMPTS,
    ROUTER_SYSTEM,
    ROUTER_USER_TEMPLATE,
    QueryIntent,
    is_advisory_question,
    is_minecraft_question,
    is_oni_question,
    is_oni_strategy_question,
    plan_attached_screen_query,
    effective_screen_question,
    question_needs_screen,
    should_auto_capture_screen,
)
from .language import (
    answer_language_rule,
    game_database_header,
    resolve_response_language,
)
from .screen_context import ScreenContext
from .minecraft_mobs import MOB_IDENTIFY_PROMPT, is_mob_or_drop_question, normalize_mob_observation
from .ocr import extract_text
from .search import build_screen_search_query, build_search_query, web_search

StatusCallback = Callable[[str], None]
TokenCallback = Callable[[str], None]


class OllamaClient:
    def __init__(self, config: AssistantConfig) -> None:
        self.config = config
        self.base_url = config.ollama_url.rstrip("/")
        self._installed_models: set[str] | None = None
        self._resolved_text_model: str | None = None
        self._resolved_vision_model: str | None = None
        self._game_kb = GameKnowledgeBase(
            config.games_data_dir,
            config.default_game_id,
        )

    def _reply_lang(self, question: str) -> str:
        return resolve_response_language(question, self.config.reply_language)

    def _md_rule(self, question: str) -> str:
        return answer_language_rule(self._reply_lang(question))

    def list_models(self) -> set[str]:
        if self._installed_models is not None:
            return self._installed_models
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()
            models = response.json().get("models", [])
            names: set[str] = set()
            for item in models:
                name = item.get("name", "")
                if not name:
                    continue
                names.add(name)
                names.add(name.split(":")[0])
            self._installed_models = names
            return names
        except Exception:
            self._installed_models = set()
            return self._installed_models

    def has_model(self, model_name: str) -> bool:
        if not model_name:
            return False
        installed = self.list_models()
        base = model_name.split(":")[0]
        return model_name in installed or base in installed

    def _pick_model(self, preferred: str, fallbacks: tuple[str, ...]) -> str | None:
        candidates = (preferred, *fallbacks)
        seen: set[str] = set()
        for name in candidates:
            if name in seen:
                continue
            seen.add(name)
            if self.has_model(name):
                return name
        return None

    def resolve_text_model(self) -> str:
        if self._resolved_text_model:
            return self._resolved_text_model
        picked = self._pick_model(self.config.text_model, self.config.text_model_fallbacks)
        self._resolved_text_model = picked or self.config.text_model
        return self._resolved_text_model

    def resolve_vision_model(self) -> str | None:
        if self._resolved_vision_model is not None:
            return self._resolved_vision_model or None
        picked = self._pick_model(self.config.vision_model, self.config.vision_model_fallbacks)
        self._resolved_vision_model = picked or ""
        return picked

    @staticmethod
    def _is_thinking_model(model: str) -> bool:
        base = model.split(":")[0].lower()
        return base.startswith("qwen3") or "deepseek-r1" in base or base.endswith("-r1")

    def _with_think_flag(self, payload: dict, model: str) -> dict:
        if self._is_thinking_model(model):
            payload["think"] = False
        return payload

    @staticmethod
    def _message_text(message: dict) -> str:
        content = (message.get("content") or "").strip()
        if content:
            return OllamaClient._strip_thinking(content)
        return ""

    def _resolve_system_prompt(
        self,
        screen_context: ScreenContext | None = None,
        *,
        minecraft_question: bool = False,
        oni_question: bool = False,
        active_game: str | None = None,
        user_message: str = "",
        advisory_mode: str = "none",
    ) -> str:
        ctx = screen_context or ScreenContext()
        game = active_game or ctx.active_game
        parts = [self.config.system_prompt]

        if game == "oni" or oni_question or ctx.oni_window:
            parts.append(self.config.oni_system_prompt)
        elif game == "minecraft" or minecraft_question or ctx.minecraft_window:
            parts.append(self.config.minecraft_system_prompt)

        mechanics_game = infer_mechanics_game(user_message, game)
        if mechanics_game or looks_like_game_question(user_message):
            parts.append(
                build_mechanics_context(
                    user_message,
                    game_id=mechanics_game,
                    active_game=ctx.active_game,
                    advisory_mode=advisory_mode,
                )
            )

        if advisory_mode == "expand":
            parts.append(ADVISORY_EXPAND_ADDENDUM)
            if game == "minecraft" or minecraft_question:
                parts.append(MINECRAFT_XP_EXPAND_FACTS)
        elif advisory_mode == "brief" or (
            advisory_mode == "none" and is_advisory_question(user_message)
        ):
            parts.append(ADVISORY_BRIEF_ADDENDUM)
        elif game == "oni" or oni_question or ctx.oni_window:
            parts.append(ONI_FACT_ADDENDUM)

        if ctx.oni_window:
            parts.append("Oxygen Not Included is currently open on screen.")
        elif ctx.minecraft_window:
            parts.append("Minecraft is currently open on screen.")

        return "\n\n".join(parts)

    def _resolve_game_id(
        self,
        question: str,
        screen_context: ScreenContext | None = None,
    ) -> str | None:
        ctx = screen_context or ScreenContext()
        explicit_mechanics_game = infer_mechanics_game(question, None)
        if explicit_mechanics_game == "noita":
            return None
        if explicit_mechanics_game in {"minecraft", "oni"}:
            return explicit_mechanics_game
        if ctx.oni_window or is_oni_question(question):
            return "oni"
        if ctx.minecraft_window or is_minecraft_question(question):
            return "minecraft"
        q = question.lower()
        mc_hints = (
            "xp farm", "mob farm", "spawner", "piglin", "zombified",
            "iron farm", "gold farm", "villager", "redstone", "опыт", "ферм",
            "свинозомби", "grinder", "enderman farm", "creeper farm",
            " xp", "experience", "level up", "levels",
        )
        if any(h in q for h in mc_hints):
            return "minecraft"
        if self.config.use_game_database and self._game_kb.has_recipe_target_match("minecraft", question):
            return "minecraft"
        return None

    def ask_text(
        self,
        user_message: str,
        on_status: StatusCallback | None = None,
        on_token: TokenCallback | None = None,
        *,
        screen_context: ScreenContext | None = None,
        minecraft_question: bool = False,
        oni_question: bool = False,
        active_game: str | None = None,
        source_question: str | None = None,
        advisory_mode: str = "none",
    ) -> str:
        lang_q = source_question or user_message
        system = self._resolve_system_prompt(
            screen_context,
            minecraft_question=minecraft_question,
            oni_question=oni_question,
            active_game=active_game,
            user_message=lang_q,
            advisory_mode=advisory_mode,
        )
        if self.config.streaming and on_token:
            return self.ask_text_stream(
                user_message,
                on_status,
                on_token,
                system=system,
                source_question=lang_q,
            )
        return self._chat(
            self.resolve_text_model(),
            user_message,
            on_status=on_status,
            system=system,
        )

    def ask_text_stream(
        self,
        user_message: str,
        on_status: StatusCallback | None = None,
        on_token: TokenCallback | None = None,
        *,
        system: str | None = None,
        source_question: str | None = None,
    ) -> str:
        self._status(on_status, "Thinking…")
        lang_q = source_question or user_message
        lang_rule = answer_language_rule(self._reply_lang(lang_q))
        prompt = (
            f"{user_message}\n\n"
            f"{lang_rule} Give as much detail as needed for a complete answer; "
            "if the question is simple, do not over-explain."
        )
        return self._stream_chat(
            self.resolve_text_model(),
            [
                {"role": "system", "content": system or self.config.system_prompt},
                {"role": "user", "content": prompt + " /no_think"},
            ],
            on_token,
            max_tokens=self.config.max_tokens,
            timeout=self.config.text_timeout_sec,
        )

    @staticmethod
    def _parse_intent_json(raw: str) -> QueryIntent:
        text = OllamaClient._strip_thinking(raw.strip())
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("JSON not found")
        data = json.loads(match.group())
        pipeline = str(data.get("pipeline", "vision_then_text"))
        if pipeline not in ("text_only", "vision_answer", "vision_then_text"):
            pipeline = "vision_then_text" if data.get("needs_screen") else "text_only"
        focus = str(data.get("focus", "none"))
        if focus not in FOCUS_VISION_PROMPTS:
            focus = "none"
        return QueryIntent(
            needs_screen=bool(data.get("needs_screen", True)),
            needs_web=bool(data.get("needs_web", False)),
            pipeline=pipeline,
            focus=focus,
            hint=str(data.get("hint", ""))[:200],
        )

    def plan_query(
        self,
        question: str,
        *,
        in_game: bool = True,
        force_screen: bool = False,
        on_status: StatusCallback | None = None,
        screen_context: ScreenContext | None = None,
    ) -> QueryIntent:
        always_screen = force_screen or self.config.always_capture_screen
        auto_capture = should_auto_capture_screen(question, always_capture=always_screen)
        ctx = screen_context or ScreenContext()
        game_open = ctx.active_game is not None

        if not self.config.use_intent_router:
            if auto_capture and game_open:
                intent = QueryIntent.fallback_in_game(question)
            elif auto_capture:
                intent = QueryIntent.screen_describe(question)
            else:
                intent = QueryIntent.fallback_text(question)
        else:
            self._status(on_status, "Understanding…")
            if ctx.oni_window:
                context = "Oxygen Not Included is open; a game screenshot may be available"
            elif ctx.minecraft_window:
                context = "Minecraft is open; a game screenshot may be available"
            else:
                context = "the user is on a computer desktop or app; it is not necessarily a supported game"
            user_msg = ROUTER_USER_TEMPLATE.format(context=context, question=question)
            try:
                raw = self._chat(
                    self.resolve_text_model(),
                    user_msg,
                    system=ROUTER_SYSTEM,
                    max_tokens=120,
                    timeout=self.config.intent_timeout_sec,
                )
                intent = self._parse_intent_json(raw)
            except Exception:
                intent = (
                    QueryIntent.fallback_in_game(question)
                    if game_open and auto_capture
                    else QueryIntent.fallback_text(question)
                )

        if question_needs_screen(question):
            intent.needs_screen = True
            if intent.pipeline == "text_only":
                intent.pipeline = "vision_then_text" if game_open else "vision_answer"
        elif not auto_capture:
            intent.needs_screen = False
            intent.pipeline = "text_only"
            intent.focus = "none"
        return intent

    def plan_attached_screen_query(
        self,
        question: str,
        screen_context: ScreenContext | None = None,
        on_status: StatusCallback | None = None,
    ) -> QueryIntent:
        """Plan intent when the user already captured a screenshot (F8 flow)."""
        ctx = screen_context or ScreenContext()
        q = question.strip()
        if not q or not self.config.use_intent_router:
            return plan_attached_screen_query(q, ctx)

        self._status(on_status, "Understanding…")
        if ctx.oni_window:
            context = (
                "The user already captured a screenshot of Oxygen Not Included and may ask about it."
            )
        elif ctx.minecraft_window:
            context = (
                "The user already captured a screenshot of Minecraft and may ask about it."
            )
        elif ctx.active_game:
            context = "The user already captured a game screenshot and may ask about it."
        else:
            context = (
                "The user already captured a desktop/app screenshot and may ask about it."
            )
        user_msg = ROUTER_USER_TEMPLATE.format(context=context, question=q)
        try:
            raw = self._chat(
                self.resolve_text_model(),
                user_msg,
                system=ROUTER_SYSTEM,
                max_tokens=120,
                timeout=self.config.intent_timeout_sec,
            )
            intent = self._parse_intent_json(raw)
        except Exception:
            intent = plan_attached_screen_query(q, ctx)

        intent.needs_screen = True
        if intent.pipeline == "text_only":
            intent.pipeline = "vision_then_text" if ctx.active_game else "vision_answer"
        return intent

    def execute_query(
        self,
        question: str,
        image_path: Path | None,
        intent: QueryIntent,
        on_status: StatusCallback | None = None,
        on_token: TokenCallback | None = None,
        screen_context: ScreenContext | None = None,
        lang_question: str | None = None,
        advisory_mode: str = "none",
        active_game: str | None = None,
        conversation_context: str = "",
    ) -> str:
        ctx = screen_context or ScreenContext()
        lang_q = lang_question if lang_question is not None else question
        if image_path is not None:
            intent.needs_screen = True
            if intent.pipeline == "text_only":
                intent.pipeline = "vision_then_text" if ctx.active_game else "vision_answer"
        if intent.pipeline == "text_only" or not intent.needs_screen:
            return self._answer_text_only(
                question, intent, on_status, on_token, ctx,
                lang_question=lang_q, advisory_mode=advisory_mode,
                active_game=active_game, conversation_context=conversation_context,
            )
        if image_path is None:
            raise RuntimeError("A screenshot is required for this question")
        if not self.config.use_vision or not self.resolve_vision_model():
            raise RuntimeError("Vision model is not installed")
        if intent.pipeline == "vision_answer" or not ctx.active_game:
            return self._ask_vision_answer(
                question, image_path, intent, on_status, on_token, ctx,
                lang_question=lang_q, advisory_mode=advisory_mode,
                conversation_context=conversation_context,
            )
        return self._ask_vision_then_text(
            question, image_path, intent, on_status, on_token, ctx,
            lang_question=lang_q, advisory_mode=advisory_mode,
            conversation_context=conversation_context,
        )

    def _detect_game(self, image_path: Path) -> str | None:
        if not self.config.use_game_database:
            return None
        try:
            raw = self._vision_chat(
                self.resolve_vision_model(),
                image_path,
                GAME_DETECT_PROMPT,
                max_tokens=24,
                on_token=None,
            )
            return self._game_kb.parse_game_response(raw)
        except Exception:
            return None

    def _append_game_database(
        self,
        parts: list[str],
        game_id: str,
        question: str,
        observation: str = "",
        *,
        advisory_mode: str = "none",
        lang_question: str | None = None,
    ) -> None:
        if not self.config.use_game_database:
            return
        mob_id = self._game_kb.extract_mob_id(observation)
        play_ver = self.config.minecraft_play_version or None
        db_text = self._game_kb.build_context(
            game_id,
            question,
            mob_id=mob_id,
            observation=observation,
            play_version=play_ver,
        )
        lang = self._reply_lang(lang_question if lang_question is not None else question)
        parts.append("")
        parts.append(game_database_header(lang))
        parts.append(db_text)
        parts.append("")
        parts.append(self._game_kb.synthesize_prompt_rules(
            game_id, question, lang=lang, advisory_mode=advisory_mode,
        ))

    def _answer_text_only(
        self,
        question: str,
        intent: QueryIntent,
        on_status: StatusCallback | None,
        on_token: TokenCallback | None,
        screen_context: ScreenContext | None = None,
        *,
        lang_question: str | None = None,
        advisory_mode: str = "none",
        active_game: str | None = None,
        conversation_context: str = "",
    ) -> str:
        parts: list[str] = []
        if conversation_context:
            parts.append(conversation_context)
            parts.append("")
        parts.append(f"Question: {question}")
        if intent.hint:
            parts.append(f"Intent: {intent.hint}")
        game_id = active_game or self._resolve_game_id(question, screen_context)
        mechanics_hint = infer_mechanics_game(question, None)
        if (
            not game_id
            and mechanics_hint != "noita"
            and re.search(r"\bxp\b|\bexperience\b|\bопыт\b", question.lower())
        ):
            game_id = "minecraft"
        mc_question = game_id == "minecraft" or (
            mechanics_hint != "noita" and is_minecraft_question(question)
        )
        oni_q = game_id == "oni" or is_oni_question(question)
        advisory = is_advisory_question(question)
        direct_recipe_acquisition = bool(
            self.config.use_game_database
            and game_id
            and self._game_kb.has_direct_recipe_match(game_id, question)
        )
        mode = advisory_mode
        if direct_recipe_acquisition and mode == "none":
            mode = "factual"
        elif mode == "none" and advisory:
            mode = "brief"
        lang_q = lang_question if lang_question is not None else question
        if (
            (intent.needs_web or advisory)
            and not direct_recipe_acquisition
            and mode != "expand"
            and self.config.web_search_enabled
        ):
            self._status(on_status, "Searching the web…")
            search = web_search(
                build_search_query(
                    lang_q,
                    minecraft_context=mc_question or game_id == "minecraft",
                    oni_context=oni_q,
                ),
                self.config.web_search_max_results,
            )
            if search:
                parts.append("Web search:")
                parts.append(search)
        if self.config.use_game_database and game_id:
            self._append_game_database(
                parts, game_id, question,
                advisory_mode=mode, lang_question=lang_q,
            )
            acquisition_rule = self._game_kb.acquisition_prompt_rule(game_id, question)
            if acquisition_rule:
                parts.append("")
                parts.append(acquisition_rule)
        if not self.config.use_game_database or not game_id:
            md = self._md_rule(lang_q)
            parts.append(
                f"{md} If the question requires explanation, give a full, "
                "structured answer with examples and practical steps."
            )
        return self.ask_text(
            "\n\n".join(parts),
            on_status,
            on_token,
            screen_context=screen_context,
            minecraft_question=mc_question,
            oni_question=oni_q,
            active_game=game_id,
            source_question=lang_q,
            advisory_mode=mode,
        )

    def _status(self, on_status: StatusCallback | None, msg: str) -> None:
        if on_status:
            on_status(msg)

    def _should_skip_vision(self, ocr_text: str) -> bool:
        text = ocr_text.strip()
        if len(text) < self.config.skip_vision_if_ocr_chars:
            return False
        if text.startswith("[OCR"):
            return False
        words = re.findall(r"[a-zA-Zа-яА-ЯёЁ]{3,}", text)
        wiki_markers = ("wiki", "crafting", "recipe", "крафт", "рецепт", "http", "www", "minecraft.fandom")
        has_wiki_marker = any(m in text.lower() for m in wiki_markers)
        return len(words) >= 40 and has_wiki_marker

    def ask_with_image(
        self,
        user_message: str,
        image_path: Path,
        ocr_text: str = "",
        on_status: StatusCallback | None = None,
        on_token: TokenCallback | None = None,
        fast: bool | None = None,
    ) -> str:
        use_fast = self.config.fast_mode if fast is None else fast

        if use_fast and self.config.use_vision and self.resolve_vision_model():
            intent = self.plan_query(user_message, in_game=True, on_status=on_status)
            return self.execute_query(user_message, image_path, intent, on_status, on_token)

        return self._ask_full(user_message, image_path, ocr_text, on_status, on_token)

    def _ask_vision_answer(
        self,
        user_message: str,
        image_path: Path,
        intent: QueryIntent,
        on_status: StatusCallback | None,
        on_token: TokenCallback | None,
        screen_context: ScreenContext | None = None,
        lang_question: str | None = None,
        advisory_mode: str = "none",
        conversation_context: str = "",
    ) -> str:
        ctx = screen_context or ScreenContext()
        lang_q = lang_question if lang_question is not None else user_message
        mode = advisory_mode
        self._status(on_status, "Looking at screen…")
        observation = ""
        ocr_text = ""
        search_text = ""
        play_recommendation = self._is_play_recommendation_question(user_message)

        with ThreadPoolExecutor(max_workers=3) as pool:
            vision_f = pool.submit(
                self._vision_describe_screen, image_path, user_message, intent, ctx,
            )
            futures = {vision_f: "vision"}
            if not play_recommendation:
                ocr_f = pool.submit(
                    self._run_ocr, image_path, "",
                )
                futures[ocr_f] = "ocr"
            for future in as_completed(futures):
                kind = futures[future]
                try:
                    result = future.result(timeout=self.config.vision_timeout_sec)
                    if kind == "vision":
                        observation = result
                    else:
                        ocr_text = result
                except Exception:
                    pass

        if not observation.strip():
            raise RuntimeError("Vision could not describe the screen")

        if self._should_search_for_screen_answer(user_message, observation, intent, ctx):
            self._status(on_status, "Searching the web…")
            search_q = build_screen_search_query(user_message, observation, ocr_text)
            try:
                search_text = web_search(search_q, self.config.web_search_max_results)
            except Exception:
                search_text = ""

        self._status(on_status, "Composing answer…")
        parts: list[str] = []
        if conversation_context:
            parts.append(conversation_context)
            parts.append("")
        parts.append(f"Question: {user_message}")
        parts.append("Screenshot description from vision:")
        parts.append(observation[:2000])
        if ocr_text and not ocr_text.startswith("[OCR") and not self._is_noisy_ocr(ocr_text):
            parts.append("Visible text from OCR:")
            parts.append(ocr_text[:1500])
        if search_text:
            parts.append("Web search results (use for names, characters, and apps):")
            parts.append(search_text)
        if play_recommendation:
            parts.append(
                "The user is asking what to play. If the screenshot shows Steam, a launcher, "
                "or a game library, recommend from the visible games only. Do not give generic "
                "web recommendations or mention games that are not visible unless the user asks "
                "for outside suggestions. Pick 1-3 options with short reasons. Keep the answer concise: "
                "one best pick first, then up to two alternatives."
            )
        if self._looks_like_spike_context(observation, search_text):
            parts.append(
                "Recognition hint: if the Cowboy Bebop wallpaper shows a slim man with "
                "dark tousled hair, a cigarette, and a suit, it is very likely Spike Spiegel. "
                "You may identify him confidently."
            )
        if ctx.foreground_title:
            parts.append(f"Active Windows foreground title: {ctx.foreground_title}")
        if ctx.oni_window:
            parts.append("Oxygen Not Included is open, so ONI game advice is allowed.")
        elif ctx.minecraft_window:
            parts.append("Minecraft is open, so game advice is allowed.")
        else:
            parts.append(
                "This is NOT a supported game window. Do not mention Minecraft, Oxygen Not Included, "
                "mobs, blocks, crafting, duplicants, or game mechanics unless clear gameplay UI is visible. "
                "If you see a browser, YouTube, Twitch, or a video player, the user is watching media — "
                "do NOT assume they are playing the game on screen. Answer the question only for the game "
                "they named, or ask which game they mean. "
                "Do not invent XP/level/quest systems — verify mechanics from search. "
                "Noita has NO traditional XP or levels; progression is spells, perks, and Orbs of True Knowledge. "
                "Do not list taskbar icons, the system clock, or apps from the taskbar unless "
                "the user explicitly asks about them. A taskbar icon does not mean an app is open "
                "or installed. If the wallpaper shows an anime/art character, identify the character "
                "from vision/OCR/search when possible; otherwise say 'looks like...' and describe "
                "hair, clothing, pose, and art style. Do not quote OCR fragments that look random."
            )
        if mode == "brief" and not ctx.active_game:
            parts.append(
                "Brief advisory mode: only give ---options--- for games you know well from search. "
                "If the visible game is unsupported or uncertain, say so and ask which game the user means "
                "instead of inventing mechanics."
            )
        if play_recommendation:
            md = self._md_rule(lang_q)
            parts.append(
                f"{md} Keep it short: 3-6 bullets max. "
                "Start with 'Best pick:' and choose one visible game. Then add up to two alternatives. "
                "Do not summarize every visible game."
            )
        else:
            md = self._md_rule(lang_q)
            parts.append(
                f"{md} Give a complete answer to the user's question, "
                "but do not over-extend simple screen descriptions. Use vision, OCR, and search; "
                "do not invent games or open windows. If you are unsure about a character name, say 'looks like...'."
            )
        answer = self.ask_text(
            "\n\n".join(parts),
            on_status,
            on_token,
            screen_context=ctx,
            source_question=lang_q,
            advisory_mode=mode,
        )
        if not ctx.active_game:
            return self._sanitize_non_minecraft_answer(answer)
        return answer

    def _vision_describe_screen(
        self,
        image_path: Path,
        user_message: str,
        intent: QueryIntent,
        screen_context: ScreenContext | None = None,
    ) -> str:
        ctx = screen_context or ScreenContext()
        focus = {
            "crosshair": "Focus on the center of the image.",
            "hud": "Focus on visible UI or HUD elements, if any.",
            "scene": "Describe the overall scene.",
            "none": "",
        }.get(intent.focus, "")
        game_note = (
            "This appears to be Oxygen Not Included gameplay."
            if ctx.oni_window
            else (
                "This appears to be Minecraft gameplay."
                if ctx.minecraft_window
                else (
                    "This is likely NOT a supported game — desktop, wallpaper, browser, YouTube/video, or app window. "
                    "If a game appears inside a browser or video player, describe it as media on screen, "
                    "NOT as the game the user is actively playing. "
                    "Anime/cartoon wallpaper art is NOT Minecraft — do NOT call it a "
                    "'Minecraft character' unless blocky voxel game UI is clearly visible."
                )
            )
        )
        if self._is_play_recommendation_question(user_message):
            prompt = (
                "Look at this screenshot of a game launcher/library, likely Steam.\n"
                f"User question: {user_message}\n"
                "Return a compact English observation for choosing what to play:\n"
                "- Name the app/library if visible\n"
                "- List only clearly readable visible game titles, especially highlighted or central ones\n"
                "- Do not describe banners, taskbar, wallpaper, or unrelated UI\n"
                "- Do not recommend yet; only provide the visible titles and any obvious genre cues\n"
            )
            model = self.resolve_vision_model()
            if not model:
                return ""
            return self._vision_chat(model, image_path, prompt, max_tokens=160, on_token=None).strip()

        prompt = (
            "Look at this screenshot.\n"
            f"{focus}\n"
            f"Context: {game_note}\n"
            f"User question: {user_message}\n"
            "Describe what you see in plain English (4-8 sentences):\n"
            "- Wallpaper/background art: style (anime, photo, abstract), colors\n"
            "- Any characters: hair color, clothing, pose, cigarette/props, art style\n"
            "- Desktop icons, windows, browser — only if clearly visible as main content\n"
            "- If this is Steam or another game library/store page: read visible game titles, "
            "sections, highlighted cards, and selected/hovered items carefully\n"
            "- Taskbar: mention only at a high level; do NOT list app icons unless the "
            "user explicitly asks about the taskbar. Do NOT claim an app is open or "
            "installed from a taskbar icon alone\n"
            "- Any readable text or logos\n"
            "Do NOT mention Minecraft, mobs, or blocks unless blocky voxel gameplay UI "
            "is clearly on screen. "
            "Do NOT say 'text interface' unless it is literally a text-only document."
        )
        model = self.resolve_vision_model()
        if not model:
            return ""
        text = self._vision_chat(model, image_path, prompt, max_tokens=260, on_token=None)
        if self._is_weak_vision_text(text):
            retry = (
                "Describe this image for someone who cannot see it. "
                "Include: wallpaper/background art, any characters (hair, outfit, pose, "
                "smoking/cigarette if any), and main desktop UI. If this is Steam or a game "
                "library, read visible game titles and sections carefully. Do not list taskbar icons. "
                "Anime/cartoon art on wallpaper is NOT Minecraft. "
                "Do not claim apps are open from taskbar icons alone."
            )
            text = self._vision_chat(model, image_path, retry, max_tokens=220, on_token=None)
        return text.strip()

    @staticmethod
    def _sanitize_non_minecraft_answer(text: str) -> str:
        """Remove obvious false Minecraft/Epic claims when not in MC context."""
        if not text or not text.strip():
            return text
        result = text
        result = re.sub(
            r"(?i)\bminecraft\s+(character|персонаж|figure|skin)\b",
            "anime/cartoon character on wallpaper",
            result,
        )
        result = re.sub(
            r"(?i)\b(персонаж|character)\s+(из\s+)?minecraft\b",
            "персонаж на обоях",
            result,
        )
        result = re.sub(
            r"(?i)\b(minecraft|майнкрафт)\b",
            "",
            result,
        )
        sentences = re.split(r"(?<=[.!?…])\s+", result)
        kept: list[str] = []
        for sentence in sentences:
            s = sentence.strip()
            if not s:
                continue
            lower = s.lower()
            if re.search(r"(?i)(epic games|launcher epic|лаунчер epic)", lower):
                if re.search(
                    r"(?i)(taskbar|панел|иконк|icon|значок|ярлык|установ|installed|open|открыт|запущен|running|active)",
                    lower,
                ):
                    continue
            if re.search(r"(?i)\b(ocr|ошибк[а-я]* распознаван|мусорн[а-я]* символ)\b", lower):
                continue
            if re.search(r"(?i)\b(моб|mob|creeper|крипер|zombie|зомби)\b", lower):
                if not re.search(r"(?i)(gameplay|игров|minecraft|майнкрафт)", lower):
                    s = re.sub(
                        r"(?i)\b(моб|mob|creeper|крипер|zombie|зомби)\w*\b",
                        "персонаж",
                        s,
                    )
            kept.append(s)
        cleaned = " ".join(kept).strip()
        cleaned = re.sub(r"\s{2,}", " ", cleaned)
        cleaned = re.sub(r"\(\s*\)", "", cleaned)
        return cleaned or text.strip()

    @staticmethod
    def _is_play_recommendation_question(question: str) -> bool:
        q = (question or "").lower()
        markers = (
            "какую игру",
            "во что поиграть",
            "что поиграть",
            "what should i play",
            "which game",
            "what game should",
            "choose a game",
            "pick a game",
            "recommend a game",
        )
        return any(marker in q for marker in markers)

    def _should_search_for_screen_answer(
        self,
        user_message: str,
        observation: str,
        intent: QueryIntent,
        ctx: ScreenContext,
    ) -> bool:
        if not self.config.web_search_enabled or ctx.active_game:
            return False
        if self._is_play_recommendation_question(user_message):
            return False
        if intent.needs_web:
            return True
        combined = f"{user_message} {observation}".lower()
        identity_markers = (
            "who is",
            "who's",
            "кто это",
            "identify",
            "name this",
            "what character",
            "какой персонаж",
            "anime",
            "аниме",
            "cowboy bebop",
            "wallpaper",
            "обои",
        )
        return any(marker in combined for marker in identity_markers)

    @staticmethod
    def _is_noisy_ocr(text: str) -> bool:
        cleaned = re.sub(r"\s+", " ", text or "").strip()
        if len(cleaned) < 8:
            return True
        words = re.findall(r"[A-Za-zА-Яа-яЁё]{3,}", cleaned)
        weird = re.findall(r"[^\w\s.,:;!?()\-\[\]А-Яа-яЁёA-Za-z0-9]", cleaned)
        quoted_fragments = re.findall(r'"[^"]{3,40}"|«[^»]{3,40}»', cleaned)
        if len(words) < 3 and len(cleaned) < 80:
            return True
        return len(weird) > max(8, len(cleaned) // 5) or len(quoted_fragments) >= 3

    @staticmethod
    def _looks_like_spike_context(vision_text: str, search_text: str) -> bool:
        combined = f"{vision_text} {search_text}".lower()
        has_bebop = any(
            marker in combined
            for marker in ("cowboy bebop", "ковбой бибоп", "spike spiegel", "спайк шпигель")
        )
        has_character_cue = any(
            marker in combined
            for marker in ("cigarette", "smoking", "сигар", "курит", "tousled hair", "взъерош")
        )
        return has_bebop and has_character_cue

    @staticmethod
    def _is_weak_vision_text(text: str) -> bool:
        cleaned = text.strip()
        if len(cleaned) < 24:
            return True
        lower = cleaned.lower()
        echo_markers = (
            "явно видно",
            "опиши только",
            "describe only",
            "plain english",
            "do not invent",
        )
        return any(m in lower for m in echo_markers) and len(cleaned) < 100

    def _ask_vision_then_text(
        self,
        user_message: str,
        image_path: Path,
        intent: QueryIntent,
        on_status: StatusCallback | None,
        on_token: TokenCallback | None,
        screen_context: ScreenContext | None = None,
        lang_question: str | None = None,
        advisory_mode: str = "none",
        conversation_context: str = "",
    ) -> str:
        ctx = screen_context or ScreenContext()
        lang_q = lang_question if lang_question is not None else user_message
        mode = advisory_mode
        if mode == "none" and is_advisory_question(lang_q):
            mode = "brief"
        if not ctx.active_game:
            return self._ask_vision_answer(
                user_message, image_path, intent, on_status, on_token, ctx,
                lang_question=lang_q, advisory_mode=mode,
                conversation_context=conversation_context,
            )

        game_id = ctx.active_game or self.config.default_game_id
        self._status(on_status, f"{game_id} + screen…")
        search_text = ""
        observation = ""
        needs_web = intent.needs_web or (
            is_advisory_question(lang_q)
            and mode != "expand"
            and self.config.web_search_enabled
        )

        if needs_web and self.config.web_search_enabled:
            with ThreadPoolExecutor(max_workers=2) as pool:
                vision_f = pool.submit(self._vision_observe, image_path, intent, user_message, ctx)
                search_f = pool.submit(
                    web_search,
                    build_search_query(
                        lang_q,
                        oni_context=game_id == "oni",
                    ),
                    self.config.web_search_max_results,
                )
                try:
                    observation = vision_f.result(timeout=self.config.vision_timeout_sec)
                except Exception:
                    observation = ""
                try:
                    search_text = search_f.result(timeout=10)
                except Exception:
                    search_text = ""
        else:
            try:
                observation = self._vision_observe(image_path, intent, user_message, ctx)
            except Exception:
                observation = ""

        self._status(on_status, "Game database…")
        parts: list[str] = []
        if conversation_context:
            parts.append(conversation_context)
            parts.append("")
        parts.append(f"Player question: {user_message}")
        if intent.hint:
            parts.append(f"Intent: {intent.hint}")
        game = self._game_kb.get_game(game_id)
        parts.append(f"Detected game: {game.name}")
        if observation:
            parts.append("Vision (context only, not a drop source):")
            parts.append(observation[:2000])
        if search_text:
            parts.append("Web search:")
            parts.append(search_text)
        self._append_game_database(
            parts, game_id, user_message, observation,
            advisory_mode=mode, lang_question=lang_q,
        )
        if not self.config.use_game_database:
            if is_mob_or_drop_question(user_message):
                parts.append("This is a mob/drop question. Use vanilla Minecraft only.")
            parts.append(
                f"{self._md_rule(lang_q)} Answer the exact question; "
                "do not describe the HUD unless the player asks about it."
            )
        stream_cb = on_token if self.config.streaming else None
        return self.ask_text(
            "\n\n".join(parts),
            on_status,
            stream_cb,
            screen_context=ctx,
            minecraft_question=game_id == "minecraft",
            oni_question=game_id == "oni",
            active_game=game_id,
            source_question=lang_q,
            advisory_mode=mode,
        )

    def _vision_observe(
        self,
        image_path: Path,
        intent: QueryIntent,
        user_message: str = "",
        screen_context: ScreenContext | None = None,
    ) -> str:
        ctx = screen_context or ScreenContext()
        model = self.resolve_vision_model()
        if not model:
            return ""
        if ctx.minecraft_window and (
            intent.focus == "crosshair" or is_mob_or_drop_question(user_message)
        ):
            return self._vision_identify_mob(image_path)
        focus = FOCUS_VISION_PROMPTS.get(intent.focus, FOCUS_VISION_PROMPTS["none"])
        prompt = f"Minecraft gameplay screenshot.\n{focus}\nBe concise."
        return self._vision_chat(model, image_path, prompt, max_tokens=180, on_token=None)

    def _vision_identify_mob(self, image_path: Path) -> str:
        model = self.resolve_vision_model()
        if not model:
            return ""
        raw = self._vision_chat(
            model, image_path, MOB_IDENTIFY_PROMPT, max_tokens=80, on_token=None,
        )
        return normalize_mob_observation(raw)

    def _ask_full(
        self,
        user_message: str,
        image_path: Path,
        ocr_text: str,
        on_status: StatusCallback | None,
        on_token: TokenCallback | None = None,
    ) -> str:
        self._status(on_status, "OCR…")
        final_ocr = self._run_ocr(image_path, ocr_text)
        vision_desc = ""
        search_text = ""

        vision_model = self.resolve_vision_model()
        use_vision = self.config.use_vision and vision_model and not self._should_skip_vision(final_ocr)
        intent = self.plan_query(user_message, in_game=True, on_status=on_status)
        do_search = self.config.web_search_enabled and intent.needs_web

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {}
            if use_vision:
                self._status(on_status, "Vision + OCR…")
                futures[pool.submit(self._describe_image, image_path, user_message)] = "vision"
            if do_search:
                self._status(on_status, "Поиск в интернете…")
                futures[pool.submit(self._run_search, user_message, final_ocr)] = "search"

            for future in as_completed(futures):
                kind = futures[future]
                try:
                    result = future.result(timeout=self.config.vision_timeout_sec)
                    if kind == "vision":
                        vision_desc = result
                    else:
                        search_text = result
                except Exception:
                    if kind == "vision":
                        vision_desc = ""
                    else:
                        search_text = ""

        if use_vision and not vision_desc.strip():
            try:
                vision_desc = self._vision_observe(image_path, intent, user_message)
            except Exception as exc:
                vision_desc = f"[Vision failed: {exc}]"

        if self.config.use_two_stage:
            self._status(on_status, "Composing answer…")
            return self._synthesize_answer(
                user_message, vision_desc, final_ocr, search_text, on_status, on_token,
            )

        if vision_desc:
            return vision_desc
        return self.ask_text(
            self._build_context_prompt(user_message, "", final_ocr, search_text),
            on_status,
            on_token,
            source_question=user_message,
        )

    def _run_search(self, user_message: str, ocr_text: str) -> str:
        query = build_search_query(user_message, ocr_text)
        return web_search(query, self.config.web_search_max_results)

    def _run_ocr(self, image_path: Path, existing: str) -> str:
        if existing:
            return existing
        return extract_text(
            image_path,
            self.config.ocr_lang,
            self.config.tesseract_cmd,
            self.config.ocr_max_chars,
        )

    @staticmethod
    def _encode_image_b64(image_path: Path, max_width: int = 1280) -> str:
        from PIL import Image

        with Image.open(image_path) as img:
            if img.width > max_width:
                ratio = max_width / img.width
                img = img.resize((max_width, max(1, int(img.height * ratio))), Image.Resampling.LANCZOS)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return base64.b64encode(buf.getvalue()).decode("ascii")

    def _describe_image(self, image_path: Path, user_message: str = "") -> str:
        model = self.resolve_vision_model()
        if not model:
            return ""
        prompt = self.config.vision_describe_prompt
        if user_message:
            prompt = f"{prompt}\n\nUser question: {user_message}"
        return self._vision_chat(model, image_path, prompt)

    def _vision_chat(
        self,
        model: str,
        image_path: Path,
        prompt: str,
        max_tokens: int | None = None,
        on_token: TokenCallback | None = None,
    ) -> str:
        image_b64 = self._encode_image_b64(image_path)
        messages = [{"role": "user", "content": prompt, "images": [image_b64]}]
        if on_token:
            return self._stream_chat(
                model,
                messages,
                on_token,
                max_tokens=max_tokens or self.config.vision_max_tokens,
                timeout=self.config.vision_timeout_sec,
            )
        payload = self._with_think_flag({
            "model": model,
            "messages": messages,
            "stream": False,
            "keep_alive": self.config.ollama_keep_alive,
            "options": {
                "num_predict": max_tokens or self.config.vision_max_tokens,
                "temperature": 0.3,
            },
        }, model)
        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=self.config.vision_timeout_sec,
        )
        response.raise_for_status()
        data = response.json()
        content = self._message_text(data.get("message", {}))
        if not content:
            raise RuntimeError("Vision model returned an empty response")
        return content

    def _synthesize_answer(
        self,
        user_message: str,
        vision_desc: str,
        ocr_text: str,
        search_text: str,
        on_status: StatusCallback | None = None,
        on_token: TokenCallback | None = None,
    ) -> str:
        prompt = self._build_context_prompt(user_message, vision_desc, ocr_text, search_text)
        system = self._resolve_system_prompt(user_message=user_message)
        if self.config.streaming and on_token:
            self._status(on_status, "Text model thinking…")
            return self._stream_chat(
                self.resolve_text_model(),
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt + " /no_think"},
                ],
                on_token,
                max_tokens=self.config.max_tokens,
                timeout=self.config.text_timeout_sec,
            )
        return self._chat(self.resolve_text_model(), prompt, on_status=on_status)

    def _build_context_prompt(
        self,
        user_message: str,
        vision_desc: str,
        ocr_text: str,
        search_text: str,
    ) -> str:
        parts = [f"Question: {user_message}"]
        if vision_desc:
            parts.append("Screen from vision:")
            parts.append(vision_desc[:2000])
        if ocr_text and not ocr_text.startswith("[OCR") and not self._is_noisy_ocr(ocr_text):
            parts.append("Visible text from OCR:")
            parts.append(ocr_text[:2500])
        if search_text:
            parts.append("Web search:")
            parts.append(search_text)
        if self._looks_like_spike_context(vision_desc, search_text):
            parts.append(
                "Recognition hint: Cowboy Bebop plus a slim smoking character with dark "
                "tousled hair usually means Spike Spiegel."
            )
        parts.append(
            f"{self._md_rule(user_message)} Answer the user's exact question. "
            "If the task is complex, explain fully, with structure and concrete steps. "
            "Do not list taskbar icons, the system clock, or noisy OCR unless they matter to the question."
        )
        return "\n\n".join(parts)

    def _stream_chat(
        self,
        model: str,
        messages: list[dict],
        on_token: TokenCallback,
        max_tokens: int,
        timeout: int,
    ) -> str:
        payload = self._with_think_flag({
            "model": model,
            "messages": messages,
            "stream": True,
            "keep_alive": self.config.ollama_keep_alive,
            "options": {
                "num_predict": max_tokens,
                "temperature": 0.4,
            },
        }, model)
        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=timeout,
            stream=True,
        )
        response.raise_for_status()
        parts: list[str] = []
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            try:
                data = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            chunk = data.get("message", {}).get("content", "")
            if chunk:
                parts.append(chunk)
                on_token(chunk)
            if data.get("done"):
                break
        full = self._strip_thinking("".join(parts).strip())
        if not full:
            raise RuntimeError("Model returned an empty response")
        return full

    def _chat(
        self,
        model: str,
        user_message: str,
        on_status: StatusCallback | None = None,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        timeout: int | None = None,
    ) -> str:
        if on_status and system != ROUTER_SYSTEM:
            self._status(on_status, "Text model thinking…")
        payload = self._with_think_flag({
            "model": model,
            "messages": [
                {"role": "system", "content": system or self.config.system_prompt},
                {"role": "user", "content": user_message + (" /no_think" if system != ROUTER_SYSTEM else "")},
            ],
            "stream": False,
            "keep_alive": self.config.ollama_keep_alive,
            "options": {
                "num_predict": max_tokens or self.config.max_tokens,
                "temperature": 0.2 if system == ROUTER_SYSTEM else 0.5,
            },
        }, model)
        response = requests.post(
            f"{self.base_url}/api/chat",
            json=payload,
            timeout=timeout or self.config.text_timeout_sec,
        )
        response.raise_for_status()
        data = response.json()
        content = self._message_text(data.get("message", {}))
        if content:
            return content
        legacy = self._strip_thinking((data.get("response") or "").strip())
        if legacy:
            return legacy
        raise RuntimeError("Model returned an empty response")

    @staticmethod
    def _strip_thinking(text: str) -> str:
        tag = "think"
        pattern = re.compile(rf"<\/?{tag}[^>]*>", re.IGNORECASE)
        parts = pattern.split(text)
        if len(parts) > 1:
            return parts[-1].strip()
        return text.strip()

    def transcribe(self, audio_path: Path) -> str:
        if not self.has_model(self.config.stt_model):
            raise RuntimeError(f"Model {self.config.stt_model} is not installed")

        with audio_path.open("rb") as audio_file:
            response = requests.post(
                f"{self.base_url}/api/transcribe",
                files={"file": (audio_path.name, audio_file, "audio/wav")},
                data={"model": self.config.stt_model},
                timeout=120,
            )
        if response.status_code >= 400:
            raise RuntimeError(f"Ollama transcribe error: {response.text[:300]}")

        data = response.json()
        if isinstance(data, dict):
            return (data.get("text") or data.get("response") or "").strip()
        return str(data).strip()

    def status_summary(self) -> str:
        text = self.resolve_text_model()
        vision = self.resolve_vision_model()
        mode = f"streaming | {MODEL_PROFILE}"
        db = " | game DB" if self.config.use_game_database else ""
        return f"Text: {text} | Vision: {vision or 'none'} | {mode}{db} | universal"
