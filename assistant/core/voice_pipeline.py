"""Voice turn coordinator: activation -> STT -> Orchestrator -> optional TTS.

This module owns the voice lifecycle without importing UI frameworks. The host
overlay supplies callbacks for status, streaming tokens, screenshots, and chat
history.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol

from ..config import AssistantConfig
from ..conversation import ChatTurn
from ..llm import StatusCallback, TokenCallback
from ..screen_context import ScreenContext
from .orchestrator import CaptureFn, Orchestrator


class VoicePipelineState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


class VoiceEngineLike(Protocol):
    def start_recording(self) -> None: ...

    def stop_recording(self) -> Path: ...

    def cancel_recording(self) -> None: ...

    def transcribe(self, audio_path: Path) -> str: ...

    def speak(self, text: str) -> None: ...


class VoiceActivationProvider(Protocol):
    """Activation strategy contract; F9 is current, wake-word can implement this later."""

    def start(self) -> None: ...

    def stop(self) -> None: ...


class PushToTalkActivation:
    """Simple push-to-talk activation used by the current F9 hotkey/button."""

    def __init__(self, on_start: Callable[[], None], on_stop: Callable[[], None]) -> None:
        self._on_start = on_start
        self._on_stop = on_stop

    def start(self) -> None:
        self._on_start()

    def stop(self) -> None:
        self._on_stop()


@dataclass(frozen=True)
class VoiceTurnResult:
    question: str
    answer: str
    audio_path: Path
    image_path: Path | None = None
    screen_context: ScreenContext | None = None


class VoiceTurnCoordinator:
    """UI-free coordinator for one voice turn.

    VoiceEngine keeps device/STT/TTS details. Orchestrator keeps reasoning/tools.
    This class only sequences those pieces and tracks a small lifecycle state.
    """

    def __init__(
        self,
        *,
        config: AssistantConfig,
        voice: VoiceEngineLike,
        orchestrator: Orchestrator,
        on_state: Callable[[VoicePipelineState], None] | None = None,
    ) -> None:
        self.config = config
        self.voice = voice
        self.orchestrator = orchestrator
        self._on_state = on_state
        self.state = VoicePipelineState.IDLE

    @property
    def is_listening(self) -> bool:
        return self.state == VoicePipelineState.LISTENING

    def _set_state(self, state: VoicePipelineState) -> None:
        self.state = state
        if self._on_state is not None:
            self._on_state(state)

    def start_recording(self) -> None:
        if self.state != VoicePipelineState.IDLE:
            raise RuntimeError(f"Voice pipeline is busy: {self.state.value}")
        self._set_state(VoicePipelineState.LISTENING)
        try:
            self.voice.start_recording()
        except Exception:
            self._set_state(VoicePipelineState.ERROR)
            self._set_state(VoicePipelineState.IDLE)
            raise

    def cancel_recording(self) -> None:
        try:
            self.voice.cancel_recording()
        finally:
            self._set_state(VoicePipelineState.IDLE)

    def complete_recording(
        self,
        *,
        image_path: Path | None = None,
        screen_context: ScreenContext | None = None,
        chat_history: list[ChatTurn] | None = None,
        excluded_hwnd: int | None = None,
        on_status: StatusCallback | None = None,
        on_token: TokenCallback | None = None,
        capture_screen: CaptureFn | None = None,
    ) -> VoiceTurnResult:
        if self.state != VoicePipelineState.LISTENING:
            raise RuntimeError("Voice pipeline is not recording")

        try:
            self._set_state(VoicePipelineState.TRANSCRIBING)
            if on_status is not None:
                on_status("Transcribing...")
            audio_path = self.voice.stop_recording()
            question = self.voice.transcribe(audio_path).strip()
            if not question:
                raise RuntimeError("Could not recognize speech")

            self._set_state(VoicePipelineState.THINKING)
            result = self.orchestrator.handle_turn(
                question,
                image_path=image_path,
                screen_context=screen_context,
                chat_history=chat_history or [],
                excluded_hwnd=excluded_hwnd,
                on_status=on_status,
                on_token=on_token,
                capture_screen=capture_screen,
            )
            return VoiceTurnResult(
                question=question,
                answer=result.answer,
                audio_path=audio_path,
                image_path=result.image_path,
                screen_context=result.screen_context,
            )
        except Exception:
            self._set_state(VoicePipelineState.ERROR)
            raise
        finally:
            self._set_state(VoicePipelineState.IDLE)

    def speak_answer(
        self,
        answer: str,
        *,
        on_status: StatusCallback | None = None,
    ) -> bool:
        if not self.config.speak_answers:
            return False
        text = (answer or "").strip()
        if not text:
            return False
        self._set_state(VoicePipelineState.SPEAKING)
        if on_status is not None:
            on_status("Speaking...")
        try:
            self.voice.speak(text)
            return True
        except Exception:
            self._set_state(VoicePipelineState.ERROR)
            return False
        finally:
            self._set_state(VoicePipelineState.IDLE)
            if on_status is not None:
                on_status("Ready")
