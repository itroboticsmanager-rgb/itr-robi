"""Fake-адаптери: увесь слайс має працювати на звичайному ПК без заліза.

Це не заглушки-порожнечі — вони відтворюють поведінку, яку важливо
тестувати: періодичну присутність, дребезг NFC, відмову модуля.
"""

from __future__ import annotations

import random

from ..events import Event, NfcTouched, Presence, Source
from .base import Health


class FakeToF:
    """Імітує людину, що підходить до стола й відходить."""

    name = "tof"

    def __init__(self, period_s: float = 12.0, seed: int = 7) -> None:
        self._period = period_s
        self._t = 0.0
        self._present = False
        self._rng = random.Random(seed)
        self._ok = False

    def initialize(self) -> Health:
        self._ok = True
        return self.health()

    def poll(self, dt: float) -> list[Event]:
        if not self._ok:
            return []
        self._t += dt
        if self._t < self._period:
            return []
        self._t = 0.0
        self._present = not self._present
        distance = self._rng.randint(400, 1400) if self._present else None
        return [Presence(Source.TOF, present=self._present, distance_mm=distance)]

    def health(self) -> Health:
        return Health(self.name, self._ok, "fake")

    def shutdown(self) -> None:
        self._ok = False


class FakeNfc:
    """Динамічна мітка (D-036). Дребезг повторних читань гаситься тут."""

    name = "nfc"

    def __init__(self, debounce_s: float = 3.0) -> None:
        self._debounce = debounce_s
        self._since_last = debounce_s
        self._pending = False
        self._ok = False
        self._payload: str | None = None

    def initialize(self) -> Health:
        self._ok = True
        return self.health()

    def write(self, payload: str | None) -> None:
        """Запис NDEF у мітку. None стирає її — вимога одноразовості (D-038)."""
        self._payload = payload

    @property
    def payload(self) -> str | None:
        return self._payload

    def simulate_touch(self) -> None:
        self._pending = True

    def poll(self, dt: float) -> list[Event]:
        self._since_last += dt
        if not (self._ok and self._pending):
            return []
        self._pending = False
        if self._since_last < self._debounce:
            return []
        self._since_last = 0.0
        return [NfcTouched(Source.NFC, ok=self._payload is not None)]

    def health(self) -> Health:
        return Health(self.name, self._ok, "fake")

    def shutdown(self) -> None:
        self._ok = False


class FakeOutputs:
    """RGB і звук. Запам'ятовує останній стан, щоб тести могли його читати."""

    name = "outputs"

    def __init__(self) -> None:
        self.rgb: tuple[int, int, int] | None = None
        self.sound: str | None = None
        self.log: list[str] = []
        self._ok = False

    def initialize(self) -> Health:
        self._ok = True
        return self.health()

    def apply(self, rgb: tuple[int, int, int] | None, sound: str | None) -> None:
        if rgb != self.rgb:
            self.rgb = rgb
            self.log.append(f"rgb={rgb}")
        if sound:
            self.sound = sound
            self.log.append(f"sound={sound}")

    def health(self) -> Health:
        return Health(self.name, self._ok, "fake")

    def shutdown(self) -> None:
        # Виходи гаснуть при вимкненні — сценарій не має пережити застосунок.
        self.rgb = None
        self.sound = None
        self._ok = False
