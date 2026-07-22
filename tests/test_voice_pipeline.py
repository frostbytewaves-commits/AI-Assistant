"""Voice pipeline coordinates STT -> Orchestrator -> optional TTS without UI."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from assistant.core import (
    PushToTalkActivation,
    TurnResult,
    VoicePipelineState,
    VoiceTurnCoordinator,
)
from assistant.intent import QueryIntent
from assistant.screen_context import ScreenContext


class FakeVoice:
    def __init__(self, audio_path: Path, *, text: str = "hello") -> None:
        self.audio_path = audio_path
        self.text = text
        self.started = 0
        self.stopped = 0
        self.cancelled = 0
        self.spoken: list[str] = []
        self.fail_transcribe = False
        self.fail_speak = False

    def start_recording(self) -> None:
        self.started += 1

    def stop_recording(self) -> Path:
        self.stopped += 1
        return self.audio_path

    def cancel_recording(self) -> None:
        self.cancelled += 1

    def transcribe(self, _audio_path: Path) -> str:
        if self.fail_transcribe:
            raise RuntimeError("stt failed")
        return self.text

    def speak(self, text: str) -> None:
        if self.fail_speak:
            raise RuntimeError("tts failed")
        self.spoken.append(text)


class FakeOrchestrator:
    def __init__(self, *, call_capture: bool = False) -> None:
        self.call_capture = call_capture
        self.calls: list[dict] = []

    def handle_turn(self, question: str, **kwargs) -> TurnResult:
        self.calls.append({"question": question, **kwargs})
        image_path = kwargs.get("image_path")
        screen_context = kwargs.get("screen_context") or ScreenContext()
        if self.call_capture:
            capture = kwargs["capture_screen"]
            image_path, screen_context = capture()
        return TurnResult(
            answer=f"answer: {question}",
            intent=QueryIntent.fallback_text(question),
            image_path=image_path,
            screen_context=screen_context,
        )


def _coordinator(tmp_path: Path, *, speak_answers: bool = True, text: str = "hello"):
    states: list[VoicePipelineState] = []
    voice = FakeVoice(tmp_path / "voice.wav", text=text)
    orchestrator = FakeOrchestrator()
    coordinator = VoiceTurnCoordinator(
        config=SimpleNamespace(speak_answers=speak_answers),  # type: ignore[arg-type]
        voice=voice,
        orchestrator=orchestrator,  # type: ignore[arg-type]
        on_state=states.append,
    )
    return coordinator, voice, orchestrator, states


def test_voice_turn_happy_path_calls_orchestrator(tmp_path: Path) -> None:
    coordinator, voice, orchestrator, states = _coordinator(tmp_path, text="what is open")

    coordinator.start_recording()
    result = coordinator.complete_recording(chat_history=[("User", "before")])

    assert result.question == "what is open"
    assert result.answer == "answer: what is open"
    assert voice.started == 1
    assert voice.stopped == 1
    assert orchestrator.calls[0]["question"] == "what is open"
    assert orchestrator.calls[0]["chat_history"] == [("User", "before")]
    assert states == [
        VoicePipelineState.LISTENING,
        VoicePipelineState.TRANSCRIBING,
        VoicePipelineState.THINKING,
        VoicePipelineState.IDLE,
    ]


def test_voice_turn_uses_capture_callback_when_orchestrator_needs_it(tmp_path: Path) -> None:
    states: list[VoicePipelineState] = []
    voice = FakeVoice(tmp_path / "voice.wav", text="what is on screen")
    orchestrator = FakeOrchestrator(call_capture=True)
    coordinator = VoiceTurnCoordinator(
        config=SimpleNamespace(speak_answers=True),  # type: ignore[arg-type]
        voice=voice,
        orchestrator=orchestrator,  # type: ignore[arg-type]
        on_state=states.append,
    )
    screenshot = tmp_path / "screen.png"
    screenshot.write_bytes(b"x")

    coordinator.start_recording()
    result = coordinator.complete_recording(
        capture_screen=lambda: (screenshot, ScreenContext(foreground_title="Game")),
    )

    assert result.image_path == screenshot
    assert result.screen_context is not None
    assert result.screen_context.foreground_title == "Game"


def test_voice_turn_transcription_error_resets_state(tmp_path: Path) -> None:
    coordinator, voice, _orchestrator, states = _coordinator(tmp_path)
    voice.fail_transcribe = True

    coordinator.start_recording()
    with pytest.raises(RuntimeError, match="stt failed"):
        coordinator.complete_recording()

    assert coordinator.state == VoicePipelineState.IDLE
    assert states[-2:] == [VoicePipelineState.ERROR, VoicePipelineState.IDLE]


def test_cancel_recording_stops_voice_and_resets_state(tmp_path: Path) -> None:
    coordinator, voice, _orchestrator, states = _coordinator(tmp_path)

    coordinator.start_recording()
    coordinator.cancel_recording()

    assert voice.cancelled == 1
    assert coordinator.state == VoicePipelineState.IDLE
    assert states[-1] == VoicePipelineState.IDLE


def test_speak_answer_honors_disabled_tts(tmp_path: Path) -> None:
    coordinator, voice, _orchestrator, _states = _coordinator(tmp_path, speak_answers=False)

    assert coordinator.speak_answer("hello") is False
    assert voice.spoken == []


def test_speak_answer_tts_failure_returns_false_and_resets_state(tmp_path: Path) -> None:
    coordinator, voice, _orchestrator, states = _coordinator(tmp_path)
    voice.fail_speak = True

    assert coordinator.speak_answer("hello") is False
    assert coordinator.state == VoicePipelineState.IDLE
    assert states[-2:] == [VoicePipelineState.ERROR, VoicePipelineState.IDLE]


def test_speak_answer_reports_ready_after_speech(tmp_path: Path) -> None:
    coordinator, voice, _orchestrator, _states = _coordinator(tmp_path)
    statuses: list[str] = []

    assert coordinator.speak_answer("hello", on_status=statuses.append) is True
    assert voice.spoken == ["hello"]
    assert statuses == ["Speaking...", "Ready"]


def test_push_to_talk_activation_delegates_start_and_stop() -> None:
    calls: list[str] = []
    activation = PushToTalkActivation(
        on_start=lambda: calls.append("start"),
        on_stop=lambda: calls.append("stop"),
    )

    activation.start()
    activation.stop()

    assert calls == ["start", "stop"]
