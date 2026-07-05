import ctypes
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import requests
from PIL import ImageGrab
import tkinter as tk

try:
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    OCR_AVAILABLE = True
except Exception:
    OCR_AVAILABLE = False

try:
    import keyboard
    HOTKEYS_AVAILABLE = True
except Exception:
    HOTKEYS_AVAILABLE = False

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen3:14b"
BASE_DIR = Path(r"C:\AI-Assistant")
SCREENSHOT_DIR = BASE_DIR / "data" / "screenshots"
DEFAULT_TASK = "Кратко и по делу объясни, что видно на экране. Если есть вопросы, помоги разобраться по шагам."
OCR_LANG = "rus+eng"

WINDOW_BG = "#1b2333"
CARD_BG = "#24324a"
CARD_BG_2 = "#1f2b40"
TEXT_MAIN = "#eef4ff"
TEXT_MUTED = "#a8b7d1"
ACCENT_2 = "#8ec5ff"
BORDER = "#5f769a"

SW_HIDE = 0
SW_SHOW = 5


@dataclass
class CaptureResult:
    image_path: Path
    extracted_text: str


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


user32 = ctypes.windll.user32


def ensure_dirs() -> None:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def get_foreground_window_rect(excluded_hwnd: int | None = None) -> tuple[int, int, int, int]:
    hwnd = user32.GetForegroundWindow()
    if hwnd == 0:
        raise RuntimeError("Не удалось получить активное окно")

    if excluded_hwnd and hwnd == excluded_hwnd:
        raise RuntimeError("Активно окно ассистента, а не целевое приложение")

    rect = RECT()
    ok = user32.GetWindowRect(hwnd, ctypes.byref(rect))
    if not ok:
        raise RuntimeError("Не удалось получить координаты активного окна")

    if rect.right <= rect.left or rect.bottom <= rect.top:
        raise RuntimeError("Некорректные координаты активного окна")

    return rect.left, rect.top, rect.right, rect.bottom


def capture_foreground_window(excluded_hwnd: int | None = None, prefix: str = "window") -> Path:
    ensure_dirs()
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    image_path = SCREENSHOT_DIR / f"{prefix}-{timestamp}.png"
    left, top, right, bottom = get_foreground_window_rect(excluded_hwnd=excluded_hwnd)
    image = ImageGrab.grab(bbox=(left, top, right, bottom), all_screens=True)
    image.save(image_path)
    return image_path


def capture_screen(prefix: str = "screen") -> Path:
    ensure_dirs()
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    image_path = SCREENSHOT_DIR / f"{prefix}-{timestamp}.png"
    image = ImageGrab.grab(all_screens=True)
    image.save(image_path)
    return image_path


def extract_text_from_image(image_path: Path) -> str:
    if not OCR_AVAILABLE:
        return ""
    try:
        text = pytesseract.image_to_string(str(image_path), lang=OCR_LANG)
        return text.strip()
    except Exception as exc:
        return f"[OCR ERROR] {exc}"


def build_prompt(task: str, extracted_text: str, image_path: Path) -> str:
    parts = [
        "You are a local desktop assistant.",
        f"User task: {task}",
        f"Screenshot path: {image_path}",
        "Always answer in Russian.",
    ]
    if extracted_text:
        parts.append("Visible text from the screenshot:")
        parts.append(extracted_text)
    else:
        parts.append("No OCR text was extracted. Say that the text may be incomplete.")
    parts.append("Give a concise and useful answer. If the screenshot contains questions, explain them clearly.")
    return "\n\n".join(parts)


def ask_ollama(prompt: str) -> str:
    payload = {
        "model": DEFAULT_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    response = requests.post(OLLAMA_URL, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()
    return data.get("response", "").strip()


class HotkeyPopup:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("AI Assistant")
        self.root.geometry("760x500+980+120")
        self.root.configure(bg=WINDOW_BG)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.93)

        self.status_var = tk.StringVar(value="Нажми Ctrl+Alt+R для анализа")
        self.is_running = False
        self.last_answer = ""

        self._build_ui()

        if HOTKEYS_AVAILABLE:
            keyboard.add_hotkey("ctrl+alt+r", self.start_analysis)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        shell = tk.Frame(self.root, bg=WINDOW_BG, highlightbackground=BORDER, highlightthickness=1)
        shell.pack(fill="both", expand=True, padx=14, pady=14)

        header = tk.Frame(shell, bg=WINDOW_BG)
        header.pack(fill="x", padx=18, pady=(16, 10))

        tk.Label(
            header,
            text="AI Assistant",
            font=("Segoe UI", 26, "bold"),
            bg=WINDOW_BG,
            fg=TEXT_MAIN,
        ).pack(side="left")

        tk.Label(
            shell,
            text="Полупрозрачное окно. Анализ только по hotkey.",
            font=("Segoe UI", 10),
            bg=WINDOW_BG,
            fg=ACCENT_2,
        ).pack(anchor="w", padx=20)

        tk.Label(
            shell,
            text="Команда по умолчанию: объяснить, что на экране, и помочь разобраться.",
            font=("Segoe UI", 10),
            bg=WINDOW_BG,
            fg=TEXT_MUTED,
        ).pack(anchor="w", padx=20, pady=(6, 10))

        answer_card = tk.Frame(shell, bg=CARD_BG, highlightbackground=BORDER, highlightthickness=1)
        answer_card.pack(fill="both", expand=True, padx=18, pady=(4, 10))

        tk.Label(
            answer_card,
            text="Ответ",
            font=("Segoe UI", 10, "bold"),
            bg=CARD_BG,
            fg=TEXT_MUTED,
        ).pack(anchor="w", padx=14, pady=(12, 6))

        self.output = tk.Text(
            answer_card,
            wrap="word",
            font=("Segoe UI", 14),
            bg=CARD_BG_2,
            fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN,
            relief="flat",
            bd=0,
            padx=12,
            pady=12,
            height=12,
        )
        self.output.pack(fill="both", expand=True, padx=14, pady=(0, 14))
        self.output.insert(tk.END, "Жду горячую клавишу...\n\nCtrl+Alt+R — захватить активное окно и получить ответ.")

        footer = tk.Frame(shell, bg=WINDOW_BG)
        footer.pack(fill="x", padx=18, pady=(0, 14))

        tk.Label(
            footer,
            textvariable=self.status_var,
            font=("Segoe UI", 10),
            bg=WINDOW_BG,
            fg=TEXT_MUTED,
        ).pack(side="left")

        hotkey_text = "Ctrl+Alt+R — анализ" if HOTKEYS_AVAILABLE else "Установи keyboard для hotkey"
        tk.Label(
            footer,
            text=hotkey_text,
            font=("Segoe UI", 10),
            bg=WINDOW_BG,
            fg=ACCENT_2,
        ).pack(side="right")

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def set_output(self, text: str) -> None:
        self.output.delete("1.0", tk.END)
        self.output.insert(tk.END, text)
        self.output.see(tk.END)

    def start_analysis(self) -> None:
        if self.is_running:
            return
        self.is_running = True
        self.set_status("Захват и анализ...")
        self.set_output("Идёт анализ...")
        thread = threading.Thread(target=self._run_analysis, daemon=True)
        thread.start()

    def _run_analysis(self) -> None:
        assistant_hwnd = int(self.root.winfo_id())
        try:
            self.root.after(0, self._hide_window)
            time.sleep(0.25)

            try:
                image_path = capture_foreground_window(excluded_hwnd=assistant_hwnd)
            except Exception:
                image_path = capture_screen()

            extracted_text = extract_text_from_image(image_path)
            prompt = build_prompt(DEFAULT_TASK, extracted_text, image_path)
            answer = ask_ollama(prompt)
            self.last_answer = answer
            self.root.after(0, lambda: self._finish_success(answer, image_path, extracted_text))
        except Exception as exc:
            self.root.after(0, lambda: self._finish_error(str(exc)))

    def _hide_window(self) -> None:
        try:
            user32.ShowWindow(int(self.root.winfo_id()), SW_HIDE)
        except Exception:
            self.root.withdraw()

    def _show_window(self) -> None:
        try:
            user32.ShowWindow(int(self.root.winfo_id()), SW_SHOW)
        except Exception:
            self.root.deiconify()
        self.root.attributes("-topmost", True)
        self.root.lift()

    def _finish_success(self, answer: str, image_path: Path, extracted_text: str) -> None:
        self._show_window()
        preview = extracted_text[:500].replace("\n", " ") if extracted_text else "[OCR пустой]"
        text = f"Файл: {image_path}\n\nOCR preview:\n{preview}\n\n{answer}"
        self.set_output(text)
        self.set_status("Готово")
        self.is_running = False

    def _finish_error(self, error_text: str) -> None:
        self._show_window()
        self.set_output(f"Ошибка:\n{error_text}")
        self.set_status("Ошибка")
        self.is_running = False

    def on_close(self) -> None:
        try:
            if HOTKEYS_AVAILABLE:
                keyboard.clear_all_hotkeys()
        except Exception:
            pass
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    app = HotkeyPopup()
    app.run()


if __name__ == "__main__":
    main()
