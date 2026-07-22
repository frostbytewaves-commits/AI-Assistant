import ctypes

import threading

import time

import tkinter as tk

from tkinter import ttk

from pathlib import Path



from .capture import capture_foreground_window, capture_full_screen, get_foreground_window_handle

from .config import AssistantConfig

from .core import (
    ContextBuilder,
    ContextManager,
    Orchestrator,
    PushToTalkActivation,
    VoiceTurnCoordinator,
)

from .screen_context import ScreenContext

from .followup import (
    build_expansion_prompt,
    build_continuation_message,
    extract_followup_options,
    is_conversation_followup,
    match_followup_selection,
    normalize_followup_text,
    strip_false_pick_prompt,
)
from .advisory_topics import ensure_advisory_options
from .intent import QueryIntent, effective_screen_question, is_game_advisory_question
from .memory import AssistantMemory

from .llm import OllamaClient

from . import markdown_ui as md

from .orb import OrbAnimator

from .voice import VoiceEngine



user32 = ctypes.windll.user32

SW_HIDE = 0

SW_SHOW = 5





class GameAssistantApp:

    def __init__(self, config: AssistantConfig | None = None) -> None:

        self.config = config or AssistantConfig()

        self.config.ensure_dirs()



        self.llm = OllamaClient(self.config)
        self.memory = AssistantMemory.load(self.config.memory_path)
        self.context_builder = ContextManager(
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
        self.orchestrator = Orchestrator(
            self.config,
            self.llm,
            self.memory,
            context_builder=self.context_builder,
        )

        self.voice = VoiceEngine(self.config)
        self.voice_pipeline = VoiceTurnCoordinator(
            config=self.config,
            voice=self.voice,
            orchestrator=self.orchestrator,
        )
        self.voice_activation = PushToTalkActivation(
            self.start_voice_hold,
            self.stop_voice_hold,
        )

        self.is_busy = False

        self.voice_recording = False

        self._busy_since: float | None = None

        self._stream_mark: str | None = None

        self._stream_active = False

        self._pending_screenshot: Path | None = None

        self._pending_screen_context: ScreenContext | None = None

        self._capturing_screen = False

        self._last_user_question = ""

        self._followup_options: list[dict] = []

        self._followup_topic = ""

        self._last_assistant_brief = ""

        self._chat_history: list[tuple[str, str]] = []

        self._followup_option_widgets: list[tk.Widget] = []

        # Soft AI orb: idle | listening | busy (Apple Intelligence mesh)
        self._orb_state = "idle"
        self._orb_phase = 0.0
        self._orb_after_id: str | None = None
        self._orb_size = 56
        self._orb: OrbAnimator | None = None

        self.root = tk.Tk()

        self.root.title("Assistant")

        self.root.geometry("560x720+24+24")

        self.root.configure(bg=md.BG)

        self.root.attributes("-topmost", True)
        self.root.minsize(460, 520)
        # Keep overlay visible over other apps (without stealing keyboard focus).
        self.root.after(800, self._keep_topmost)

        self.status_var = tk.StringVar(value="Ready")

        self._build_ui()

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._bind_clipboard_shortcuts()

        threading.Thread(target=self._warmup_models, daemon=True).start()



    def _toplevel_hwnd(self) -> int:
        """Real Win32 HWND of the Tk toplevel (winfo_id is often a child)."""
        try:
            hwnd = int(self.root.winfo_id())
            GA_ROOT = 2
            root = int(user32.GetAncestor(hwnd, GA_ROOT) or 0)
            return root or hwnd
        except Exception:
            return int(self.root.winfo_id() or 0)

    def _keep_topmost(self) -> None:
        """Force always-on-top via Win32 — Tk -topmost alone is unreliable here."""
        try:
            if not self.root.winfo_exists():
                return
            self.root.attributes("-topmost", True)
            hwnd = self._toplevel_hwnd()
            if hwnd:
                HWND_TOPMOST = -1
                SWP_NOSIZE = 0x0001
                SWP_NOMOVE = 0x0002
                SWP_NOACTIVATE = 0x0010
                user32.SetWindowPos(
                    hwnd,
                    HWND_TOPMOST,
                    0,
                    0,
                    0,
                    0,
                    SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
                )
            self.root.after(1200, self._keep_topmost)
        except Exception:
            try:
                self.root.after(2000, self._keep_topmost)
            except Exception:
                pass

    def _bind_clipboard_shortcuts(self) -> None:
        # Chat log
        self.output.bind("<Control-KeyPress>", self._chat_ctrl_key)
        self.output.bind("<Control-Insert>", self._chat_copy)
        # Input: layout-independent — Windows keycodes for A/C/V/X stay the same on RU/EN
        self.input_entry.bind("<Control-KeyPress>", self._entry_ctrl_key)
        self.input_entry.bind("<Shift-Insert>", self._entry_paste)
        self.input_entry.bind("<<Paste>>", self._entry_paste)
        self.input_entry.bind("<Shift-Delete>", self._entry_cut)
        self.input_entry.bind("<Button-3>", self._input_context_menu)

    # Win32 virtual-key codes (stable across keyboard layouts)
    _VK_A, _VK_C, _VK_V, _VK_X = 0x41, 0x43, 0x56, 0x58

    def _entry_ctrl_key(self, event: tk.Event) -> str | None:
        code = int(getattr(event, "keycode", 0) or 0)
        # On some Tk builds keycode is already the VK; also accept keysym fallbacks
        sym = (event.keysym or "").lower()
        if code in (self._VK_V, 86) or sym in {"v", "м", "cyrillic_em"}:
            return self._entry_paste()
        if code in (self._VK_C, 67) or sym in {"c", "с", "cyrillic_es"}:
            return self._entry_copy()
        if code in (self._VK_X, 88) or sym in {"x", "ч", "cyrillic_cha"}:
            return self._entry_cut()
        if code in (self._VK_A, 65) or sym in {"a", "ф", "cyrillic_ef"}:
            return self._entry_select_all()
        return None

    def _chat_ctrl_key(self, event: tk.Event) -> str | None:
        code = int(getattr(event, "keycode", 0) or 0)
        sym = (event.keysym or "").lower()
        if code in (self._VK_C, 67) or sym in {"c", "с", "cyrillic_es"}:
            return self._chat_copy()
        if code in (self._VK_A, 65) or sym in {"a", "ф", "cyrillic_ef"}:
            return self._chat_select_all()
        return None

    def _clipboard_text(self) -> str:
        """Read Windows clipboard robustly (Tk CLIPBOARD / STRING / CF_UNICODETEXT)."""
        errors: list[Exception] = []
        for getter in (
            lambda: self.root.clipboard_get(),
            lambda: self.root.clipboard_get(type="STRING"),
            lambda: self.root.clipboard_get(type="UTF8_STRING"),
            lambda: self.root.tk.call("::tk::GetSelection", self.root, "CLIPBOARD"),
        ):
            try:
                value = getter()
                if value:
                    return str(value)
            except Exception as exc:  # TclError and others
                errors.append(exc)
        # Win32 CF_UNICODETEXT fallback
        try:
            CF_UNICODETEXT = 13
            OpenClipboard = user32.OpenClipboard
            GetClipboardData = user32.GetClipboardData
            CloseClipboard = user32.CloseClipboard
            kernel32 = ctypes.windll.kernel32
            if not OpenClipboard(None):
                return ""
            try:
                handle = GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return ""
                ptr = kernel32.GlobalLock(handle)
                if not ptr:
                    return ""
                try:
                    return ctypes.wstring_at(ptr)
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                CloseClipboard()
        except Exception:
            return ""

    @staticmethod
    def _readonly_chat_key(event: tk.Event) -> str | None:
        # Allow shortcuts (Ctrl) and navigation; block typing into the chat log.
        if event.state & 0x4:  # Control
            return None
        if event.keysym in {
            "Left", "Right", "Up", "Down", "Home", "End", "Prior", "Next",
            "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R",
            "Escape", "Tab", "Insert",
        }:
            return None
        return "break"

    def _chat_copy(self, _event=None):
        try:
            text = self.output.selection_get()
        except tk.TclError:
            return "break"
        if text:
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                self.root.update_idletasks()
            except Exception:
                pass
        return "break"

    def _chat_select_all(self, _event=None):
        self.output.tag_add("sel", "1.0", "end")
        return "break"

    def _entry_copy(self, _event=None):
        try:
            text = self.input_entry.selection_get()
        except tk.TclError:
            return "break"
        if text:
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                self.root.update_idletasks()
            except Exception:
                pass
        return "break"

    def _entry_cut(self, _event=None):
        try:
            text = self.input_entry.selection_get()
        except tk.TclError:
            return "break"
        if text:
            try:
                self.root.clipboard_clear()
                self.root.clipboard_append(text)
                self.root.update_idletasks()
                self.input_entry.delete("sel.first", "sel.last")
            except Exception:
                pass
        return "break"

    def _entry_paste(self, _event=None):
        text = self._clipboard_text()
        if not text:
            return "break"
        try:
            self.input_entry.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        self.input_entry.insert("insert", text)
        return "break"

    def _entry_select_all(self, _event=None):
        self.input_entry.selection_range(0, "end")
        self.input_entry.icursor("end")
        return "break"

    def _input_context_menu(self, event: tk.Event):
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="Cut", command=lambda: self._entry_cut())
        menu.add_command(label="Copy", command=lambda: self._entry_copy())
        menu.add_command(label="Paste", command=lambda: self._entry_paste())
        menu.add_separator()
        menu.add_command(label="Select all", command=lambda: self._entry_select_all())
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
        return "break"

    def _run_on_main(self, fn, timeout: float = 1.5) -> None:
        if threading.current_thread() is threading.main_thread():
            fn()
            return
        done = threading.Event()

        def wrapper() -> None:
            try:
                fn()
            finally:
                done.set()

        self.root.after(0, wrapper)
        done.wait(timeout)



    def _warmup_models(self) -> None:

        """Держит модели в VRAM — первый ответ быстрее."""

        import requests

        base = self.config.ollama_url.rstrip("/")

        models = [self.llm.resolve_text_model()]
        if self.config.warmup_vision:
            vision = self.llm.resolve_vision_model()
            if vision:
                models.append(vision)

        for model in models:

            if not model:

                continue

            try:

                payload = {
                    "model": model,
                    "messages": [{"role": "user", "content": "hi /no_think"}],
                    "stream": False,
                    "keep_alive": self.config.ollama_keep_alive,
                    "options": {
                        "num_predict": 1,
                        "num_ctx": int(self.config.num_ctx),
                    },
                }
                if self.llm._is_thinking_model(model):
                    payload["think"] = False  # warm-up stays cheap; answers use profile thinking

                requests.post(
                    f"{base}/api/chat",
                    json=payload,

                    timeout=120,

                )

            except Exception:

                pass



    def _build_ui(self) -> None:

        style = ttk.Style()

        style.theme_use("clam")

        style.configure("Chat.TFrame", background=md.BG)

        style.configure(

            "Action.TButton",

            background=md.SURFACE,

            foreground=md.TEXT,

            borderwidth=0,

            focusthickness=0,

            padding=(14, 8),

            font=("Segoe UI", 10),

        )

        style.map(

            "Action.TButton",

            background=[("active", md.SURFACE_HOVER), ("pressed", md.BORDER)],

        )



        header = tk.Frame(self.root, bg=md.BG, pady=14, padx=20)

        header.pack(fill="x")

        left_header = tk.Frame(header, bg=md.BG)
        left_header.pack(side="left", fill="y")

        self.speak_indicator = tk.Canvas(
            left_header,
            width=self._orb_size,
            height=self._orb_size,
            bg=md.BG,
            highlightthickness=0,
            bd=0,
        )
        self.speak_indicator.pack(side="left", padx=(0, 12))
        self._orb = OrbAnimator(
            self.speak_indicator,
            size=self._orb_size,
            bg_hex=md.BG,
        )
        self._mic_dot = None  # legacy; voice paths use _set_mic_dot → orb state

        title_col = tk.Frame(left_header, bg=md.BG)
        title_col.pack(side="left", fill="y")
        tk.Label(
            title_col,
            text="Assistant",
            font=("Segoe UI", 14, "bold"),
            bg=md.BG,
            fg=md.TEXT,
        ).pack(anchor="w")
        self.status_label = tk.Label(
            title_col,
            textvariable=self.status_var,
            font=("Segoe UI", 9),
            bg=md.BG,
            fg=md.TEXT_MUTED,
            padx=0,
            pady=0,
        )
        self.status_label.pack(anchor="w")

        self._set_orb_state("idle")
        self._start_orb_pulse()

        sep = tk.Frame(self.root, bg=md.BORDER, height=1)

        sep.pack(fill="x")



        chat_wrap = tk.Frame(self.root, bg=md.BG)

        chat_wrap.pack(fill="both", expand=True, padx=0, pady=0)



        self.scroll = tk.Scrollbar(chat_wrap, orient="vertical")

        self.output = tk.Text(

            chat_wrap,

            wrap="word",

            bg=md.BG,

            fg=md.TEXT,

            relief="flat",

            bd=0,

            padx=0,

            pady=16,

            highlightthickness=0,

            yscrollcommand=self.scroll.set,

            cursor="arrow",

        )

        self.scroll.config(command=self.output.yview)

        self.scroll.pack(side="right", fill="y")

        self.output.pack(side="left", fill="both", expand=True)

        # NORMAL so user can select/copy; keys that would edit are blocked.
        self.output.configure(state=tk.NORMAL)

        md.configure_chat_tags(self.output)

        md.clear_chat(self.output)
        self.output.bind("<Key>", self._readonly_chat_key)



        bottom = tk.Frame(self.root, bg=md.BG, padx=14, pady=0)

        bottom.pack(fill="x", side="bottom", pady=(8, 12))

        action_bar = tk.Frame(bottom, bg=md.BG, pady=0, padx=0)

        action_bar.pack(fill="x", side="top", pady=(0, 8))

        btn_inner = tk.Frame(action_bar, bg=md.BG)

        btn_inner.pack(fill="x")

        input_bar = tk.Frame(
            bottom,
            bg=md.SURFACE,
            padx=14,
            pady=10,
            highlightthickness=1,
            highlightbackground=md.BORDER,
            highlightcolor=md.ACCENT,
        )

        input_bar.pack(fill="x", side="bottom")



        self.input_var = tk.StringVar()

        self.input_entry = tk.Entry(

            input_bar,

            textvariable=self.input_var,

            font=("Segoe UI", 11),

            bg=md.SURFACE,

            fg=md.TEXT,

            insertbackground=md.TEXT,

            relief="flat",

            highlightthickness=0,

            highlightbackground=md.BORDER,

            highlightcolor=md.ACCENT,

        )

        self.input_entry.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))

        self.input_entry.bind("<Return>", self._on_input_enter)
        # Clipboard binds are registered in _bind_clipboard_shortcuts (handles RU layout).



        ttk.Button(

            input_bar,

            text="→",

            style="Action.TButton",

            command=self._send_text_message,

            width=3,

        ).pack(side="right")

        self.input_bar = input_bar

        self.options_frame = tk.Frame(bottom, bg=md.BG)



        self.screen_btn = ttk.Button(

            btn_inner,

            text="Screen",

            style="Action.TButton",

            command=self.start_screen_analysis,

        )

        self.screen_btn.pack(side="left", padx=(0, 6))



        self.voice_btn = ttk.Button(

            btn_inner,

            text="Voice",

            style="Action.TButton",

            command=self._toggle_voice_button,

        )

        self.voice_btn.pack(side="left", padx=(0, 6))



        ttk.Button(

            btn_inner,

            text="Speak",

            style="Action.TButton",

            command=self.toggle_speak,

        ).pack(side="left")



        self.root.after(500, self._poll_busy_watchdog)



    def _set_mic_dot(self, recording: bool) -> None:
        """Legacy voice hook — maps to orb listening / idle."""
        self._set_orb_state("listening" if recording else ("busy" if self.is_busy else "idle"))

    def _set_orb_state(self, state: str) -> None:
        if state not in {"idle", "listening", "busy"}:
            state = "idle"
        self._orb_state = state
        if self._orb is not None:
            self._orb.set_mode(state)  # type: ignore[arg-type]
            breath = 1.0 if state != "idle" else 0.55
            try:
                self._orb.paint(breath)
            except tk.TclError:
                pass

    def _start_orb_pulse(self) -> None:
        if self._orb_after_id is not None:
            return
        self._tick_orb_pulse()

    def _stop_orb_pulse(self) -> None:
        if self._orb_after_id is not None:
            try:
                self.root.after_cancel(self._orb_after_id)
            except Exception:
                pass
            self._orb_after_id = None

    def _tick_orb_pulse(self) -> None:
        if self._orb is None:
            return
        if self._orb_state == "listening":
            speed, base, amp = 0.18, 0.55, 0.42
        elif self._orb_state == "busy":
            speed, base, amp = 0.12, 0.48, 0.48
        else:
            speed, base, amp = 0.05, 0.38, 0.28
        try:
            self._orb.tick(speed=speed, base=base, amp=amp)
        except tk.TclError:
            return
        self._orb_after_id = self.root.after(40, self._tick_orb_pulse)

    def _show_welcome(self) -> None:
        self.output.configure(state=tk.NORMAL)
        md.clear_chat(self.output)
        self.output.configure(state=tk.NORMAL)



    def _record_chat(self, role: str, text: str) -> None:
        cleaned = text.strip()
        if not cleaned:
            return
        if role.lower() == "user":
            fallback_game = self.llm._resolve_game_id(self._followup_topic or cleaned)
            self.memory.update_from_user(cleaned, fallback_game=fallback_game)
        elif role.lower() == "assistant":
            fallback_game = self.llm._resolve_game_id(self._followup_topic or self._last_user_question)
            self.memory.note_assistant_message(cleaned, fallback_game=fallback_game)
        self._chat_history.append((role, cleaned))
        if len(self._chat_history) > 16:
            self._chat_history = self._chat_history[-16:]

    def _excluded_hwnd(self) -> int | None:
        try:
            return self._assistant_hwnd()
        except Exception:
            return None

    def _host_context(self):
        """Fresh Host snapshot (open windows) for the model — no screenshot."""
        return self.context_builder.build(excluded_hwnd=self._excluded_hwnd())

    def _conversation_context(self) -> str:
        return self.orchestrator.build_conversation_context(
            self._chat_history,
            excluded_hwnd=self._excluded_hwnd(),
        )

    def _append_user(self, text: str) -> None:

        self._record_chat("User", text)

        self.output.configure(state=tk.NORMAL)

        md.append_user_message(self.output, text)

        self.output.configure(state=tk.NORMAL)

        self.output.see(tk.END)



    def _append_assistant(self, text: str) -> None:

        self.output.configure(state=tk.NORMAL)

        md.append_assistant_message(self.output, text)

        self.output.configure(state=tk.NORMAL)

        self.output.see(tk.END)



    def _append_note(self, text: str) -> None:

        self.output.configure(state=tk.NORMAL)

        md.append_system_note(self.output, text)

        self.output.configure(state=tk.NORMAL)

        self.output.see(tk.END)



    def _append_error(self, text: str) -> None:

        self.output.configure(state=tk.NORMAL)

        md.append_error(self.output, text)

        self.output.configure(state=tk.NORMAL)

        self.output.see(tk.END)



    def _poll_busy_watchdog(self) -> None:

        if self.is_busy and self._busy_since is not None:
            # UI watchdog must outlive HTTP text timeout (thinking can be slow on CPU).
            limit = max(180, int(self.config.text_timeout_sec) + 60)
            if time.time() - self._busy_since > limit:

                self._set_busy(False)

                self.set_status("Timeout — restart assistant")

                text_model = self.llm.resolve_text_model()
                vision = self.llm.resolve_vision_model() or "none"
                self._append_note(
                    "Request took too long. Restart the assistant. "
                    f"Unload unused Ollama models (`ollama stop`), keep primarily {text_model}"
                    + (f" (vision {vision} only when using Screen)." if vision != "none" else ".")
                )

        self.root.after(1000, self._poll_busy_watchdog)



    def _set_busy(self, busy: bool) -> None:

        self.is_busy = busy

        self._busy_since = time.time() if busy else None

        state = tk.DISABLED if busy else tk.NORMAL

        self.screen_btn.configure(state=state)

        self.input_entry.configure(state=state)

        if not self.voice_recording:

            self.voice_btn.configure(state=state)

        if self.voice_recording:
            self._set_orb_state("listening")
        elif busy:
            self._set_orb_state("busy")
        else:
            self._set_orb_state("idle")



    def _toggle_voice_button(self) -> None:

        if self.voice_recording:

            self.voice_activation.stop()

        else:

            self.voice_activation.start()



    def set_status(self, text: str) -> None:

        self.status_var.set(text)



    def _llm_status(self, text: str) -> None:

        self.root.after(0, lambda: self.set_status(text))



    def _begin_assistant_stream(self) -> None:

        self.output.configure(state=tk.NORMAL)

        self._stream_mark = md.begin_assistant_stream(self.output)

        self._stream_active = True

        self.output.configure(state=tk.NORMAL)



    def _append_stream_chunk(self, chunk: str) -> None:

        self.output.configure(state=tk.NORMAL)

        md.append_assistant_stream_chunk(self.output, chunk)

        self.output.configure(state=tk.NORMAL)



    def _finalize_assistant_stream(self, full_text: str) -> None:

        self.output.configure(state=tk.NORMAL)

        if self._stream_active and self._stream_mark:

            md.finalize_assistant_stream(self.output, self._stream_mark, full_text)

        else:

            md.append_assistant_message(self.output, full_text)

        self._stream_mark = None

        self._stream_active = False

        self.output.configure(state=tk.NORMAL)

        self.output.see(tk.END)



    def _make_token_callback(self):

        if not self.config.streaming:

            return None

        state = {"started": False, "buf": "", "pending": False}

        def flush() -> None:

            state["pending"] = False

            if not state["buf"]:

                return

            chunk, state["buf"] = state["buf"], ""

            self._append_stream_chunk(chunk)

        def on_token(chunk: str) -> None:

            if not state["started"]:

                state["started"] = True

                self.root.after(0, self._begin_assistant_stream)

            state["buf"] += chunk

            if not state["pending"]:

                state["pending"] = True

                self.root.after(40, lambda: self.root.after(0, flush))

        def flush_remaining() -> None:

            self.root.after(0, flush)

        on_token.flush_remaining = flush_remaining  # type: ignore[attr-defined]

        return on_token



    def _on_input_enter(self, _event=None) -> None:

        self._send_text_message()



    def _send_text_message(self) -> None:

        if self.is_busy or self.voice_recording or self._capturing_screen:

            return

        question = normalize_followup_text(self.input_var.get().strip())

        if self._followup_options and question:
            selected = match_followup_selection(question, self._followup_options)
            if selected is not None:
                self.input_var.set("")
                self._set_busy(True)
                self.set_status("Thinking…")
                self._append_user(selected["title"])
                topic = self._followup_topic
                game_id = self.llm._resolve_game_id(topic)
                self._clear_followup_buttons()
                prompt = build_expansion_prompt(topic, selected, game_id=game_id)
                threading.Thread(
                    target=lambda: self._run_advisory_expansion(
                        prompt, selected["title"], game_id=game_id, source_topic=topic,
                    ),
                    daemon=True,
                ).start()
                return

        if self._followup_topic and question and is_conversation_followup(
            question, self._followup_topic,
        ):
            self.input_var.set("")
            self._set_busy(True)
            self.set_status("Thinking…")
            self._append_user(question)
            topic = self._followup_topic
            game_id = self.llm._resolve_game_id(topic)
            cont = build_continuation_message(
                topic,
                question,
                prior_brief=self._last_assistant_brief,
                game_id=game_id,
            )
            self._clear_followup_buttons()
            threading.Thread(
                target=lambda: self._run_query_with_capture(cont, lang_question=question),
                daemon=True,
            ).start()
            return

        if self._followup_options:
            self._clear_followup_buttons()

        if question and self._followup_topic and not is_conversation_followup(
            question, self._followup_topic,
        ):
            self._followup_topic = ""
            self._last_assistant_brief = ""

        pending_path = self._pending_screenshot

        pending_ctx = self._pending_screen_context

        if not question and pending_path is None:

            return

        self.input_var.set("")

        self._set_busy(True)

        self.set_status("Thinking…")

        if question:

            self._append_user(question)

            self._last_user_question = question

        elif pending_path is not None:

            self._append_note("📷 Screenshot attached")

        if pending_path is not None:

            self._pending_screenshot = None

            self._pending_screen_context = None

            threading.Thread(

                target=lambda: self._run_attached_screen_query(

                    question, pending_path, pending_ctx,

                ),

                daemon=True,

            ).start()

            return

        threading.Thread(

            target=lambda: self._run_query_with_capture(question),

            daemon=True,

        ).start()



    def _clear_followup_buttons(self) -> None:

        self._followup_options = []

        for widget in self._followup_option_widgets:

            widget.destroy()

        self._followup_option_widgets = []

        self.options_frame.pack_forget()



    def _clear_followup_options(self) -> None:

        self._clear_followup_buttons()

        self._followup_topic = ""

        self._last_assistant_brief = ""



    def _show_followup_options(self, options: list[dict]) -> None:

        self._clear_followup_options()

        if not options:

            return

        self._followup_options = options

        self.options_frame.pack(fill="x", side="top", pady=(0, 6), before=self.input_bar)

        for opt in options:

            label = f"{opt['id']}. {opt['title']}"

            btn = ttk.Button(

                self.options_frame,

                text=label,

                style="Action.TButton",

                command=lambda o=opt: self._on_followup_click(o),

            )

            btn.pack(side="left", padx=(0, 6), pady=2)

            self._followup_option_widgets.append(btn)



    def _on_followup_click(self, option: dict) -> None:

        if self.is_busy or self.voice_recording:

            return

        topic = self._followup_topic

        game_id = self.llm._resolve_game_id(topic)

        self._clear_followup_options()

        self._set_busy(True)

        self.set_status("Thinking…")

        self._append_user(option["title"])

        prompt = build_expansion_prompt(topic, option, game_id=game_id)

        threading.Thread(

            target=lambda: self._run_advisory_expansion(
                prompt, option["title"], game_id=game_id, source_topic=topic,
            ),

            daemon=True,

        ).start()



    def _run_advisory_expansion(
        self,
        prompt: str,
        display_title: str,
        *,
        game_id: str | None = None,
        source_topic: str = "",
    ) -> None:

        try:
            item_detail = self.llm._game_kb.item_source_detail(
                game_id, source_topic or self._followup_topic or prompt, display_title,
            )
            if item_detail:
                self._finish(item_detail, parse_followup=False)
                return

            on_token = self._make_token_callback()
            result = self.orchestrator.handle_turn(
                prompt,
                pre_intent=QueryIntent.fallback_text(prompt),
                lang_question=display_title,
                advisory_mode="expand",
                active_game=game_id,
                chat_history=self._chat_history,
                excluded_hwnd=self._excluded_hwnd(),
                on_status=self._llm_status,
                on_token=on_token,
            )
            if on_token is not None:
                flush_remaining = getattr(on_token, "flush_remaining", None)
                if flush_remaining is not None:
                    flush_remaining()
            self._finish(result.answer, parse_followup=False)

        except Exception as exc:

            self.root.after(0, self._show_window)

            self._finish_error(str(exc))



    def toggle_speak(self) -> None:

        self.config.speak_answers = not self.config.speak_answers



    def start_screen_analysis(self) -> None:

        if self.is_busy or self.voice_recording or self._capturing_screen:

            self.set_status("Busy…" if self.is_busy else "Release F9 first")

            return

        self._capturing_screen = True

        self.set_status("Capturing screen…")

        threading.Thread(target=self._capture_screen_for_question, daemon=True).start()



    def _capture_screen_for_question(self) -> None:

        try:

            image_path, ctx = self._grab_screen_for_analysis()

            def on_ready() -> None:

                self._capturing_screen = False

                self._clear_followup_options()

                self._pending_screenshot = image_path

                self._pending_screen_context = ctx

                if ctx.oni_window:

                    hint = "ONI — type a question and press Enter (or Enter alone for auto-analysis)"

                elif ctx.minecraft_window:

                    hint = "Minecraft — type a question and press Enter (or Enter alone for auto-analysis)"

                elif ctx.active_game:

                    hint = "Game — type a question and press Enter (or Enter alone for auto-analysis)"

                else:

                    hint = "Screenshot ready — type a question and press Enter (or Enter alone)"

                self.set_status(hint)

                self._show_window()

                self.input_entry.focus_set()

            self.root.after(0, on_ready)

        except Exception as exc:

            def on_error() -> None:

                self._capturing_screen = False

                self._append_error(str(exc))

                self.set_status("Ready")

            self.root.after(0, on_error)



    def _run_attached_screen_query(

        self,

        user_question: str,

        image_path: Path,

        ctx: ScreenContext,

    ) -> None:

        try:

            on_token = self._make_token_callback()
            effective = effective_screen_question(user_question)
            result = self.orchestrator.handle_turn(
                effective,
                image_path=image_path,
                screen_context=ctx,
                lang_question=user_question.strip() or None,
                chat_history=self._chat_history,
                excluded_hwnd=self._excluded_hwnd(),
                on_status=self._llm_status,
                on_token=on_token,
                attached_screen=True,
            )

            if on_token is not None:

                flush_remaining = getattr(on_token, "flush_remaining", None)

                if flush_remaining is not None:

                    flush_remaining()

            self._finish(result.answer)

        except Exception as exc:

            self.root.after(0, self._show_window)

            self._finish_error(str(exc))



    def _screen_context_now(self, assistant_hwnd: int | None = None) -> ScreenContext:
        hwnd = assistant_hwnd
        if hwnd is None:
            try:
                hwnd = self._assistant_hwnd()
            except Exception:
                hwnd = None
        try:
            return self.context_builder.build(excluded_hwnd=hwnd).to_screen_context()
        except Exception:
            return ScreenContext.detect(hwnd)

    def _grab_screen_now(self) -> tuple[Path, ScreenContext]:
        assistant_hwnd = self._prepare_for_capture()
        ctx = self._screen_context_now(assistant_hwnd)
        try:
            path = capture_foreground_window(
                self.config.screenshot_dir,
                excluded_hwnd=assistant_hwnd,
            )
        except Exception:
            path = capture_full_screen(self.config.screenshot_dir)
        self._restore_after_capture()
        return path, ctx

    def _grab_screen_for_voice(self) -> tuple[Path, ScreenContext]:
        """Voice queries: never hide the assistant; a visible overlay is less disruptive."""
        assistant_hwnd = self._assistant_hwnd()
        foreground_hwnd = get_foreground_window_handle()
        ctx = self._screen_context_now(assistant_hwnd)
        if foreground_hwnd and foreground_hwnd != assistant_hwnd:
            try:
                path = capture_foreground_window(
                    self.config.screenshot_dir,
                    excluded_hwnd=assistant_hwnd,
                    prefix="voice",
                )
            except Exception:
                path = capture_full_screen(self.config.screenshot_dir, prefix="voice")
            return path, ctx
        path = capture_full_screen(self.config.screenshot_dir, prefix="voice")
        return path, ctx



    def _grab_screen_for_analysis(self) -> tuple[Path, ScreenContext]:
        """F8: полный экран на рабочем столе, иначе активное окно игры."""
        assistant_hwnd = self._prepare_for_capture()
        ctx = self._screen_context_now(assistant_hwnd)
        if ctx.active_game:
            try:
                path = capture_foreground_window(
                    self.config.screenshot_dir,
                    excluded_hwnd=assistant_hwnd,
                )
            except Exception:
                path = capture_full_screen(self.config.screenshot_dir)
        else:
            path = capture_full_screen(self.config.screenshot_dir)
        self._restore_after_capture()
        return path, ctx



    def _run_query_with_capture(
        self, question: str, *, lang_question: str | None = None,
    ) -> None:

        try:
            self._run_query(question, lang_question=lang_question)
        except Exception as exc:
            self.root.after(0, self._show_window)
            self._finish_error(str(exc))

    def _run_query(

        self,

        question: str,

        *,

        image_path: Path | None = None,

        pre_intent=None,

        screen_context: ScreenContext | None = None,

        lang_question: str | None = None,

    ) -> None:

        try:

            on_token = self._make_token_callback()

            def capture() -> tuple[Path, ScreenContext]:
                self.root.after(0, lambda: self.set_status("Screenshot…"))
                return self._grab_screen_for_voice()

            result = self.orchestrator.handle_turn(
                question,
                image_path=image_path,
                screen_context=screen_context,
                pre_intent=pre_intent,
                lang_question=lang_question,
                chat_history=self._chat_history,
                excluded_hwnd=self._excluded_hwnd(),
                on_status=self._llm_status,
                on_token=on_token,
                capture_screen=capture,
            )

            if on_token is not None:

                flush_remaining = getattr(on_token, "flush_remaining", None)

                if flush_remaining is not None:

                    flush_remaining()

            self._finish(result.answer)

        except Exception as exc:

            self.root.after(0, self._show_window)

            self._finish_error(str(exc))



    def start_voice_hold(self) -> None:

        if self.is_busy or self.voice_recording:

            return

        self.voice_recording = True

        self._set_mic_dot(True)

        self.voice_btn.configure(text="Stop")

        self.set_status("Listening…")

        self._pending_screenshot = None

        self._pending_screen_context = None

        try:

            self.voice_pipeline.start_recording()

        except Exception as exc:

            self.voice_recording = False

            self._set_mic_dot(False)

            self.voice_btn.configure(text="Voice")

            self._append_error(str(exc))



    def stop_voice_hold(self) -> None:

        if not self.voice_recording:

            return

        if self.is_busy:

            self.voice_pipeline.cancel_recording()

            self.voice_recording = False

            self._set_mic_dot(False)

            self.voice_btn.configure(text="Voice")

            self.set_status("Wait — previous answer in progress")

            return

        self.voice_recording = False

        self._set_mic_dot(False)

        self.voice_btn.configure(text="Voice")

        self._set_busy(True)

        self.set_status("Transcribing…")

        threading.Thread(target=self._run_voice_query, daemon=True).start()



    def _assistant_hwnd(self) -> int:
        return self._toplevel_hwnd()

    def _hide_window(self) -> None:
        try:
            hwnd = self._assistant_hwnd()
            self.root.withdraw()
            user32.ShowWindow(hwnd, SW_HIDE)
            self.root.update_idletasks()
            self.root.update()
        except Exception:
            try:
                self.root.withdraw()
            except Exception:
                pass

    def _show_window(self) -> None:
        try:
            hwnd = self._assistant_hwnd()
            self.root.deiconify()
            user32.ShowWindow(hwnd, SW_SHOW)
            self.root.update_idletasks()
            self.root.update()
        except Exception:
            try:
                self.root.deiconify()
            except Exception:
                pass
        try:
            self.root.attributes("-topmost", True)
            hwnd = self._toplevel_hwnd()
            if hwnd:
                HWND_TOPMOST = -1
                user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
        except Exception:
            pass

    def _wait_until_hidden(self, hwnd: int, timeout_sec: float = 0.65) -> None:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                if not user32.IsWindowVisible(hwnd):
                    break
            except Exception:
                break
            time.sleep(0.04)
        time.sleep(self.config.capture_delay_sec)

    def _prepare_for_capture(self) -> int:
        hwnd = self._assistant_hwnd()
        self._run_on_main(self._hide_window, timeout=2.0)
        self._wait_until_hidden(hwnd)
        return hwnd

    def _restore_after_capture(self) -> None:
        self._run_on_main(self._show_window, timeout=2.0)



    def _capture_on_press(self) -> None:

        try:

            self.root.after(0, lambda: self.set_status("Screenshot…"))

            self._pending_screenshot, self._pending_screen_context = self._grab_screen_now()

        except Exception:

            self._pending_screenshot = None

            self._pending_screen_context = None



    def _finish(self, answer: str, *, parse_followup: bool = True, speak: bool = True) -> None:

        display = answer

        options: list[dict] = []

        if parse_followup:

            topic_q = " ".join(
                p for p in (self._followup_topic, self._last_user_question) if p
            )
            game_id = self.llm._resolve_game_id(topic_q)
            item_question = bool(
                game_id
                and self.config.use_game_database
                and self.llm._game_kb.has_recipe_target_match(game_id, topic_q)
            )
            if item_question:
                display, options = extract_followup_options(answer)
                display = strip_false_pick_prompt(display)
                options = []
            elif game_id and is_game_advisory_question(topic_q, game_id=game_id):
                display, options = ensure_advisory_options(answer, topic_q, game_id)
            else:
                display, options = extract_followup_options(answer)

        if speak and self.config.speak_answers:

            threading.Thread(target=lambda: self.voice.speak(display), daemon=True).start()

        def update_ui() -> None:

            if self.config.streaming:

                self._finalize_assistant_stream(display)

            else:

                self._append_assistant(display)

            self._record_chat("Assistant", display)

            if self._last_user_question:

                self._followup_topic = self._followup_topic or self._last_user_question

                self._last_assistant_brief = display[:800]

            if options:

                self._show_followup_options(options)

            self.set_status("Ready")

            self._set_busy(False)
            try:
                self.root.attributes("-topmost", True)
                hwnd = self._toplevel_hwnd()
                if hwnd:
                    user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
            except Exception:
                pass


        self.root.after(0, update_ui)



    def _finish_error(self, error: str) -> None:

        def update_ui() -> None:

            self._stream_mark = None

            self._stream_active = False

            self._append_error(error)

            self.set_status("Error")

            self.voice_btn.configure(text="Voice")

            self._set_busy(False)



        self.root.after(0, update_ui)



    def _run_voice_query(self) -> None:

        try:

            image_path = self._pending_screenshot

            ctx = self._pending_screen_context

            self._pending_screenshot = None

            self._pending_screen_context = None

            on_token = self._make_token_callback()

            def capture() -> tuple[Path, ScreenContext]:
                self.root.after(0, lambda: self.set_status("Screenshot…"))
                return self._grab_screen_for_voice()

            result = self.voice_pipeline.complete_recording(
                image_path=image_path,
                screen_context=ctx,
                chat_history=self._chat_history,
                excluded_hwnd=self._excluded_hwnd(),
                on_status=self._llm_status,
                on_token=on_token,
                capture_screen=capture,
            )

            if on_token is not None:
                flush_remaining = getattr(on_token, "flush_remaining", None)
                if flush_remaining is not None:
                    flush_remaining()

            self._last_user_question = result.question

            def append_voice_question() -> None:
                self._append_user(result.question)

            self.root.after(0, append_voice_question)
            if self.config.speak_answers:
                threading.Thread(
                    target=lambda: self.voice_pipeline.speak_answer(
                        result.answer,
                        on_status=self._llm_status,
                    ),
                    daemon=True,
                ).start()
            self._finish(result.answer, speak=False)

        except Exception as exc:

            self.root.after(0, self._show_window)

            self._finish_error(str(exc))



    def on_close(self) -> None:

        self._stop_orb_pulse()

        try:

            self.voice.shutdown()

        except Exception:

            pass

        self.root.destroy()



    def run(self) -> None:

        self.root.mainloop()


