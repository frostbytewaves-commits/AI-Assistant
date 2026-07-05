import asyncio
import logging
import re
import subprocess
import struct
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

from .config import AssistantConfig


def _subprocess_hidden() -> dict:
    if sys.platform != "win32":
        return {}
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = 0
    return {"creationflags": flags, "startupinfo": info}


def _suppress_hf_hub_noise() -> None:
    for name in ("huggingface_hub", "huggingface_hub.utils._http", "httpx"):
        logging.getLogger(name).setLevel(logging.ERROR)


# Типичные «галлюцинации» Whisper на тишине / шуме (не реальная речь).
WHISPER_HALLUCINATION_MARKERS = (
    "редактор субтитров",
    "корректор",
    "а.кулаков",
    "а.семкин",
    "семкин",
    "кулаков",
    "субтитр",
    "subtitles",
    "subtitle",
    "thanks for watching",
    "thank you for watching",
    "amara.org",
    "продолжение следует",
    "подписывайтесь",
    "subscribe",
    "copyright",
    "©",
)


class VoiceEngine:
    def __init__(self, config: AssistantConfig) -> None:
        self.config = config
        _suppress_hf_hub_noise()
        self._recording = False
        self._frames: list[bytes] = []
        self._stream = None
        self._sd = None
        self._whisper_model = None
        self._input_device: int | None = None
        self._record_rate: int = config.sample_rate
        self._frame_lock = threading.Lock()
        self._speak_lock = threading.Lock()
        self._playback_proc: subprocess.Popen | None = None
        self._pyttsx3_engine = None
        self._stop_speech = threading.Event()
        self._speech_generation = 0
        self._shutdown_speech = False

    def _import_sounddevice(self):
        if self._sd is None:
            import sounddevice as sd

            self._sd = sd
        return self._sd

    def _device_label(self, sd, index: int) -> str:
        info = sd.query_devices(index)
        label = str(info.get("name", f"device {index}"))
        return re.sub(r"\s+", " ", label).strip()

    @staticmethod
    def _is_usable_input_device(info: dict) -> bool:
        if info.get("max_input_channels", 0) <= 0:
            return False
        name = str(info.get("name", "")).lower()
        bad_markers = (
            "sound mapper",
            "primary sound capture",
            "stereo mix",
            "what u hear",
            "output",
            "speaker",
            "динамик",
        )
        return not any(marker in name for marker in bad_markers)

    @staticmethod
    def _input_device_score(info: dict, index: int, default_index: int | None) -> int:
        name = str(info.get("name", "")).lower()
        score = 0
        if default_index is not None and index == default_index:
            score += 15
        preferred_scores = {
            "airpods": 120,
            "headset": 90,
            "headphone": 80,
            "головной телефон": 80,
            "bluetooth": 60,
            "microphone": 35,
            "микрофон": 35,
            "mic": 20,
            "realtek": 5,
        }
        for marker, value in preferred_scores.items():
            if marker in name:
                score += value
        if "@system32" in name or "bthhfenum" in name:
            score -= 25
        if "hands-free" in name or "hands free" in name:
            score -= 10
        score += int(info.get("max_input_channels", 0))
        return score

    def _resolve_input_device(self, sd) -> int:
        if self._input_device is not None:
            return self._input_device

        cfg = self.config.input_device
        if isinstance(cfg, int) and cfg >= 0:
            info = sd.query_devices(cfg)
            if not self._is_usable_input_device(info):
                raise RuntimeError(f"Выбранное устройство не похоже на микрофон: {self._device_label(sd, cfg)}")
            self._input_device = cfg
            return cfg

        if isinstance(cfg, str) and cfg.strip():
            needle = cfg.strip().lower()
            for index, info in enumerate(sd.query_devices()):
                if not self._is_usable_input_device(info):
                    continue
                if needle in str(info.get("name", "")).lower():
                    self._input_device = index
                    return index
            raise RuntimeError(f"Микрофон не найден по имени: {cfg}")

        default_in: int | None = None
        default_fallback: int | None = None
        try:
            raw_default = sd.default.device[0]
            if raw_default is not None and int(raw_default) >= 0:
                default_in = int(raw_default)
                info = sd.query_devices(default_in)
                if info.get("max_input_channels", 0) > 0:
                    default_fallback = default_in
        except Exception:
            default_in = None

        candidates: list[tuple[int, int]] = []
        for index, info in enumerate(sd.query_devices()):
            if self._is_usable_input_device(info):
                score = self._input_device_score(info, index, default_in)
                candidates.append((score, index))
        if candidates:
            _, index = max(candidates, key=lambda item: (item[0], -item[1]))
            self._input_device = index
            try:
                summary = ", ".join(
                    f"[{idx}] {self._device_label(sd, idx)} score={score}"
                    for score, idx in sorted(candidates, key=lambda item: (item[0], -item[1]), reverse=True)[:5]
                )
                logging.getLogger(__name__).info("Microphone candidates: %s", summary)
            except Exception:
                pass
            return index
        if default_fallback is not None:
            self._input_device = default_fallback
            return default_fallback

        for index, info in enumerate(sd.query_devices()):
            if info.get("max_input_channels", 0) > 0:
                self._input_device = index
                return index

        raise RuntimeError(
            "Микрофон не найден. Открой Параметры Windows → Система → Звук → "
            "Ввод — выбери микрофон и проверь, что полоска уровня реагирует на голос."
        )

    def _open_input_stream(self, sd):
        device = self._resolve_input_device(sd)
        label = self._device_label(sd, device)
        rates = (self.config.sample_rate, 44100, 48000)
        last_err: Exception | None = None

        for rate in rates:
            try:
                stream = sd.InputStream(
                    device=device,
                    samplerate=rate,
                    channels=1,
                    dtype="int16",
                    callback=self._record_callback,
                )
                stream.start()
                self._record_rate = rate
                logging.getLogger(__name__).info(
                    "Microphone: [%s] %s @ %s Hz", device, label, rate
                )
                return stream
            except Exception as exc:
                last_err = exc

        raise RuntimeError(
            f"Не удалось открыть микрофон «{label}». "
            "Проверь, что он не занят другой программой (Discord, OBS). "
            f"({last_err})"
        ) from last_err

    def _record_callback(self, indata, frames, time_info, status) -> None:
        if status:
            logging.getLogger(__name__).warning("Audio status: %s", status)
        if self._recording:
            data = indata.copy().tobytes()
            with self._frame_lock:
                self._frames.append(data)

    def cancel_recording(self) -> None:
        self._recording = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._frame_lock:
            self._frames = []

    def start_recording(self) -> None:
        sd = self._import_sounddevice()
        self._frames = []
        self._recording = True
        self._stream = self._open_input_stream(sd)

    def stop_recording(self) -> Path:
        self._recording = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        self.config.ensure_dirs()
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        audio_path = self.config.audio_dir / f"voice-{timestamp}.wav"

        with self._frame_lock:
            frames = list(self._frames)
        with wave.open(str(audio_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self._record_rate)
            wf.writeframes(b"".join(frames))

        if not frames:
            raise RuntimeError("Запись пустая — микрофон не слышит")

        duration, rms = self._measure_audio(audio_path)
        if duration < self.config.min_voice_duration_sec:
            raise RuntimeError(
                f"Слишком коротко ({duration:.1f} сек). "
                "Удерживай F9 дольше и говори после нажатия."
            )
        if rms < self.config.min_voice_rms:
            raise RuntimeError(
                "Слишком тихо — говори громче или проверь микрофон в Windows."
            )

        return audio_path

    @staticmethod
    def _measure_audio(audio_path: Path) -> tuple[float, float]:
        with wave.open(str(audio_path), "rb") as wf:
            rate = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
        if not raw:
            return 0.0, 0.0
        samples = struct.unpack(f"<{len(raw) // 2}h", raw)
        duration = len(samples) / rate
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        return duration, rms

    @staticmethod
    def _is_hallucination(text: str) -> bool:
        normalized = re.sub(r"\s+", " ", text.lower().strip())
        if len(normalized) < 2:
            return True
        words = re.findall(r"[a-zа-яё]{2,}", normalized, re.IGNORECASE)
        if len(words) <= 2 and len(normalized) > 25:
            return True
        if re.search(r"(.)\1{5,}", normalized):
            return True
        if len(set(words)) <= 2 and len(words) >= 8:
            return True
        return any(marker in normalized for marker in WHISPER_HALLUCINATION_MARKERS)

    def transcribe(self, audio_path: Path) -> str:
        errors: list[str] = []

        if self.config.use_faster_whisper:
            try:
                text = self._transcribe_faster_whisper(audio_path)
                if text and not self._is_hallucination(text):
                    logging.getLogger(__name__).info("Transcribed: %s", text)
                    return text
                errors.append("Whisper: похоже на шум, не на речь")
            except Exception as exc:
                errors.append(str(exc))

        try:
            text = self.transcribe_local_fallback(audio_path)
            if text and not self._is_hallucination(text):
                logging.getLogger(__name__).info("Transcribed fallback: %s", text)
                return text
            errors.append("Google STT: пустой или странный результат")
        except Exception as exc:
            errors.append(str(exc))

        raise RuntimeError(
            "Не удалось распознать речь. "
            "Удерживай F9, говори чётко после нажатия. "
            + (errors[0] if errors else "")
        )

    def _transcribe_faster_whisper(self, audio_path: Path) -> str:
        _suppress_hf_hub_noise()
        from faster_whisper import WhisperModel

        if self._whisper_model is None:
            self._whisper_model = WhisperModel(
                self.config.whisper_model_size,
                device="cpu",
                compute_type="int8",
            )

        kwargs: dict = {
            "condition_on_previous_text": False,
            "no_speech_threshold": 0.65,
            "compression_ratio_threshold": 2.2,
            "log_prob_threshold": -0.9,
            "beam_size": 5,
            "best_of": 5,
            "initial_prompt": (
                "Short voice commands in Russian or English for a desktop AI assistant. "
                "Examples: какую игру мне поиграть, что на экране, explain this, "
                "what should I play, pick a game from Steam."
            ),
        }
        if self.config.whisper_language:
            kwargs["language"] = self.config.whisper_language
        if self.config.whisper_vad_filter:
            kwargs["vad_filter"] = True
            kwargs["vad_parameters"] = {
                "min_silence_duration_ms": 500,
                "speech_pad_ms": 300,
            }

        segments, _info = self._whisper_model.transcribe(str(audio_path), **kwargs)
        parts: list[str] = []
        accepted_logprobs: list[float] = []
        for segment in segments:
            if getattr(segment, "no_speech_prob", 0) > 0.55:
                continue
            if getattr(segment, "avg_logprob", 0) < -1.0:
                continue
            chunk = segment.text.strip()
            if chunk:
                parts.append(chunk)
                accepted_logprobs.append(float(getattr(segment, "avg_logprob", 0)))

        text = " ".join(parts).strip()
        if not text:
            raise RuntimeError("Whisper не услышал слов")
        if accepted_logprobs and sum(accepted_logprobs) / len(accepted_logprobs) < -0.75:
            raise RuntimeError("Whisper low confidence")
        return text

    def transcribe_local_fallback(self, audio_path: Path) -> str:
        try:
            import speech_recognition as sr
        except ImportError as exc:
            raise RuntimeError(
                "Установи faster-whisper или SpeechRecognition: "
                "pip install faster-whisper SpeechRecognition pyaudio"
            ) from exc

        recognizer = sr.Recognizer()
        with sr.AudioFile(str(audio_path)) as source:
            audio = recognizer.record(source)

        try:
            return recognizer.recognize_google(audio, language="ru-RU").strip()
        except sr.UnknownValueError as exc:
            raise RuntimeError("Не удалось распознать речь") from exc
        except sr.RequestError as exc:
            raise RuntimeError("Google STT недоступен — нужен интернет") from exc

    def speak(self, text: str) -> None:
        speech_text = self._prepare_speech_text(text)
        if not speech_text:
            return

        with self._speak_lock:
            if self._shutdown_speech:
                return
        self.stop_speaking()
        with self._speak_lock:
            if self._shutdown_speech:
                return
            self._speech_generation += 1
            generation = self._speech_generation
        self._stop_speech.clear()

        try:
            from .language import detect_response_language, tts_voice_for_language

            lang = detect_response_language(speech_text)
            voice = tts_voice_for_language(lang, default_en=self.config.tts_voice)
            if asyncio.run(self._speak_edge_tts(speech_text, generation, voice)):
                return
        except Exception as exc:
            logging.getLogger(__name__).warning("edge-tts failed: %s", exc)

        if not self._is_current_speech(generation):
            return

        try:
            self._speak_pyttsx3(speech_text, generation)
        except Exception as exc:
            logging.getLogger(__name__).warning("pyttsx3 failed: %s", exc)

    def stop_speaking(self) -> None:
        self._stop_speech.set()
        with self._speak_lock:
            self._speech_generation += 1
            proc = self._playback_proc
            self._playback_proc = None
            engine = self._pyttsx3_engine
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        if engine is not None:
            try:
                engine.stop()
            except Exception:
                pass

    def shutdown(self) -> None:
        with self._speak_lock:
            self._shutdown_speech = True
        self.stop_speaking()
        self.cancel_recording()

    def _is_current_speech(self, generation: int) -> bool:
        with self._speak_lock:
            return (
                not self._stop_speech.is_set()
                and not self._shutdown_speech
                and generation == self._speech_generation
            )

    @staticmethod
    def _prepare_speech_text(text: str) -> str:
        """Convert Markdown-ish assistant output into text that sounds natural."""
        cleaned = text.strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r"```[\s\S]*?```", " code block omitted. ", cleaned)
        cleaned = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)

        lines: list[str] = []
        for raw_line in cleaned.splitlines():
            line = raw_line.strip()
            if not line:
                lines.append("")
                continue
            if re.fullmatch(r"[-*_#|: ]{3,}", line):
                continue
            line = re.sub(r"^\s{0,3}#{1,6}\s*", "", line)
            line = re.sub(r"^\s{0,3}>\s*", "", line)
            line = re.sub(r"^\s*[-*+]\s+", "", line)
            line = re.sub(r"^\s*\d+[\.)]\s+", "", line)
            line = line.replace("|", ". ")
            lines.append(line)

        cleaned = "\n".join(lines)
        cleaned = re.sub(r"[*_~#>`]+", "", cleaned)
        cleaned = re.sub(r"\s+([,.!?;:])", r"\1", cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def _speech_chunks(text: str, max_chars: int = 1400) -> list[str]:
        paragraphs = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
        chunks: list[str] = []
        current = ""

        def emit_current() -> None:
            nonlocal current
            if current.strip():
                chunks.append(current.strip())
            current = ""

        for paragraph in paragraphs:
            sentences = re.split(r"(?<=[.!?])\s+", paragraph)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                if len(sentence) > max_chars:
                    emit_current()
                    for start in range(0, len(sentence), max_chars):
                        chunks.append(sentence[start:start + max_chars].strip())
                    continue
                candidate = f"{current} {sentence}".strip() if current else sentence
                if len(candidate) > max_chars:
                    emit_current()
                    current = sentence
                else:
                    current = candidate
            emit_current()
        return chunks

    async def _speak_edge_tts(self, text: str, generation: int, voice: str | None = None) -> bool:
        import edge_tts

        if not self._is_current_speech(generation):
            return True

        tts_voice = voice or self.config.tts_voice
        spoken_any = False
        for chunk in self._speech_chunks(text):
            if not self._is_current_speech(generation):
                return True

            communicate = edge_tts.Communicate(chunk, tts_voice)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                mp3_path = Path(tmp.name)

            try:
                try:
                    await communicate.save(str(mp3_path))
                except Exception:
                    if spoken_any:
                        logging.getLogger(__name__).warning(
                            "edge-tts stopped after partial speech"
                        )
                        return True
                    raise
                if not self._is_current_speech(generation):
                    return True
                if not self._play_mp3_windows(mp3_path, generation):
                    logging.getLogger(__name__).warning("MP3 playback failed or was stopped")
                    return True
                spoken_any = True
            finally:
                mp3_path.unlink(missing_ok=True)
        return True

    def _speak_pyttsx3(self, text: str, generation: int) -> None:
        import pyttsx3

        engine = pyttsx3.init()
        with self._speak_lock:
            self._pyttsx3_engine = engine
        try:
            if not self._is_current_speech(generation):
                return
            engine.setProperty("rate", 180)
            engine.say(text)
            engine.runAndWait()
        finally:
            with self._speak_lock:
                if self._pyttsx3_engine is engine:
                    self._pyttsx3_engine = None

    def _play_mp3_windows(self, mp3_path: Path, generation: int) -> bool:
        path = mp3_path.resolve()
        path_str = str(path)
        uri = path.as_uri()
        hidden = _subprocess_hidden()

        def run_player(args: list[str], timeout: float = 120) -> bool:
            if not self._is_current_speech(generation):
                return False
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **hidden,
            )
            with self._speak_lock:
                self._playback_proc = proc
            deadline = time.monotonic() + timeout
            try:
                while proc.poll() is None:
                    if (
                        not self._is_current_speech(generation)
                        or time.monotonic() >= deadline
                    ):
                        try:
                            proc.terminate()
                            proc.wait(timeout=1)
                        except Exception:
                            try:
                                proc.kill()
                            except Exception:
                                pass
                        return False
                    time.sleep(0.1)
                return proc.returncode == 0
            finally:
                with self._speak_lock:
                    if self._playback_proc is proc:
                        self._playback_proc = None

        if sys.platform == "win32":
            ps_script = (
                "Add-Type -AssemblyName presentationCore; "
                "$p = New-Object System.Windows.Media.MediaPlayer; "
                f"$p.Open([Uri]::new('{uri}')); "
                "$p.Play(); "
                "while ($p.NaturalDuration.HasTimeSpan -eq $false) { Start-Sleep -Milliseconds 100 }; "
                "$sec = [math]::Ceiling($p.NaturalDuration.TimeSpan.TotalSeconds) + 1; "
                "Start-Sleep -Seconds $sec"
            )
            try:
                if run_player(
                    [
                        "powershell",
                        "-NoProfile",
                        "-NonInteractive",
                        "-WindowStyle",
                        "Hidden",
                        "-Command",
                        ps_script,
                    ]
                ):
                    return True
            except Exception:
                pass

        try:
            return run_player(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path_str])
        except Exception:
            pass

        return False
