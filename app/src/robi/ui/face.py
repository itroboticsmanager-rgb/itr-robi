"""Рендерер обличчя.

Оптимізація тут одна, але важлива: усе, що не змінюється між кадрами,
малюється **один раз** у супервибірці 4x і зменшується до цільового
розміру. У кадрі лишаються самі blit-и. Саме тому обличчя згладжене й
водночас дешеве — це те, що робить бенчмарк на Pi чесним.

Кадри блимання прораховані дискретними кроками, тож блимання не
викликає масштабування в реальному часі.
"""

from __future__ import annotations

import math
import random

import pygame

from .theme import GEOMETRY, PALETTE, SUPERSAMPLE, Color

BLINK_STEPS = 9


def _circle(radius: int, color: Color) -> pygame.Surface:
    """Згладжене коло через супервибірку."""
    big = radius * 2 * SUPERSAMPLE
    surf = pygame.Surface((big, big), pygame.SRCALPHA)
    pygame.draw.circle(surf, color, (big // 2, big // 2), big // 2)
    return pygame.transform.smoothscale(surf, (radius * 2, radius * 2))


def _smile(width: int, height: int, thickness: int, color: Color) -> pygame.Surface:
    """Дуга усмішки. Малюється точками, щоб кінці лишалися круглими."""
    big_w = width * SUPERSAMPLE
    big_h = (height + thickness) * SUPERSAMPLE
    surf = pygame.Surface((big_w, big_h), pygame.SRCALPHA)
    r = max(1, thickness * SUPERSAMPLE // 2)
    steps = max(24, big_w // 4)
    for i in range(steps + 1):
        t = i / steps
        x = int(t * (big_w - 2 * r)) + r
        y = int(math.sin(t * math.pi) * (big_h - 2 * r)) + r
        pygame.draw.circle(surf, color, (x, y), r)
    return pygame.transform.smoothscale(surf, (width, height + thickness))


class FaceRenderer:
    """Малює обличчя ROBI та керує його мікроповедінкою."""

    def __init__(self, size: tuple[int, int], seed: int = 3) -> None:
        self._rng = random.Random(seed)

        self._gaze_target = (0.0, 0.0)
        self._gaze = (0.0, 0.0)
        self._has_face = False

        self._blink_t = 0.0
        self._next_blink = self._schedule_blink()
        self._blink_progress = 0.0

        self._breath = 0.0
        self._saccade = (0.0, 0.0)
        self._saccade_t = 0.0
        self._clock = 0.0

        self.resize(size)

    # -- підготовка --------------------------------------------------------

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        w, h = size
        g = GEOMETRY

        self._eye_r = max(8, int(g.eye_radius * w))
        self._pupil_r = max(4, int(g.pupil_radius * w))
        self._hl_r = max(2, int(g.highlight_radius * w))
        self._travel = g.pupil_travel * w
        self._eye_dx = g.eye_gap * w / 2
        self._eye_y = g.eye_y * h

        self._background = self._make_background(size)
        self._eye_frames = self._make_blink_frames()
        self._pupil = _circle(self._pupil_r, PALETTE.pupil)
        self._highlight = _circle(self._hl_r, PALETTE.eye_white)

        mw = int(g.mouth_width * w)
        mh = int(g.mouth_height * h)
        mt = max(3, int(g.mouth_thickness * w))
        self._mouth = _smile(mw, mh, mt, PALETTE.mouth)
        self._mouth_x = w // 2 - mw // 2
        self._mouth_y = int(g.mouth_y * h)

    def _make_background(self, size: tuple[int, int]) -> pygame.Surface:
        """Вертикальний градієнт обличчя. Рахується один раз на розмір."""
        w, h = size
        surf = pygame.Surface(size)
        top, bottom = PALETTE.face_top, PALETTE.face_bottom
        for y in range(h):
            t = y / max(1, h - 1)
            surf.fill(
                (
                    int(top[0] + (bottom[0] - top[0]) * t),
                    int(top[1] + (bottom[1] - top[1]) * t),
                    int(top[2] + (bottom[2] - top[2]) * t),
                ),
                pygame.Rect(0, y, w, 1),
            )
        return surf

    def _make_blink_frames(self) -> list[pygame.Surface]:
        """Дискретні кроки блимання, щоб не масштабувати в кадрі."""
        full = _circle(self._eye_r, PALETTE.eye_white)
        frames = []
        for i in range(BLINK_STEPS):
            openness = 1.0 - i / (BLINK_STEPS - 1)
            height = max(2, int(self._eye_r * 2 * openness))
            frames.append(pygame.transform.smoothscale(full, (self._eye_r * 2, height)))
        return frames

    # -- поведінка ---------------------------------------------------------

    def _schedule_blink(self) -> float:
        return self._rng.uniform(2.5, 6.0)

    def look_at(self, x: float, y: float) -> None:
        """Ціль погляду в нормалізованих координатах -1..1."""
        self._gaze_target = (max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y)))
        self._has_face = True

    def look_away(self) -> None:
        """Обличчя зникло з кадру — плавне повернення в нейтраль."""
        self._gaze_target = (0.0, 0.0)
        self._has_face = False

    def update(self, dt: float) -> None:
        self._clock += dt

        # Погляд наздоганяє ціль експоненційно — різких стрибків очей не буває.
        k = 1.0 - math.exp(-dt * 6.0)
        gx, gy = self._gaze
        tx, ty = self._gaze_target
        self._gaze = (gx + (tx - gx) * k, gy + (ty - gy) * k)

        self._blink_t += dt
        if self._blink_progress > 0.0:
            self._blink_progress += dt / 0.16
            if self._blink_progress >= 2.0:
                self._blink_progress = 0.0
                self._blink_t = 0.0
                self._next_blink = self._schedule_blink()
        elif self._blink_t >= self._next_blink:
            self._blink_progress = 0.001

        # Дихання: ледь помітне вертикальне коливання всієї групи.
        self._breath = math.sin(self._clock * 1.1) * 0.004

        # Саккади лише коли ROBI нікого не бачить — інакше він дивиться на людину.
        self._saccade_t -= dt
        if self._saccade_t <= 0.0:
            self._saccade_t = self._rng.uniform(0.8, 2.4)
            if self._has_face:
                self._saccade = (0.0, 0.0)
            else:
                self._saccade = (
                    self._rng.uniform(-0.25, 0.25),
                    self._rng.uniform(-0.15, 0.15),
                )

    def _blink_frame(self) -> pygame.Surface:
        if self._blink_progress <= 0.0:
            return self._eye_frames[0]
        # 0..1 повіка закривається, 1..2 відкривається назад.
        p = self._blink_progress
        closed = p if p <= 1.0 else 2.0 - p
        idx = min(BLINK_STEPS - 1, int(closed * (BLINK_STEPS - 1)))
        return self._eye_frames[idx]

    # -- рендер ------------------------------------------------------------

    def draw(self, target: pygame.Surface) -> None:
        w, h = self.size
        target.blit(self._background, (0, 0))

        eye = self._blink_frame()
        eye_h = eye.get_height()
        gx, gy = self._gaze
        sx, sy = self._saccade
        cy = self._eye_y + self._breath * h

        for sign in (-1, 1):
            cx = w / 2 + sign * self._eye_dx
            target.blit(eye, (int(cx - self._eye_r), int(cy - eye_h / 2)))

            # Зіниця ховається разом із повікою — інакше вона пливе по білку.
            if eye_h > self._pupil_r:
                px = cx + (gx + sx) * self._travel
                py = cy + (gy + sy) * self._travel * 0.6
                target.set_clip(
                    pygame.Rect(
                        int(cx - self._eye_r),
                        int(cy - eye_h / 2),
                        self._eye_r * 2,
                        eye_h,
                    )
                )
                target.blit(self._pupil, (int(px - self._pupil_r), int(py - self._pupil_r)))
                target.blit(
                    self._highlight,
                    (int(px - self._pupil_r * 0.35), int(py - self._pupil_r * 0.75)),
                )
                target.set_clip(None)

        target.blit(self._mouth, (self._mouth_x, int(self._mouth_y + self._breath * h)))
