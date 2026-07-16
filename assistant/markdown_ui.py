"""Простой Markdown-рендер для Tkinter Text (мягкий Apple-like dark)."""

import re
import tkinter as tk

# Soft dark — closer to macOS / Apple HIG than ChatGPT green
BG = "#1c1c1e"
SURFACE = "#2c2c2e"
SURFACE_HOVER = "#3a3a3c"
TEXT = "#f5f5f7"
TEXT_MUTED = "#98989d"
USER_BG = "#2c2c2e"
ASSISTANT_BG = BG
ACCENT = "#0a84ff"  # system blue
BORDER = "#38383a"
CODE_BG = "#000000"

# AI orb states
ORB_IDLE = "#5e5e62"
ORB_IDLE_GLOW = "#3a3a3c"
ORB_LISTEN = "#ff453a"
ORB_LISTEN_GLOW = "#ff6961"
ORB_BUSY = "#64d2ff"
ORB_BUSY_GLOW = "#0a84ff"


def configure_chat_tags(text: tk.Text) -> None:
    base_margin = 28
    text.tag_configure(
        "body",
        foreground=TEXT,
        background=ASSISTANT_BG,
        font=("Segoe UI", 11),
        lmargin1=base_margin,
        lmargin2=base_margin,
        rmargin=base_margin,
        spacing1=2,
        spacing3=8,
    )
    text.tag_configure(
        "user_body",
        foreground=TEXT,
        background=USER_BG,
        font=("Segoe UI", 11),
        lmargin1=base_margin,
        lmargin2=base_margin,
        rmargin=base_margin,
        spacing1=8,
        spacing3=8,
    )
    text.tag_configure("user_label", foreground=TEXT_MUTED, font=("Segoe UI", 9, "bold"), lmargin1=base_margin)
    text.tag_configure("assistant_label", foreground=ACCENT, font=("Segoe UI", 9, "bold"), lmargin1=base_margin)
    text.tag_configure("h1", foreground=TEXT, font=("Segoe UI", 15, "bold"), lmargin1=base_margin, lmargin2=base_margin, spacing1=10, spacing3=6)
    text.tag_configure("h2", foreground=TEXT, font=("Segoe UI", 13, "bold"), lmargin1=base_margin, lmargin2=base_margin, spacing1=8, spacing3=4)
    text.tag_configure("h3", foreground=TEXT, font=("Segoe UI", 12, "bold"), lmargin1=base_margin, lmargin2=base_margin, spacing1=6, spacing3=4)
    text.tag_configure("bold", font=("Segoe UI", 11, "bold"))
    text.tag_configure("code", foreground="#ff9f0a", background=CODE_BG, font=("Cascadia Mono", 10))
    text.tag_configure("bullet", foreground=TEXT, font=("Segoe UI", 11), lmargin1=base_margin + 18, lmargin2=base_margin + 34, rmargin=base_margin, spacing3=5)
    text.tag_configure("muted", foreground=TEXT_MUTED, font=("Segoe UI", 10))
    text.tag_configure("error", foreground="#ff453a", font=("Segoe UI", 11))


def _insert_inline(text: tk.Text, line: str, base_tag: str) -> None:
    pattern = re.compile(r"(\*\*.+?\*\*|`[^`]+`|\*[^*]+?\*)")
    pos = 0
    for match in pattern.finditer(line):
        if match.start() > pos:
            text.insert(tk.END, line[pos : match.start()], base_tag)
        chunk = match.group(0)
        if chunk.startswith("**") and chunk.endswith("**"):
            text.insert(tk.END, chunk[2:-2], ("bold", base_tag))
        elif chunk.startswith("`") and chunk.endswith("`"):
            text.insert(tk.END, chunk[1:-1], "code")
        elif chunk.startswith("*") and chunk.endswith("*"):
            text.insert(tk.END, chunk[1:-1], ("bold", base_tag))
        else:
            text.insert(tk.END, chunk, base_tag)
        pos = match.end()
    if pos < len(line):
        text.insert(tk.END, line[pos:], base_tag)


def render_markdown_block(text: tk.Text, content: str, base_tag: str = "body") -> None:
    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            text.insert(tk.END, "\n")
            continue
        if line.startswith("### "):
            text.insert(tk.END, line[4:] + "\n", "h3")
        elif line.startswith("## "):
            text.insert(tk.END, line[3:] + "\n", "h2")
        elif line.startswith("# "):
            text.insert(tk.END, line[2:] + "\n", "h1")
        elif line.startswith("- ") or line.startswith("* "):
            text.insert(tk.END, "• ", "bullet")
            _insert_inline(text, line[2:], "bullet")
            text.insert(tk.END, "\n")
        elif re.match(r"^\d+\.\s", line):
            text.insert(tk.END, line + "\n", "bullet")
        else:
            _insert_inline(text, line, base_tag)
            text.insert(tk.END, "\n")


def append_user_message(text: tk.Text, message: str) -> None:
    text.insert(tk.END, "You\n", "user_label")
    render_markdown_block(text, message, "user_body")
    text.insert(tk.END, "\n")


def append_assistant_message(text: tk.Text, message: str) -> None:
    text.insert(tk.END, "Assistant\n", "assistant_label")
    render_markdown_block(text, message, "body")
    text.insert(tk.END, "\n")


def begin_assistant_stream(text: tk.Text) -> str:
    text.insert(tk.END, "Assistant\n", "assistant_label")
    return text.index("insert")


def append_assistant_stream_chunk(text: tk.Text, chunk: str) -> None:
    text.insert(tk.END, chunk, "body")
    text.see(tk.END)


def finalize_assistant_stream(text: tk.Text, start_mark: str, full_content: str) -> None:
    text.delete(start_mark, tk.END)
    render_markdown_block(text, full_content, "body")
    text.insert(tk.END, "\n")
    text.see(tk.END)


def clear_chat(text: tk.Text) -> None:
    text.delete("1.0", tk.END)


def append_error(text: tk.Text, message: str) -> None:
    text.insert(tk.END, message + "\n", "error")
