"""Спільний словник подій і намірів.

Це єдине місце, де описано, чим шари обмінюються між собою. Правило:
вгору по стеку йдуть **факти** (що сталося), вниз — **наміри** (що показати).
Жоден шар не передає сирі дані периферії: зокрема vision віддає позицію
обличчя, але ніколи не кадр (D-027).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum


def now() -> float:
    """Монотонний час у секундах. Не залежить від корекції системного годинника."""
    return time.monotonic()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


# --------------------------------------------------------------------------
# Події від периферії та світу
# --------------------------------------------------------------------------


class Source(str, Enum):
    TOUCH = "touch"
    TOF = "tof"
    NFC = "nfc"
    VISION = "vision"
    CRM = "crm"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class Event:
    source: Source
    at: float = field(default_factory=now)


@dataclass(frozen=True, slots=True)
class Touch(Event):
    """Семантична дія, а не сирі координати (див. crm-integration.md)."""

    action_id: str = "tap"
    x: float = 0.0
    y: float = 0.0


@dataclass(frozen=True, slots=True)
class Swipe(Event):
    """Протягування пальцем. Координати нормалізовані, як у `Touch`.

    Окремо від `Touch` навмисно: протягування — це намір, відмінний від
    натискання, і плутати їх означало б відкривати меню щоразу, коли
    людина тягне екран.
    """

    direction: str = "down"
    x: float = 0.0
    y: float = 0.0
    distance: float = 0.0


@dataclass(frozen=True, slots=True)
class Presence(Event):
    """ToF: є людина поруч чи ні."""

    present: bool = False
    distance_mm: int | None = None


@dataclass(frozen=True, slots=True)
class FaceSeen(Event):
    """Результат детекції обличчя.

    `x`/`y` нормалізовані в діапазон -1..1 відносно центра кадру.
    Кадр сюди не потрапляє й потрапити не може — це межа D-027.
    """

    count: int = 0
    x: float = 0.0
    y: float = 0.0
    size: float = 0.0


@dataclass(frozen=True, slots=True)
class NfcTouched(Event):
    """Телефон торкнувся мітки. Ідентифікації особи тут не буває (D-014)."""

    ok: bool = True
    kind: str = "link"


# --------------------------------------------------------------------------
# Команди CRM
# --------------------------------------------------------------------------


class CommandKind(str, Enum):
    SET_MODE = "command.set_mode"
    SHOW_QR = "command.show_qr"
    CANCEL = "command.cancel"
    REQUEST_STATUS = "command.request_status"


@dataclass(frozen=True, slots=True)
class Command:
    """Конверт команди CRM.

    `expires_at` — монотонний дедлайн, уже переведений з wall-clock при
    прийомі. Прострочені команди не виконуються й не відтворюються після
    reconnect.
    """

    kind: CommandKind
    command_id: str
    payload: dict
    received_at: float = field(default_factory=now)
    expires_at: float | None = None

    def expired(self, at: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        return (at if at is not None else now()) >= self.expires_at


class CommandStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CommandResult:
    command_id: str
    status: CommandStatus
    reason: str = ""


# --------------------------------------------------------------------------
# Наміри режимів
# --------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Intent:
    """Намір режиму. Режим не чіпає залізо напряму — він просить."""

    rgb: tuple[int, int, int] | None = None
    sound: str | None = None
    ttl: float = 0.0
