"""Thin Orchestrator — Sense/Context → Plan → Act/Answer (no UI, no NLP sprawl)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..config import AssistantConfig
from ..conversation import ChatTurn, format_chat_history
from ..intent import QueryIntent
from ..llm import OllamaClient, StatusCallback, TokenCallback
from ..memory import MemoryManager
from ..screen_context import ScreenContext
from .context import ContextManager

CaptureFn = Callable[[], tuple[Path, ScreenContext]]


@dataclass
class TurnResult:
    answer: str
    intent: QueryIntent
    screen_context: ScreenContext
    image_path: Path | None = None


class Orchestrator:
    """Glue only: assemble context, ask planner/LLM, return answer.

    Capture/UI stay in the host (overlay). Tools already run inside OllamaClient.execute_query.
    """

    def __init__(
        self,
        config: AssistantConfig,
        llm: OllamaClient,
        memory: MemoryManager,
        context_builder: ContextManager | None = None,
    ) -> None:
        self.config = config
        self.llm = llm
        self.memory = memory
        self.context_builder = context_builder or ContextManager(
            capabilities=[
                "web_search",
                "screen_capture",
                "voice",
                "launch_app",
                "focus_window",
                "close_window",
                "open_url",
                "media_play_pause",
                "volume_mute",
            ],
        )

    def build_conversation_context(
        self,
        chat_history: list[ChatTurn],
        *,
        excluded_hwnd: int | None = None,
    ) -> str:
        parts = [self.memory.format_context()]
        try:
            host = self.context_builder.build(excluded_hwnd=excluded_hwnd)
            block = host.to_prompt_block()
            if block:
                parts.append(block)
        except Exception:
            pass
        history = format_chat_history(chat_history)
        if history:
            parts.append(history)
        return "\n\n".join(parts)

    def resolve_screen_context(
        self,
        *,
        excluded_hwnd: int | None = None,
        screen_context: ScreenContext | None = None,
    ) -> ScreenContext:
        if screen_context is not None:
            return screen_context
        try:
            return self.context_builder.build(excluded_hwnd=excluded_hwnd).to_screen_context()
        except Exception:
            return ScreenContext.detect(excluded_hwnd)

    def handle_turn(
        self,
        question: str,
        *,
        image_path: Path | None = None,
        screen_context: ScreenContext | None = None,
        pre_intent: QueryIntent | None = None,
        lang_question: str | None = None,
        advisory_mode: str = "none",
        active_game: str | None = None,
        chat_history: list[ChatTurn] | None = None,
        excluded_hwnd: int | None = None,
        on_status: StatusCallback | None = None,
        on_token: TokenCallback | None = None,
        capture_screen: CaptureFn | None = None,
        attached_screen: bool = False,
    ) -> TurnResult:
        """One user turn: plan → optional capture → execute (tools or answer)."""
        ctx = self.resolve_screen_context(
            excluded_hwnd=excluded_hwnd,
            screen_context=screen_context,
        )

        if pre_intent is not None:
            intent = pre_intent
        elif attached_screen:
            intent = self.llm.plan_attached_screen_query(
                question, screen_context=ctx, on_status=on_status,
            )
        else:
            intent = self.llm.plan_query(
                question,
                force_screen=self.config.always_capture_screen,
                on_status=on_status,
                screen_context=ctx,
            )

        path = image_path
        if path is None and intent.needs_screen:
            if capture_screen is None:
                raise RuntimeError("A screenshot is required for this question")
            path, ctx = capture_screen()

        lang_q = lang_question if lang_question is not None else question
        conversation_context = self.build_conversation_context(
            chat_history or [],
            excluded_hwnd=excluded_hwnd,
        )
        resolved_game = active_game if active_game is not None else self.llm._resolve_game_id(lang_q, ctx)

        answer = self.llm.execute_query(
            question,
            path,
            intent,
            on_status=on_status,
            on_token=on_token,
            screen_context=ctx,
            lang_question=lang_q,
            advisory_mode=advisory_mode,
            active_game=resolved_game,
            conversation_context=conversation_context,
        )
        return TurnResult(
            answer=answer,
            intent=intent,
            screen_context=ctx,
            image_path=path,
        )
