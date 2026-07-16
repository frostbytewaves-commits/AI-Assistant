"""Apple Intelligence–style soft mesh orb (PIL) for the overlay header."""

from __future__ import annotations

import math
from typing import Literal

from PIL import Image, ImageDraw, ImageFilter, ImageTk

OrbMode = Literal["idle", "listening", "busy"]

# Soft Apple Intelligence palette (approx.)
_CYAN = (110, 230, 255)
_INDIGO = (88, 70, 220)
_VIOLET = (140, 90, 255)
_PINK = (255, 140, 210)
_MAGENTA = (255, 100, 170)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _blob(
    size: int,
    color: tuple[int, int, int],
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    blur: float,
    alpha: int = 220,
) -> Image.Image:
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    draw.ellipse(
        [cx - rx, cy - ry, cx + rx, cy + ry],
        fill=(color[0], color[1], color[2], max(0, min(255, alpha))),
    )
    if blur > 0:
        layer = layer.filter(ImageFilter.GaussianBlur(radius=blur))
    return layer


def _capsule_mask(size: int, pad: float, blur: float) -> Image.Image:
    """Vertical soft capsule alpha mask (taller than wide)."""
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    # Apple Intelligence silhouette: upright pill
    left = pad * 1.15
    right = size - pad * 1.15
    top = pad * 0.45
    bottom = size - pad * 0.45
    radius = (right - left) / 2
    draw.rounded_rectangle(
        [left, top, right, bottom],
        radius=radius,
        fill=255,
    )
    if blur > 0:
        mask = mask.filter(ImageFilter.GaussianBlur(radius=blur))
    return mask


def render_orb_rgba(
    size: int,
    *,
    phase: float,
    breath: float,
    mode: OrbMode = "idle",
    bg_hex: str = "#1c1c1e",
) -> Image.Image:
    """Render one frame of the mesh orb onto a solid background."""
    breath = max(0.0, min(1.0, breath))
    wobble = 0.10 * math.sin(phase)
    wobble2 = 0.08 * math.cos(phase * 0.9)

    scale = 0.90 + 0.12 * breath
    mid = size / 2
    span_x = size * 0.34 * scale
    span_y = size * 0.46 * scale

    bg = _hex_to_rgb(bg_hex)
    canvas = Image.new("RGBA", (size, size), (*bg, 255))
    mesh = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    if mode == "listening":
        top, mid_c, bot = (255, 170, 210), _MAGENTA, (255, 95, 130)
        glow_boost = 1.15
    elif mode == "busy":
        top, mid_c, bot = (140, 245, 255), _INDIGO, _VIOLET
        glow_boost = 1.25
    else:
        top, mid_c, bot = (120, 235, 255), _INDIGO, (255, 150, 215)
        glow_boost = 1.05

    # Soft outer halo
    mesh = Image.alpha_composite(
        mesh,
        _blob(
            size,
            mid_c,
            mid + wobble * 3,
            mid,
            span_x * 1.25,
            span_y * 1.15,
            blur=size * 0.16,
            alpha=int(100 * glow_boost),
        ),
    )
    # Cyan / turquoise — top
    mesh = Image.alpha_composite(
        mesh,
        _blob(
            size,
            top,
            mid - span_x * 0.08 + wobble * 8,
            mid - span_y * 0.42 + wobble2 * 6,
            span_x * 0.85,
            span_y * 0.55,
            blur=size * 0.11,
            alpha=int(235 * glow_boost),
        ),
    )
    # Indigo / violet — center
    mesh = Image.alpha_composite(
        mesh,
        _blob(
            size,
            mid_c,
            mid + wobble2 * 6,
            mid + wobble * 4,
            span_x * 0.95,
            span_y * 0.70,
            blur=size * 0.13,
            alpha=int(240 * glow_boost),
        ),
    )
    # Pink / magenta — bottom
    mesh = Image.alpha_composite(
        mesh,
        _blob(
            size,
            bot,
            mid + span_x * 0.10 - wobble * 7,
            mid + span_y * 0.40 - wobble2 * 5,
            span_x * 0.90,
            span_y * 0.55,
            blur=size * 0.12,
            alpha=int(220 * glow_boost),
        ),
    )
    # Glass highlight near top
    mesh = Image.alpha_composite(
        mesh,
        _blob(
            size,
            (255, 255, 255),
            mid - span_x * 0.05,
            mid - span_y * 0.35,
            span_x * 0.35,
            span_y * 0.18,
            blur=size * 0.07,
            alpha=int(75 + 45 * breath),
        ),
    )

    pad = size * (0.16 - 0.025 * breath)
    mask = _capsule_mask(size, pad=pad, blur=size * 0.055)
    mesh.putalpha(mask)

    return Image.alpha_composite(canvas, mesh)


class OrbAnimator:
    """Keeps PhotoImage refs alive and paints onto a Tk Canvas."""

    def __init__(self, canvas, *, size: int = 56, bg_hex: str = "#1c1c1e") -> None:
        self.canvas = canvas
        self.size = size
        self.bg_hex = bg_hex
        self.mode: OrbMode = "idle"
        self.phase = 0.0
        self._photo: ImageTk.PhotoImage | None = None
        # Placeholder transparent pixel until first paint
        blank = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        self._photo = ImageTk.PhotoImage(blank)
        self._item = canvas.create_image(size // 2, size // 2, image=self._photo)
        self.paint(breath=0.5)

    def set_mode(self, mode: OrbMode) -> None:
        if mode not in {"idle", "listening", "busy"}:
            mode = "idle"
        self.mode = mode  # type: ignore[assignment]

    def paint(self, breath: float) -> None:
        img = render_orb_rgba(
            self.size,
            phase=self.phase,
            breath=breath,
            mode=self.mode,
            bg_hex=self.bg_hex,
        )
        photo = ImageTk.PhotoImage(img)
        self._photo = photo  # prevent GC
        self.canvas.itemconfig(self._item, image=photo)

    def tick(self, *, speed: float, base: float, amp: float) -> float:
        self.phase += speed
        breath = base + amp * (0.5 + 0.5 * math.sin(self.phase))
        # Slow secondary swirl
        self.phase  # already advanced
        self.paint(breath)
        return breath
