"""Палітра й геометрія обличчя.

Кольори зняті з референсів у `assets/references/`. Геометрія задана в
частках від розміру екрана, щоб обличчя лишалося собою і на 800x480,
і на 1280x720 — рішення про дисплей ще відкрите (D-021).
"""

from __future__ import annotations

from dataclasses import dataclass

Color = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class Palette:
    face_top: Color = (74, 143, 247)
    face_bottom: Color = (47, 111, 224)
    eye_white: Color = (255, 255, 255)
    pupil: Color = (16, 31, 53)
    mouth: Color = (16, 31, 53)
    accent: Color = (143, 190, 250)
    error: Color = (232, 92, 76)
    offline: Color = (247, 181, 74)
    ok: Color = (108, 214, 152)
    hud: Color = (233, 241, 255)


@dataclass(frozen=True, slots=True)
class Geometry:
    """Частки від ширини/висоти екрана."""

    eye_radius: float = 0.105
    eye_gap: float = 0.30
    eye_y: float = 0.42
    pupil_radius: float = 0.058
    pupil_travel: float = 0.030
    highlight_radius: float = 0.019
    mouth_y: float = 0.70
    mouth_width: float = 0.17
    mouth_height: float = 0.085
    mouth_thickness: float = 0.020


PALETTE = Palette()
GEOMETRY = Geometry()

#: Наскільки якісно згладжуються краї: 4 означає рендер у 4x і зменшення.
SUPERSAMPLE = 4
