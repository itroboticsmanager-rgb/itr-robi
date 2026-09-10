"""Живий процедурний персонаж ROBI.

ROBI не є фоном із двома очима. Рендер збирає канонічну голову з наданих
3D-референсів: майже квадратну синю оболонку, вуха, антену, світлу
блакитну панель, глянцеві очі та маленьку темно-синю усмішку. Компактна
вітрина використовує ті самі пропорції та лише кадрує нижню частину.

Емоції задаються станами зі спільного словника (`mascot_state`), ключі
якого дослівно збігаються з гайдом CRM.

Усі градієнти, тіні та форми готуються під час ``resize``. У кадрі
лишаються blit-и, кілька простих обчислень і плавне стеження за ціллю.
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
from .theme import PALETTE, SUPERSAMPLE, Color
from .typography import ui_font

BLINK_STEPS = 10


def _rounded_gradient(
    size: tuple[int, int],
    top: Color,
    bottom: Color,
    radius: int,
) -> pygame.Surface:
    """Cached-at-resize vertical gradient clipped to a rounded rectangle."""
    width, height = (max(2, int(value)) for value in size)
    strip = pygame.Surface((2, height), pygame.SRCALPHA)
    for y in range(height):
        t = y / max(1, height - 1)
        t = t * t * (3.0 - 2.0 * t)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        pygame.draw.line(strip, color, (0, y), (1, y))
    gradient = pygame.transform.smoothscale(strip, (width, height))
    mask = pygame.Surface((width, height), pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    gradient.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
    return gradient


def _curve(
    width: int,
    height: int,
    thickness: int,
    color: Color,
    *,
    smile: bool,
) -> pygame.Surface:
    """Soft quadratic expression line for a smile or a frown."""
    scale = SUPERSAMPLE
    pad = thickness * 2
    surf = pygame.Surface(
        ((width + pad * 2) * scale, (height + pad * 2) * scale),
        pygame.SRCALPHA,
    )
    left = (pad * scale, (pad + (height * 0.18 if smile else height * 0.82)) * scale)
    right = ((pad + width) * scale, left[1])
    control_y = (pad + (height * 0.92 if smile else height * 0.08)) * scale
    points: list[tuple[int, int]] = []
    for index in range(33):
        t = index / 32
        x = (1.0 - t) * left[0] + t * right[0]
        y = (1.0 - t) ** 2 * left[1] + 2 * (1.0 - t) * t * control_y + t**2 * right[1]
        points.append((int(x), int(y)))
    line_width = max(2, thickness * scale)
    pygame.draw.lines(surf, color, False, points, line_width)
    radius = line_width // 2
    pygame.draw.circle(surf, color, points[0], radius)
    pygame.draw.circle(surf, color, points[-1], radius)
    return pygame.transform.smoothscale(
        surf,
        (width + pad * 2, height + pad * 2),
    )


def _ellipse(size: tuple[int, int], color: tuple[int, ...]) -> pygame.Surface:
    """Згладжений еліпс через супервибірку."""
    width, height = (max(2, value) for value in size)
    big = pygame.Surface((width * SUPERSAMPLE, height * SUPERSAMPLE), pygame.SRCALPHA)
    pygame.draw.ellipse(big, color, big.get_rect())
    return pygame.transform.smoothscale(big, (width, height))


def _arc(width: int, height: int, thickness: int, color: Color, depth: float) -> pygame.Surface:
    """Дуга з круглими кінцями для щасливого ока-півмісяця."""
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

    def __init__(
        self,
        size: tuple[int, int],
        seed: int = 3,
        *,
        compact: bool = False,
    ) -> None:
        self._rng = random.Random(seed)
        self.compact = compact

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
        self._state_clock = 0.0

        self._state = MascotState.IDLE
        self._state_left: float | None = None
        #: Підказка про жест. Ховається, щойно ROBI розгорнули: далі вона
        #: вже нічого не пояснює, а лише займає місце на обличчі.
        self.show_handle = True
        self._reaction_kind = "idle"
        self._reaction_left = 0.0
        self._reaction_duration = 0.0
        self._reaction_strength = 0.0

        self.resize(size)

    # -- підготовка ----------------------------------------------------

    def resize(self, size: tuple[int, int]) -> None:
        self.size = size
        w, h = size
        # One aspect ratio is used everywhere. Compact mode gets a taller
        # logical canvas and is cropped by Showcase, never stretched to fit
        # its shallow strip.
        body_aspect = 1.23
        max_body_h = h * (0.75 if self.compact else 0.60)
        max_body_w = w * (0.82 if self.compact else 0.64)
        body_h = int(min(max_body_h, max_body_w / body_aspect))
        body_w = int(body_h * body_aspect)
        body_y = int(h * (0.235 if self.compact else 0.26))
        self._robot_rect = pygame.Rect(
            w // 2 - body_w // 2,
            body_y,
            body_w,
            body_h,
        )
        inset_x = int(body_w * 0.115)
        self._display_rect = pygame.Rect(
            self._robot_rect.left + inset_x,
            self._robot_rect.top + int(body_h * 0.22),
            body_w - inset_x * 2,
            int(body_h * 0.55),
        )

        display = self._display_rect
        self._eye_w = max(20, int(min(display.width * 0.265, display.height * 0.66)))
        self._eye_h = max(18, int(self._eye_w * 0.92))
        self._pupil_w = max(10, int(self._eye_w * 0.56))
        self._pupil_h = max(10, int(self._pupil_w * 1.08))
        self._travel = display.width * 0.028
        self._eye_dx = display.width * 0.205
        self._eye_y = display.top + display.height * 0.39
        self._mouth_y = display.top + display.height * 0.78

        self._background = self._make_background(size)
        self._shell = self._make_shell(size)
        self._eye_frames = self._make_blink_frames()
        self._pupil = _pupil((self._pupil_w, self._pupil_h))

        self._eye_variants = self._make_eye_variants()
        mouth_w = max(20, int(display.width * 0.15))
        mouth_h = max(8, int(display.height * 0.15))
        mouth_line = max(2, int(display.height * 0.035))
        self._mouth_variants = {
            "smile": _curve(mouth_w, mouth_h, mouth_line, PALETTE.eye_line, smile=True),
            "happy": _curve(
                int(mouth_w * 1.35),
                int(mouth_h * 1.15),
                mouth_line,
                PALETTE.eye_line,
                smile=True,
            ),
            "frown": _curve(mouth_w, mouth_h, mouth_line, PALETTE.eye_line, smile=False),
        }
        flat = pygame.Surface((mouth_w, mouth_h + mouth_line * 2), pygame.SRCALPHA)
        pygame.draw.line(
            flat,
            PALETTE.eye_line,
            (mouth_line, flat.get_height() // 2),
            (flat.get_width() - mouth_line, flat.get_height() // 2),
            mouth_line,
        )
        o_size = max(8, int(mouth_h * 0.92))
        surprised = pygame.Surface((o_size + mouth_line * 2, o_size + mouth_line * 2), pygame.SRCALPHA)
        pygame.draw.ellipse(
            surprised,
            PALETTE.eye_line,
            surprised.get_rect().inflate(-mouth_line, -mouth_line),
            width=mouth_line,
        )
        self._mouth_variants["flat"] = flat
        self._mouth_variants["o"] = surprised

        self._star = _star(max(12, int(h * 0.036)))
        cheek_size = (max(8, int(display.width * 0.09)), max(4, int(display.height * 0.07)))
        self._cheek = _ellipse(cheek_size, (*PALETTE.cheek, 52))
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
            PALETTE.eye_line,
            0.0,
        )
        return {
            EYE_WIDE: (wide, int(base_h * 1.16)),
            EYE_NARROW: (narrow, max(2, int(base_h * 0.52))),
            EYE_CRESCENT: (crescent, 0),
            EYE_CLOSED: self._eye_frames[BLINK_STEPS - 1],
        }

    def _make_background(self, size: tuple[int, int]) -> pygame.Surface:
        """Soft reception-light scene behind the full character."""
        w, h = size
        if self.compact:
            return pygame.Surface(size, pygame.SRCALPHA)

        sample_w = max(96, w // 6)
        sample_h = max(64, h // 6)
        small = pygame.Surface((sample_w, sample_h))

        top = PALETTE.scene_top
        bottom = PALETTE.scene_bottom
        for y in range(sample_h):
            fy = y / max(1, sample_h - 1)
            vertical = fy * fy * (3.0 - 2.0 * fy)
            for x in range(sample_w):
                fx = x / max(1, sample_w - 1)
                base = [top[i] + (bottom[i] - top[i]) * vertical for i in range(3)]
                warm_light = math.exp(
                    -(((fx - 0.22) / 0.34) ** 2 + ((fy - 0.12) / 0.32) ** 2)
                )
                blue_pool = math.exp(
                    -(((fx - 0.78) / 0.42) ** 2 + ((fy - 0.78) / 0.42) ** 2)
                )
                rgb = []
                for i in range(3):
                    value = base[i]
                    value += (PALETTE.canvas_warm[i] - value) * warm_light * 0.20
                    value += (PALETTE.face_glow[i] - value) * blue_pool * 0.12
                    rgb.append(max(0, min(255, int(value))))
                small.set_at((x, y), rgb)

        result = pygame.transform.smoothscale(small, size)
        haze = pygame.Surface(size, pygame.SRCALPHA)
        pygame.draw.circle(
            haze,
            (*PALETTE.highlight, 28),
            (int(w * 0.17), int(h * 0.12)),
            int(min(w, h) * 0.22),
        )
        pygame.draw.circle(
            haze,
            (*PALETTE.primary_soft, 22),
            (int(w * 0.84), int(h * 0.82)),
            int(min(w, h) * 0.27),
        )
        result.blit(haze, (0, 0))
        return result

    def _make_shell(self, size: tuple[int, int]) -> pygame.Surface:
        """Build the canonical soft ROBI head, face panel, ears and antenna."""
        w, h = size
        body = self._robot_rect
        display = self._display_rect
        shell = pygame.Surface(size, pygame.SRCALPHA)

        if not self.compact:
            floor = pygame.Rect(
                body.left + int(body.width * 0.08),
                body.bottom - int(body.height * 0.01),
                int(body.width * 0.84),
                int(body.height * 0.15),
            )
            pygame.draw.ellipse(shell, (*PALETTE.shell_shadow, 34), floor)

        ear_w = max(10, int(body.width * 0.09))
        ear_h = max(18, int(body.height * 0.32))
        ear_y = body.top + int(body.height * 0.38)
        for side in (-1, 1):
            ear = pygame.Rect(0, 0, ear_w, ear_h)
            ear.center = (
                body.left - int(ear_w * 0.18)
                if side < 0
                else body.right + int(ear_w * 0.18),
                ear_y,
            )
            pygame.draw.rect(
                shell,
                (*PALETTE.shell_shadow, 62),
                ear.move(0, max(2, int(body.height * 0.018))),
                border_radius=ear_w // 2,
            )
            ear_fill = _rounded_gradient(
                ear.size,
                PALETTE.face_glow,
                PALETTE.primary_soft,
                ear_w // 2,
            )
            shell.blit(ear_fill, ear.topleft)
            pygame.draw.rect(
                shell,
                (*PALETTE.display_glass, 150),
                ear,
                width=max(1, int(body.height * 0.008)),
                border_radius=ear_w // 2,
            )

        shadow_step = max(3, int(body.height * 0.025))
        pygame.draw.rect(
            shell,
            (*PALETTE.shell_shadow, 54),
            body.move(0, shadow_step),
            border_radius=int(body.height * 0.23),
        )
        body_fill = _rounded_gradient(
            body.size,
            PALETTE.shell_top,
            PALETTE.shell_bottom,
            int(body.height * 0.23),
        )
        shell.blit(body_fill, body.topleft)
        pygame.draw.rect(
            shell,
            PALETTE.shell_rim,
            body,
            width=max(2, int(body.height * 0.012)),
            border_radius=int(body.height * 0.23),
        )
        body_gloss = pygame.Surface(body.size, pygame.SRCALPHA)
        pygame.draw.ellipse(
            body_gloss,
            (*PALETTE.highlight, 24),
            pygame.Rect(
                -int(body.width * 0.13),
                -int(body.height * 0.42),
                int(body.width * 0.92),
                int(body.height * 0.90),
            ),
        )
        body_mask = pygame.Surface(body.size, pygame.SRCALPHA)
        pygame.draw.rect(
            body_mask,
            (255, 255, 255, 255),
            body_mask.get_rect(),
            border_radius=int(body.height * 0.23),
        )
        body_gloss.blit(body_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        shell.blit(body_gloss, body.topleft)
        antenna_x = body.centerx
        antenna_top = max(int(h * 0.025), body.top - int(body.height * 0.25))
        stem_bottom = body.top + int(body.height * 0.04)
        stem_w = max(3, int(body.width * 0.022))
        pygame.draw.line(
            shell,
            (*PALETTE.shell_shadow, 90),
            (antenna_x + stem_w // 2, antenna_top + stem_w),
            (antenna_x + stem_w // 2, stem_bottom + stem_w),
            stem_w + 3,
        )
        pygame.draw.line(
            shell,
            PALETTE.primary,
            (antenna_x, antenna_top + stem_w),
            (antenna_x, stem_bottom),
            stem_w,
        )
        orb_r = max(6, int(body.width * 0.045))
        pygame.draw.circle(
            shell,
            (*PALETTE.shell_shadow, 78),
            (antenna_x + max(1, orb_r // 8), antenna_top + max(2, orb_r // 6)),
            orb_r,
        )
        pygame.draw.circle(shell, PALETTE.primary_soft, (antenna_x, antenna_top), orb_r)
        pygame.draw.circle(
            shell,
            PALETTE.face_glow,
            (antenna_x - orb_r // 3, antenna_top - orb_r // 3),
            max(2, orb_r // 3),
        )

        display_shadow = display.inflate(
            max(4, int(body.width * 0.012)),
            max(4, int(body.height * 0.024)),
        ).move(0, max(2, int(body.height * 0.012)))
        pygame.draw.rect(
            shell,
            (*PALETTE.shell_shadow, 48),
            display_shadow,
            border_radius=int(display.height * 0.25),
        )
        panel = _rounded_gradient(
            display.size,
            PALETTE.display_top,
            PALETTE.display_bottom,
            int(display.height * 0.23),
        )
        shell.blit(panel, display.topleft)
        pygame.draw.rect(
            shell,
            (*PALETTE.display_glass, 150),
            display,
            width=max(2, int(display.height * 0.018)),
            border_radius=int(display.height * 0.23),
        )

        glass = pygame.Surface(display.size, pygame.SRCALPHA)
        pygame.draw.ellipse(
            glass,
            (*PALETTE.highlight, 30),
            pygame.Rect(
                -int(display.width * 0.12),
                -int(display.height * 0.62),
                int(display.width * 0.86),
                int(display.height * 1.02),
            ),
        )
        mask = pygame.Surface(display.size, pygame.SRCALPHA)
        pygame.draw.rect(
            mask,
            (255, 255, 255, 255),
            mask.get_rect(),
            border_radius=int(display.height * 0.23),
        )
        glass.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        shell.blit(glass, display.topleft)

        return shell

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
        self._state_clock = 0.0

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
        self._state_clock += dt
        self._reaction_left = max(0.0, self._reaction_left - dt)

        # Тимчасові стани самі повертаються в idle; стани без hold_s
        # лишаються, поки їх не змінять — «помилка», яка зникла сама,
        # людину біля стійки лише спантеличить.
        if self._state_left is not None:
            self._state_left -= dt
            if self._state_left <= 0.0:
                self._state = MascotState.IDLE
                self._state_left = None
                self._state_clock = 0.0
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

    def _current_eye(self, sign: int) -> tuple[pygame.Surface, int]:
        """Eye silhouette with intentional asymmetry for emotional states."""
        look = look_for(self._state)
        # A success wink is legible without particles or color. It closes one
        # eye briefly, then settles into the shared happy crescent.
        if self._state is MascotState.SUCCESS and sign > 0 and self._state_clock < 0.72:
            return self._eye_variants[EYE_CLOSED]
        # Loading scans instead of showing two inert closed lines.
        if self._state is MascotState.LOADING:
            return self._eye_frames[0]
        # Thinking is slightly asymmetrical, a quiet EMO-like micro-expression.
        if self._state is MascotState.THINKING and sign > 0:
            return self._eye_variants[EYE_NARROW]
        if look.eye == EYE_OPEN:
            return self._blink_frame()
        return self._eye_variants[look.eye]

    def _animated_gaze(self, look) -> tuple[float, float]:
        if self._state is MascotState.LOADING:
            return (math.sin(self._state_clock * 2.4) * 0.58, 0.10)
        if self._state is MascotState.THINKING:
            return (
                look.gaze[0] + math.sin(self._state_clock * 0.9) * 0.08,
                look.gaze[1] + math.cos(self._state_clock * 0.7) * 0.04,
            )
        if self._state is MascotState.EMPTY:
            return (
                look.gaze[0] + math.sin(self._state_clock * 0.65) * 0.05,
                look.gaze[1],
            )
        return look.gaze

    def _state_lift(self, sign: int, h: int) -> float:
        if self._state is MascotState.LOADING:
            return math.sin(self._state_clock * 3.0 + sign * 0.8) * h * 0.008
        if self._state is MascotState.ACHIEVEMENT:
            return -abs(math.sin(self._state_clock * 3.2)) * h * 0.010
        if self._state is MascotState.SAD:
            return h * 0.012
        return 0.0

    def _blink_frame(self) -> tuple[pygame.Surface, int]:
        if self._blink_progress <= 0.0:
            return self._eye_frames[0]
        closed = math.sin(min(2.0, self._blink_progress) * math.pi / 2.0)
        idx = min(BLINK_STEPS - 1, int(closed * (BLINK_STEPS - 1)))
        return self._eye_frames[idx]

    # -- рендер --------------------------------------------------------

    def draw(self, target: pygame.Surface) -> None:
        w, h = self.size
        if self.compact:
            target.fill((0, 0, 0, 0))
        else:
            target.blit(self._background, (0, 0))

        reaction = self._reaction_amount()
        state_float = 0.0
        if self._state is MascotState.ACHIEVEMENT:
            state_float = -abs(math.sin(self._state_clock * 3.2)) * h * 0.008
        elif self._state is MascotState.SAD:
            state_float = h * 0.006
        head_y = int(self._breath * h - reaction * h * 0.010 + state_float)
        head_x = 0
        if self._reaction_kind == "oops" and reaction > 0.0:
            head_x = int(math.sin(self._state_clock * 18.0) * reaction * w * 0.004)

        target.blit(self._shell, (head_x, head_y))
        self._draw_cheeks(target, reaction, head_x, head_y)

        cy = self._eye_y + head_y
        look = look_for(self._state)
        gx, gy = self._gaze
        sx, sy = self._saccade
        # Стан може вести погляд сам: «дивляться вгору» в thinking,
        # «вбік» у empty. Стеження за людиною лишається тільки в idle,
        # інакше емоція боролася б із камерою за напрямок очей.
        if not look.follows_face:
            gx, gy = self._animated_gaze(look)
            sx = sy = 0.0
        for sign in (-1, 1):
            eye, eye_h = self._current_eye(sign)
            canvas_w, canvas_h = eye.get_width(), eye.get_height()
            cx = w / 2.0 + sign * self._eye_dx + head_x
            eye_cy = cy + self._state_lift(sign, self._display_rect.height)
            target.blit(eye, (int(cx - canvas_w / 2), int(eye_cy - canvas_h / 2)))

            if eye_h > self._pupil_h * 0.48:
                px = cx + (gx + sx) * self._travel
                py = eye_cy + (gy + sy) * self._travel * 0.62
                target.set_clip(
                    pygame.Rect(
                        int(cx - self._eye_w / 2),
                        int(eye_cy - eye_h / 2),
                        self._eye_w,
                        eye_h,
                    )
                )
                target.blit(
                    self._pupil,
                    (int(px - self._pupil_w / 2), int(py - self._pupil_h / 2)),
                )
                target.set_clip(None)

        self._draw_mouth(target, reaction, head_x, head_y)
        self._draw_expression(target, reaction, head_x, head_y)
        if self.show_handle:
            self._draw_handle(target)

    def _draw_cheeks(
        self,
        target: pygame.Surface,
        reaction: float,
        head_x: int,
        head_y: int,
    ) -> None:
        amount = reaction
        if self._state in {
            MascotState.HAPPY,
            MascotState.SUCCESS,
            MascotState.ACHIEVEMENT,
        }:
            amount = max(amount, 0.78)
        if amount <= 0.04:
            return
        self._cheek.set_alpha(min(150, int(48 + amount * 90)))
        y = int(self._display_rect.top + self._display_rect.height * 0.63 + head_y)
        offset = int(self._display_rect.width * 0.37)
        for x in (
            self._display_rect.centerx - offset + head_x,
            self._display_rect.centerx + offset + head_x,
        ):
            target.blit(self._cheek, self._cheek.get_rect(center=(x, y)))

    def _draw_mouth(
        self,
        target: pygame.Surface,
        reaction: float,
        head_x: int,
        head_y: int,
    ) -> None:
        if self._state in {MascotState.SLEEPING, MascotState.LOADING}:
            return
        if self._state in {MascotState.SAD, MascotState.EMPTY}:
            key = "frown"
        elif self._state is MascotState.WARNING:
            key = "flat"
        elif self._state in {MascotState.ERROR, MascotState.POINTING}:
            key = "o"
        elif self._state in {
            MascotState.HAPPY,
            MascotState.SUCCESS,
            MascotState.ACHIEVEMENT,
        } or reaction > 0.35:
            key = "happy"
        else:
            key = "smile"
        mouth = self._mouth_variants[key]
        center = (
            self._display_rect.centerx + head_x,
            int(self._mouth_y + head_y),
        )
        target.blit(mouth, mouth.get_rect(center=center))

    def _draw_handle(self, target: pygame.Surface) -> None:
        """Коротка смужка вгорі: «мене можна потягнути».

        Свідомо непомітна. Це та сама ручка, що в шторок на телефоні:
        хто знає жест — упізнає її боковим зором, хто не знає — не
        відволікається. Тому ні анімації, ні пульсації, ні підпису: на
        вітрині біля стійки миготливий елемент перетягує на себе увагу,
        яка мала б дістатися дитині поруч.
        """
        w, h = self.size
        width = max(24, int(w * 0.055))
        height = max(3, int(h * 0.006))
        x = w // 2 - width // 2
        y = max(height, int(h * 0.022))
        bar = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(
            bar, (*PALETTE.face_glow, 120), bar.get_rect(), border_radius=height // 2
        )
        target.blit(bar, (x, y))

    def _draw_expression(
        self,
        target: pygame.Surface,
        reaction: float,
        head_x: int,
        head_y: int,
    ) -> None:
        """Draw lightweight semantic accents around the character."""
        look = look_for(self._state)

        if look.zzz:
            self._draw_zzz(target, head_x, head_y)

        self._draw_state_marks(target, head_x, head_y)

        # Іскри світяться і від стану (happy/success/achievement), і від
        # короткої реакції на дотик — беремо сильніше з двох.
        amount = max(reaction, 0.85 if look.sparkle else 0.0)
        if amount <= 0.03:
            return

        self._star.set_alpha(min(230, int(amount * 230)))
        body = self._robot_rect
        for x, y in (
            (body.left - int(body.width * 0.09) + head_x, body.top + int(body.height * 0.12) + head_y),
            (body.right + int(body.width * 0.045) + head_x, body.top + int(body.height * 0.26) + head_y),
        ):
            target.blit(self._star, (x, y))

    def _draw_state_marks(
        self,
        target: pygame.Surface,
        head_x: int,
        head_y: int,
    ) -> None:
        """Small semantic marks make all twelve states distinct without color alone."""
        display = self._display_rect.move(head_x, head_y)
        w, h = display.size
        t = self._state_clock

        if self._state is MascotState.THINKING:
            for index, radius in enumerate((0.010, 0.014, 0.019)):
                x = int(display.right - w * (0.15 - index * 0.045))
                y = int(display.top + h * (0.18 - index * 0.075))
                pygame.draw.circle(target, PALETTE.eye_line, (x, y), max(3, int(h * radius)))
        elif self._state is MascotState.LOADING:
            pulse = 0.45 + math.sin(t * 3.2) * 0.18
            for index in range(3):
                x = int(display.centerx + (index - 1) * w * 0.07)
                y = int(display.top + h * 0.78)
                radius = max(3, int(h * (0.010 + 0.004 * math.sin(t * 3.2 + index))))
                color = (
                    PALETTE.eye_line
                    if index == int(t * 2.0) % 3
                    else PALETTE.primary_soft
                )
                pygame.draw.circle(target, color, (x, y), int(radius * pulse + radius * 0.6))
        elif self._state is MascotState.SAD:
            phase = min(1.0, t / 0.7)
            x = int(display.centerx + self._eye_dx + self._eye_w * 0.30)
            y = int(self._eye_y + head_y + self._eye_h * 0.42 + phase * h * 0.10)
            r = max(4, int(h * 0.012))
            pygame.draw.circle(target, PALETTE.face_glow, (x, y), r)
            pygame.draw.polygon(
                target,
                PALETTE.face_glow,
                [(x - r, y), (x + r, y), (x, y - r * 2)],
            )
        elif self._state is MascotState.WARNING:
            x = int(display.right - w * 0.09)
            y = int(display.top + h * 0.16)
            length = int(h * 0.15)
            pygame.draw.line(target, PALETTE.accent_yellow, (x, y), (x, y + length), max(4, int(h * 0.010)))
            pygame.draw.circle(target, PALETTE.accent_yellow, (x, y + int(length * 1.35)), max(3, int(h * 0.007)))
        elif self._state is MascotState.ERROR:
            x = int(display.right - w * 0.09)
            y = int(display.top + h * 0.16)
            pygame.draw.line(target, PALETTE.accent_coral, (x, y), (x, y + int(h * 0.15)), max(4, int(h * 0.025)))
            pygame.draw.circle(target, PALETTE.accent_coral, (x, y + int(h * 0.20)), max(3, int(h * 0.020)))
        elif self._state is MascotState.POINTING:
            x = int(display.right - w * 0.14)
            y = int(display.top + h * 0.63)
            length = int(w * 0.10)
            pygame.draw.line(
                target,
                PALETTE.eye_line,
                (x, y),
                (x + length, y),
                max(3, int(h * 0.008)),
            )
            pygame.draw.polygon(
                target,
                PALETTE.eye_line,
                [(x + length, y), (x + length - int(h * 0.08), y - int(h * 0.06)), (x + length - int(h * 0.08), y + int(h * 0.06))],
            )

    def _draw_zzz(
        self,
        target: pygame.Surface,
        head_x: int,
        head_y: int,
    ) -> None:
        """Сон у гайді показується літерами, а не заплющеними очима."""
        w, h = self.size
        body = self._robot_rect.move(head_x, head_y)
        if self._zzz_font is None:
            self._zzz_font = ui_font(max(20, int(h * 0.085)), weight="semibold")
        for i in range(3):
            phase = (self._clock * 0.55 + i * 0.33) % 1.0
            alpha = int(200 * math.sin(phase * math.pi))
            glyph = self._zzz_font.render("z", True, PALETTE.eye_line)
            glyph.set_alpha(max(0, alpha))
            scale = 0.7 + 0.5 * phase
            glyph = pygame.transform.smoothscale(
                glyph, (max(1, int(glyph.get_width() * scale)), max(1, int(glyph.get_height() * scale)))
            )
            x = int(body.right - body.width * 0.10 + i * body.width * 0.045)
            y = int(body.top + body.height * 0.12 - phase * body.height * 0.16)
            target.blit(glyph, (x, y))
