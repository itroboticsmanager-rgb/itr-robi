"""Системні стани: дозволені переходи й заборонені стрибки."""

import pytest

from robi.state.machine import IllegalTransition, StateMachine, SystemState


def test_starts_booting():
    assert StateMachine().state is SystemState.BOOTING


def test_boot_to_ready():
    m = StateMachine()
    m.to(SystemState.READY, "self-check ok")
    assert m.state is SystemState.READY


def test_cannot_skip_from_booting_to_interacting():
    """Пристрій не має «взаємодіяти» до завершення self-check."""
    m = StateMachine()
    with pytest.raises(IllegalTransition):
        m.to(SystemState.INTERACTING)


def test_shutting_down_is_terminal():
    m = StateMachine()
    m.to(SystemState.READY)
    m.to(SystemState.SHUTTING_DOWN)
    assert m.is_terminal()
    with pytest.raises(IllegalTransition):
        m.to(SystemState.READY)


def test_fault_can_only_go_to_service_or_shutdown():
    """З fault не можна «просто продовжити» — це б маскувало апаратну помилку."""
    m = StateMachine()
    m.to(SystemState.READY)
    m.to(SystemState.FAULT, "sensor jam")
    assert not m.can(SystemState.READY)
    assert m.can(SystemState.SERVICE)
    assert m.can(SystemState.SHUTTING_DOWN)


def test_offline_keeps_device_usable():
    """offline не є помилкою: з нього є шлях назад у ready та в interacting."""
    m = StateMachine()
    m.to(SystemState.READY)
    m.to(SystemState.OFFLINE, "crm unreachable")
    assert m.can(SystemState.READY)
    assert m.can(SystemState.INTERACTING)


def test_same_state_transition_is_noop():
    m = StateMachine()
    m.to(SystemState.READY)
    m.to(SystemState.READY)
    assert len(m.history) == 2


def test_history_records_reasons():
    m = StateMachine()
    m.to(SystemState.READY, "self-check ok")
    m.to(SystemState.OFFLINE, "crm unreachable")
    assert [reason for _, reason in m.history] == ["start", "self-check ok", "crm unreachable"]
