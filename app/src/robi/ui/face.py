"""Живе процедурне обличчя ROBI.

Візуальна мова повторює маскота бренду: світло-блакитна лицьова панель і
великі глянцеві очі. **Рота немає** — його немає й у персонажа: ні в
переліку частин візуального гайда CRM, ні на 3D-референсах. Гайд прямо
називає очі «основним емоційним елементом», і на пристрої вони лишаються
єдиним, бо кінцівки статичні (`D-019`), антена без світлодіода (`D-045`),
а канал RGB знято (`D-043`).

Емоції задаються станами зі спільного словника (`mascot_state`), ключі
якого дослівно збігаються з гайдом CRM.

Усі дорогі поверхні готуються під час ``resize``. У кадрі лишаються
blit-и, кілька простих обчислень і плавне стеження за ціллю.
"""

from __future__ import annotations

import math
import random

import pygame

from ..mascot_state import (
    EYE_CLOSED,
    EYE_CRESCENT,
    EYE_NARROW,
    EYE_OPEN,
    EYE_WIDE,
    MascotState,
    look_for,
)
from .theme import GEOMETRY, PALETTE, SUPERSAMPLE, Color

BLINK_STEPS = 10


def _ellipse(size: tuple[int, int], color: tuple[int, ...]) -> pygame.Surface:
    """Згладжений еліпс через супервибірку."""
    width, height = (max(2, value) for value in size)
    big = pygame.Surface((width * SUPERSAMPLE, height * SUPERSAMPLE), pygame.SRCALPHA)
    pygame.draw.ellipse(big, color, big.get_rect())
    return pygame.transform.smoothscale(big, (width, height))


def _arc(width: int, height: int, thickness: int, color: Color, depth: float) -> pygame.Surface:
    """Дуга з круглими кінцями — щасливе око-півмісяць.

    Цією ж кривою раніше малювався рот. Рот прибрано як не належний
    персонажу, а крива лишилася: у гайді бренду `happy` і `success` — це
    саме очі-півмісяці.
    """
    pad = thickness
    big_w = (width + pad * 2) * SUPERSAMPLE
    big_h = (height + pad * 2) * SUPERSAMPLE
    surf = pygame.Surface((big_w, big_h), pygame.SRCALPHA)

    radius = max(1, thickness * SUPERSAMPLE // 2)
    x0 = pad * SUPERSAMPLE
    x1 = (pad + width) * SUPERSAMPLE
    y0 = (pad + height * 0.08) * SUPERSAMPLE
    control_y = (pad + height * (1.35 + depth * 0.38)) * SUPERSAMPLE
    steps = max(28, width // 3)
    points: list[tuple[int, int]] = []
    for i in range(steps + 1):
        t = i / steps
        x = (1.0 - t) * x0 + t * x1
        y = (1.0 - t) ** 2 * y0 + 2.0 * (1.0 - t) * t * control_y + t**2 * y0
        points.append((int(x), int(y)))

    pygame.draw.lines(surf, color, False, points, radius * 2)
    pygame.draw.circle(surf, color, points[0], radius)
    pygame.draw.circle(surf, color, points[-1], radius)
    return pygame.transform.smoothscale(surf, (width + pad * 2, height + pad * 2))


def _pupil(size: tuple[int, int]) -> pygame.Surface:
    """Глянцева зіниця з двома відблисками як на 3D-референсі."""
    width, height = size
    scale = SUPERSAMPLE
    surf = pygame.Surface((width * scale, height * scale), pygame.SRCALPHA)
    rect = surf.get_rect()
    pygame.draw.ellipse(surf, PALETTE.pupil, rect)

    soft = rect.inflate(-int(width * 0.16 * scale), -int(height * 0.16 * scale))
    soft.y -= int(height * 0.035 * scale)
    pygame.draw.ellipse(surf, PALETTE.pupil_soft, soft)

    large_r = max(2, int(width * 0.145 * scale))
    small_r = max(1, int(width * 0.057 * scale))
    pygame.draw.circle(
        surf,
        PALETTE.highlight,
        (int(width * 0.34 * scale), int(height * 0.29 * scale)),
        large_r,
    )
    pygame.draw.circle(
        surf,
        PALETTE.highlight,
        (int(width * 0.70 * scale), int(height * 0.67 * scale)),
        small_r,
    )
    return pygame.transform.smoothscale(surf, size)


def _star(size: int) -> pygame.Surface:
    """М'який чотирипроменевий відблиск для коротких реакцій."""
    big = size * SUPERSAMPLE
    surf = pygame.Surface((big, big), pygame.SRCALPHA)
    center = big // 2
    outer = big * 0.47
    inner = big * 0.13
    points = [
        (center, int(center - outer)),
        (int(center + inner), int(center - inner)),
        (int(center + outer), center),
        (int(center + inner), int(center + inner)),
        (center, int(center + outer)),
        (int(center - inner), int(center + inner)),
        (int(center - outer), center),
        (int(center - inner), int(center - inner)),
    ]
    pygame.draw.polygon(surf, PALETTE.highlight, points)
    return pygame.transform.smoothscale(surf, (size, size))


class FaceRenderer:
    """Малює ROBI та керує його мікроповедінкою."""

    def __init__(self, size: tuple[int, int], seed: int = 3) -> None:
        self._rng = random.Random(seed)

        self._gaze_target = (0.0, 0.0)
        self._gaze = (0.0, 0.0)
        self._has_face = False
        self._gesture_target = (0.0, 0.0)
        self._gesture_t = 0.0

        self._blink_t = 0.0
        self._next_blink = self._schedule_blink()
        self._blink_progress = 0.0

        self._breath = 0.0
        self._saccade = (0.0, 0.0)
        self._saccade_target = (0.0, 0.0)
        self._saccade_t = 0.0
        self._clock = 0.0

        self._state = MascotState.IDLE
        self._state_left: float | None = None
        self._reaction_kind = "idle"
        self._reaction_left = 0.0
        self._reaction_duration = 0.0
        self._reaction_strength = 0.0

        self.resize(size)

    # -- підготовка ----------------------------------------------------

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        w, h = size
        g = GEOMETRY

        self._eye_w = max(24, int(g.eye_radius * w * 2.0))
        self._eye_h = max(22, int(self._eye_w * g.eye_aspect))
        self._pupil_w = max(12, int(g.pupil_radius * w * 2.0))
        self._pupil_h = max(12, int(self._pupil_w * g.pupil_aspect))
        self._travel = g.pupil_travel * w
        self._eye_dx = g.eye_gap * w / 2.0
        self._eye_y = g.eye_y * h

        self._background = self._make_background(size)
        self._eye_frames = self._make_blink_frames()
        self._pupil = _pupil((self._pupil_w, self._pupil_h))

        self._eye_variants = self._make_eye_variants()

        self._star = _star(max(12, int(h * 0.036)))
        self._zzz_font = None

    def _make_eye_variants(self) -> dict[str, tuple[pygame.Surface, int]]:
        """Форми ока під стани бренду, готуються один раз на розмір.

        Значення — поверхня й ефективна висота: за нею вирішується, чи
        лишається місце для зіниці. У півмісяця її немає — це вже не
        око з зіницею, а вигин.
        """
        base, base_h = self._eye_frames[0]
        wide = pygame.transform.smoothscale(
            base, (int(base.get_width() * 1.16), int(base.get_height() * 1.16))
        )
        narrow = pygame.transform.smoothscale(
            base, (base.get_width(), max(4, int(base.get_height() * 0.52)))
        )
        crescent = _arc(
            self._eye_w,
            max(6, int(self._eye_h * 0.42)),
            max(4, int(self._eye_w * 0.16)),
            PALETTE.eye_white,
            0.0,
        )
        return {
            EYE_WIDE: (wide, int(base_h * 1.16)),
            EYE_NARROW: (narrow, max(2, int(base_h * 0.52))),
            EYE_CRESCENT: (crescent, 0),
            EYE_CLOSED: self._eye_frames[BLINK_STEPS - 1],
        }

    def _make_background(self, size: tuple[int, int]) -> pygame.Surface:
        """Двовимірне світло й віньєтка додають панелі м'якого об'єму."""
        w, h = size
        sample_w = max(96, w // 6)
        sample_h = max(64, h // 6)
        small = pygame.Surface((sample_w, sample_h))

        top = PALETTE.face_top
        bottom = PALETTE.face_bottom
        glow = PALETTE.face_glow
        edge = PALETTE.face_edge
        for y in range(sample_h):
            fy = y / max(1, sample_h - 1)
            vertical = fy * fy * (3.0 - 2.0 * fy)
            for x in range(sample_w):
                fx = x / max(1, sample_w - 1)
                base = [top[i] + (bottom[i] - top[i]) * vertical for i in range(3)]

                light = math.exp(-(((fx - 0.30) / 0.43) ** 2 + ((fy - 0.08) / 0.40) ** 2))
                edge_distance = min(fx, 1.0 - fx, fy, 1.0 - fy)
                vignette = max(0.0, 1.0 - edge_distance * 8.0)
                lower_glow = math.exp(-(((fx - 0.72) / 0.55) ** 2 + ((fy - 0.95) / 0.45) ** 2))

                rgb = []
                for i in range(3):
                    value = base[i]
                    value += (glow[i] - value) * light * 0.20
                    value += (glow[i] - value) * lower_glow * 0.06
                    value += (edge[i] - value) * vignette * 0.18
                    rgb.append(max(0, min(255, int(value))))
                small.set_at((x, y), rgb)

        return pygame.transform.smoothscale(small, size)

    def _make_blink_frames(self) -> list[tuple[pygame.Surface, int]]:
        pad = max(4, int(self._eye_w * 0.035))
        canvas_size = (self._eye_w + pad * 2, self._eye_h + pad * 2)
        self._eye_canvas_size = canvas_size
        frames: list[tuple[pygame.Surface, int]] = []

        for i in range(BLINK_STEPS):
            openness = 1.0 - i / (BLINK_STEPS - 1)
            openness = openness**0.72
            eye_h = max(3, int(self._eye_h * openness))
            frame = pygame.Surface(canvas_size, pygame.SRCALPHA)
            center_y = canvas_size[1] // 2

            if i == BLINK_STEPS - 1:
                thickness = max(3, int(self._eye_h * 0.045))
                y = center_y
                pygame.draw.line(
                    frame,
                    PALETTE.eye_line,
                    (pad + thickness, y),
                    (pad + self._eye_w - thickness, y),
                    thickness,
                )
                pygame.draw.circle(frame, PALETTE.eye_line, (pad + thickness, y), thickness // 2)
                pygame.draw.circle(
                    frame,
                    PALETTE.eye_line,
                    (pad + self._eye_w - thickness, y),
                    thickness // 2,
                )
            else:
                shadow = _ellipse((self._eye_w, eye_h), (*PALETTE.eye_shadow, 116))
                white = _ellipse((self._eye_w, eye_h), PALETTE.eye_white)
                top = center_y - eye_h // 2
                frame.blit(shadow, (pad, top + max(2, pad // 2)))
                frame.blit(white, (pad, top))
            frames.append((frame, eye_h))

        return frames

    # -- поведінка -----------------------------------------------------

    def _schedule_blink(self) -> float:
        return self._rng.uniform(2.6, 5.2)

    def look_at(self, x: float, y: float) -> None:
        """Ціль погляду в нормалізованих координатах -1..1."""
        self._gaze_target = (max(-1.0, min(1.0, x)), max(-1.0, min(1.0, y)))
        self._has_face = True

    def look_away(self) -> None:
        """Людина зникла, ROBI спокійно повертається у нейтраль."""
        self._gaze_target = (0.0, 0.0)
        self._has_face = False

    # -- стани бренду ---------------------------------------------------

    def set_state(self, state: MascotState) -> None:
        """Виставити стан зі спільного словника (`mascot_state`)."""
        look = look_for(state)
        self._state = state
        self._state_left = look.hold_s

    @property
    def state(self) -> MascotState:
        return self._state

    def react_greeting(self) -> None:
        self._start_reaction("greeting", duration=1.35, strength=0.72)

    def react_touch(self, x: float, y: float) -> None:
        self._gesture_target = (
            max(-1.0, min(1.0, x * 2.0 - 1.0)),
            max(-1.0, min(1.0, y * 2.0 - 1.0)),
        )
        self._gesture_t = 0.72
        self._start_reaction("happy", duration=1.25, strength=1.0)

    def react_success(self) -> None:
        self._start_reaction("success", duration=1.5, strength=1.0)

    def react_error(self) -> None:
        self._start_reaction("oops", duration=1.25, strength=0.9)

    def _start_reaction(self, kind: str, *, duration: float, strength: float) -> None:
        self._reaction_kind = kind
        self._reaction_left = duration
        self._reaction_duration = duration
        self._reaction_strength = strength
        # Спільне м'яке кліпання зшиває погляд і усмішку в одну реакцію.
        if self._blink_progress <= 0.0:
            self._blink_progress = 0.001

    def _reaction_amount(self) -> float:
        if self._reaction_left <= 0.0 or self._reaction_duration <= 0.0:
            return 0.0
        elapsed = self._reaction_duration - self._reaction_left
        attack = min(1.0, elapsed / 0.16)
        release = min(1.0, self._reaction_left / 0.42)
        # Smoothstep keeps the reaction energetic without a spring or bounce.
        envelope = min(attack, release)
        envelope = envelope * envelope * (3.0 - 2.0 * envelope)
        return envelope * self._reaction_strength

    def update(self, dt: float) -> None:
        self._clock += dt
        self._reaction_left = max(0.0, self._reaction_left - dt)

        # Тимчасові стани самі повертаються в idle; стани без hold_s
        # лишаються, поки їх не змінять — «помилка», яка зникла сама,
        # людину біля стійки лише спантеличить.
        if self._state_left is not None:
            self._state_left -= dt
            if self._state_left <= 0.0:
                self._state = MascotState.IDLE
                self._state_left = None
        self._gesture_t = max(0.0, self._gesture_t - dt)

        target = self._gesture_target if self._gesture_t > 0.0 else self._gaze_target
        gaze_k = 1.0 - math.exp(-dt * 5.2)
        gx, gy = self._gaze
        self._gaze = (gx + (target[0] - gx) * gaze_k, gy + (target[1] - gy) * gaze_k)

        self._blink_t += dt
        if self._blink_progress > 0.0:
            self._blink_progress += dt / 0.12
            if self._blink_progress >= 2.0:
                self._blink_progress = 0.0
                self._blink_t = 0.0
                self._next_blink = self._schedule_blink()
        elif self._blink_t >= self._next_blink:
            self._blink_progress = 0.001

        self._breath = math.sin(self._clock * 1.05) * 0.0032

        # Idle gaze is deliberately tiny and eased. Sudden independent eye
        # jumps read as nervous or creepy on a large physical display.
        self._saccade_t -= dt
        if self._saccade_t <= 0.0:
            self._saccade_t = self._rng.uniform(1.8, 4.0)
            if self._has_face:
                self._saccade_target = (0.0, 0.0)
            else:
                self._saccade_target = (
                    self._rng.uniform(-0.12, 0.12),
                    self._rng.uniform(-0.07, 0.07),
                )
        idle_k = 1.0 - math.exp(-dt * 1.8)
        sx, sy = self._saccade
        tx, ty = self._saccade_target
        self._saccade = (sx + (tx - sx) * idle_k, sy + (ty - sy) * idle_k)

    def _current_eye(self) -> tuple[pygame.Surface, int]:
        """Форма ока за станом. Кліпає лише відкрите — інші форми статичні."""
        look = look_for(self._state)
        if look.eye == EYE_OPEN:
            return self._blink_frame()
        return self._eye_variants[look.eye]

    def _blink_frame(self) -> tuple[pygame.Surface, int]:
        if self._blink_progress <= 0.0:
            return self._eye_frames[0]
        closed = math.sin(min(2.0, self._blink_progress) * math.pi / 2.0)
        idx = min(BLINK_STEPS - 1, int(closed * (BLINK_STEPS - 1)))
        return self._eye_frames[idx]

    # -- рендер --------------------------------------------------------

    def draw(self, target: pygame.Surface) -> None:
        w, h = self.size
        target.blit(self._background, (0, 0))

        reaction = self._reaction_amount()
        lift = -reaction * h * 0.010
        cy = self._eye_y + self._breath * h + lift
        look = look_for(self._state)
        eye, eye_h = self._current_eye()
        canvas_w, canvas_h = eye.get_width(), eye.get_height()

        gx, gy = self._gaze
        sx, sy = self._saccade
        # Стан може вести погляд сам: «дивляться вгору» в thinking,
        # «вбік» у empty. Стеження за людиною лишається тільки в idle,
        # інакше емоція боролася б із камерою за напрямок очей.
        if not look.follows_face:
            gx, gy = look.gaze
            sx = sy = 0.0
        for sign in (-1, 1):
            cx = w / 2.0 + sign * self._eye_dx
            target.blit(eye, (int(cx - canvas_w / 2), int(cy - canvas_h / 2)))

            if eye_h > self._pupil_h * 0.48:
                px = cx + (gx + sx) * self._travel
                py = cy + (gy + sy) * self._travel * 0.62
                target.set_clip(
                    pygame.Rect(
                        int(cx - self._eye_w / 2),
                        int(cy - eye_h / 2),
                        self._eye_w,
                        eye_h,
                    )
                )
                target.blit(
                    self._pupil,
                    (int(px - self._pupil_w / 2), int(py - self._pupil_h / 2)),
                )
                target.set_clip(None)

        self._draw_expression(target, reaction, lift)

    def _draw_expression(self, target: pygame.Surface, reaction: float, lift: float) -> None:
        """Понад очима лишилися тільки іскри й «Zzz».

        Рум'янець прив'язувався до положення рота, якого більше немає, і
        разом із ним пішов: у гайді бренду його теж немає.
        """
        w, h = self.size
        look = look_for(self._state)

        if look.zzz:
            self._draw_zzz(target, lift)

        # Іскри світяться і від стану (happy/success/achievement), і від
        # короткої реакції на дотик — беремо сильніше з двох.
        amount = max(reaction, 0.85 if look.sparkle else 0.0)
        if amount <= 0.03:
            return

        self._star.set_alpha(min(230, int(amount * 230)))
        for x, y in (
            (int(w * 0.225), int(h * 0.255 + lift)),
            (int(w * 0.755), int(h * 0.315 + lift)),
        ):
            target.blit(self._star, (x, y))

    def _draw_zzz(self, target: pygame.Surface, lift: float) -> None:
        """Сон у гайді показується літерами, а не заплющеними очима."""
        w, h = self.size
        if self._zzz_font is None:
            self._zzz_font = pygame.font.Font(None, max(20, int(h * 0.085)))
        for i in range(3):
            phase = (self._clock * 0.55 + i * 0.33) % 1.0
            alpha = int(200 * math.sin(phase * math.pi))
            glyph = self._zzz_font.render("z", True, PALETTE.eye_line)
            glyph.set_alpha(max(0, alpha))
            scale = 0.7 + 0.5 * phase
            glyph = pygame.transform.smoothscale(
                glyph, (max(1, int(glyph.get_width() * scale)), max(1, int(glyph.get_height() * scale)))
            )
            x = int(w * 0.62 + i * w * 0.035)
            y = int(self._eye_y - h * 0.10 - phase * h * 0.09 + lift)
            target.blit(glyph, (x, y))
