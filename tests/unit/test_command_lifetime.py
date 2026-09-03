"""Стеля часу життя команди від CRM.

Цей тест охороняє поведінку, яку легко зламати «оптимізацією»: команда
без строку не має жити вічно. Пристрій стоїть на рецепції й може
втратити мережу; поки її немає, CRM не скасує нічого, і єдиний, хто
здатен прибрати чужий платіжний QR з екрана, — сам пристрій.

Звірка стану при перепідключенні цього не замінює: розрив триває саме
тоді, коли звірки не буде.
"""

import pytest

from robi.events import Command, CommandKind, CommandStatus
from robi.state.coordinator import (
    MAX_CRM_ACTIVATION_S,
    Coordinator,
    ModeName,
    Priority,
)


class Clock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def coordinator(clock):
    return Coordinator(ModeName.MASCOT, clock=clock, unsupported=frozenset())


def qr(cid: str, **payload) -> Command:
    return Command(CommandKind.SHOW_QR, cid, {"value": "https://example.org/x", **payload})


def mode(cid: str, **payload) -> Command:
    return Command(CommandKind.SET_MODE, cid, {"mode": "qr", **payload})


# --- команда без строку ---------------------------------------------------


def test_set_mode_without_ttl_no_longer_lives_forever(coordinator, clock):
    """Саме тут була діра: `set_mode` без строку не спливала ніколи.

    `show_qr` мав власні типові 15 секунд і вічним не був — тест нижче
    це фіксує, щоб опис проблеми не розповзався ширшим за неї саму.
    """
    assert coordinator.apply(mode("c1")).status is CommandStatus.ACCEPTED
    assert coordinator.mode is ModeName.QR

    clock.advance(MAX_CRM_ACTIVATION_S + 1)
    assert coordinator.tick() is True
    assert coordinator.mode is ModeName.MASCOT


def test_show_qr_keeps_its_own_shorter_default(coordinator, clock):
    """Стеля не подовжує: у QR власний типовий строк, і він коротший."""
    coordinator.apply(qr("c2"))
    clock.advance(16.0)
    coordinator.tick()
    assert coordinator.mode is ModeName.MASCOT


def test_it_survives_until_the_ceiling(coordinator, clock):
    """Стеля не має обривати команду раніше часу."""
    coordinator.apply(mode("c3"))
    clock.advance(MAX_CRM_ACTIVATION_S - 1)
    assert coordinator.tick() is False
    assert coordinator.mode is ModeName.QR


# --- надто щедрий строк ---------------------------------------------------


def test_overlong_ttl_is_clamped(coordinator, clock):
    """Ризик той самий: різниця лише в тому, чи назвала CRM число навмисно."""
    coordinator.apply(mode("c4", duration_ms=int((MAX_CRM_ACTIVATION_S + 600) * 1000)))
    clock.advance(MAX_CRM_ACTIVATION_S + 1)
    coordinator.tick()
    assert coordinator.mode is ModeName.MASCOT


def test_short_ttl_is_left_alone(coordinator, clock):
    """Стеля обмежує, а не вирівнює: короткий строк лишається коротким."""
    coordinator.apply(qr("c5", duration_ms=2000))
    clock.advance(2.5)
    coordinator.tick()
    assert coordinator.mode is ModeName.MASCOT


# --- налаштовність --------------------------------------------------------


def test_ceiling_is_configurable(clock):
    c = Coordinator(ModeName.MASCOT, clock=clock, unsupported=frozenset(),
                    max_activation_s=10.0)
    c.apply(mode("c6"))
    clock.advance(11.0)
    c.tick()
    assert c.mode is ModeName.MASCOT


def test_user_interaction_is_not_capped_by_the_crm_ceiling(clock):
    """Стеля стосується команд CRM; меню під пальцем живе за своїм TTL."""
    c = Coordinator(ModeName.MASCOT, clock=clock, unsupported=frozenset())
    c.user_interaction(ModeName.INFO, ttl=45.0)
    assert c.active.priority is Priority.USER
    clock.advance(44.0)
    assert c.tick() is False
    clock.advance(2.0)
    assert c.tick() is True
