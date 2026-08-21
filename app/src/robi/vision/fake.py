"""Fake vision: програє записаний сценарій руху обличчя без камери.

Людина повільно проходить перед столом, іноді зникає з кадру. Цього
достатньо, щоб перевірити поведінку погляду й повернення в нейтраль.
"""

from __future__ import annotations

import math

from ..events import FaceSeen, Source
from ..hardware.base import Health
from .base import VisionStats


class FakeVision:
    name = "vision"

    def __init__(self, fps: float = 8.0, cycle_s: float = 18.0) -> None:
        self._interval = 1.0 / fps
        self._cycle = cycle_s
        self._acc = 0.0
        self._t = 0.0
        self._capturing = False
        self._ok = False
        self._frames = 0
        self._detections = 0

    def initialize(self) -> Health:
        self._ok = True
        return self.health()

    def start_capture(self) -> None:
        if self._ok:
            self._capturing = True

    def stop_capture(self) -> None:
        self._capturing = False

    @property
    def capturing(self) -> bool:
        return self._capturing

    def poll(self, dt: float) -> list[FaceSeen]:
        if not (self._ok and self._capturing):
            return []
        self._t += dt
        self._acc += dt
        if self._acc < self._interval:
            return []
        self._acc = 0.0
        self._frames += 1

        phase = (self._t % self._cycle) / self._cycle
        # Дві третини циклу людина в кадрі, третину — немає.
        if phase > 0.66:
            return [FaceSeen(Source.VISION, count=0)]

        self._detections += 1
        x = math.sin(phase * math.tau * 1.5)
        y = 0.25 * math.sin(phase * math.tau * 0.7)
        return [FaceSeen(Source.VISION, count=1, x=x, y=y, size=0.3)]

    def stats(self) -> VisionStats:
        return VisionStats(self._frames, self._detections, self._capturing)

    def health(self) -> Health:
        return Health(self.name, self._ok, "fake")

    def shutdown(self) -> None:
        self._capturing = False
        self._ok = False
