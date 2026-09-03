"""Палітра й геометрія обличчя ROBI.

Ролі кольорів зібрані з актуальних 3D-референсів маскота. Вони вибрані
в OKLCH, а тут зберігаються як RGB, бо саме цей формат приймає pygame.
Геометрія задана у частках екрана й оптимізована для Surface Go 2 у 3:2,
але лишається адаптивною для вікон розробника.
"""

from __future__ import annotations

from dataclasses import dataclass

Color = tuple[int, int, int]


@dataclass(frozen=True, slots=True)
class Palette:
    # Блакитна лицьова панель, а не колір зовнішнього корпуса.
    face_top: Color = (121, 190, 251)
    face_bottom: Color = (77, 155, 239)
    face_edge: Color = (50, 126, 224)
    face_glow: Color = (177, 220, 255)

    eye_white: Color = (248, 252, 255)
    eye_shadow: Color = (45, 112, 191)
    pupil: Color = (13, 29, 62)
    pupil_soft: Color = (27, 58, 111)
    highlight: Color = (244, 250, 255)
    mouth: Color = (18, 55, 126)

    accent: Color = (150, 207, 255)
    error: Color = (224, 83, 76)
    offline: Color = (239, 170, 55)
    ok: Color = (71, 195, 139)

    # Діагностика й QR використовують темний текст на світлому екрані.
    hud: Color = (15, 41, 84)
    hud_muted: Color = (63, 96, 145)
    qr_ink: Color = (9, 24, 48)
    qr_paper: Color = (249, 252, 255)
    qr_shadow: Color = (38, 105, 183)


@dataclass(frozen=True, slots=True)
class Geometry:
    """Частки від ширини/висоти екрана."""

    eye_radius: float = 0.088
    eye_aspect: float = 0.92
    eye_gap: float = 0.29
    eye_y: float = 0.405
    pupil_radius: float = 0.044
    pupil_aspect: float = 1.08
    pupil_travel: float = 0.024
    mouth_y: float = 0.665
    mouth_width: float = 0.105
    mouth_height: float = 0.050
    mouth_thickness: float = 0.009


PALETTE = Palette()
GEOMETRY = Geometry()

#: Наскільки якісно згладжуються краї: 4 означає рендер у 4x і зменшення.
SUPERSAMPLE = 4
