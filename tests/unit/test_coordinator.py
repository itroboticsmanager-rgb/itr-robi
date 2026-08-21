"""Координатор режимів: пріоритети, TTL і idempotency."""

import pytest

from robi.events import Command, CommandKind, CommandStatus
from robi.state.coordinator import Coordinator, ModeName, Priority


def qr_command(cid="c1", value="https://example.org/x", **payload):
    return Command(CommandKind.SHOW_QR, cid, {"value": value, **payload})


def test_starts_in_base_mode():
    assert Coordinator().mode is ModeName.MASCOT


def test_crm_command_switches_mode():
    c = Coordinator()
    result = c.apply(qr_command(duration_ms=5000), at=100.0)
    assert result.status is CommandStatus.ACCEPTED
    assert c.mode is ModeName.QR


def test_activation_expires_back_to_base():
    c = Coordinator()
    c.apply(qr_command(duration_ms=5000), at=100.0)
    assert not c.tick(at=104.0)
    assert c.mode is ModeName.QR
    assert c.tick(at=105.1)
    assert c.mode is ModeName.MASCOT


def test_duplicate_command_id_does_not_repeat_action():
    """Дубль повертає той самий вердикт і не подовжує показ."""
    c = Coordinator()
    first = c.apply(qr_command(cid="same", duration_ms=5000), at=100.0)
    expires = c.active.expires_at

    second = c.apply(qr_command(cid="same", duration_ms=5000), at=103.0)
    assert second == first
    assert c.active.expires_at == expires


def test_expired_command_is_rejected():
    c = Coordinator()
    cmd = Command(CommandKind.SHOW_QR, "old", {"value": "https://example.org"}, expires_at=50.0)
    result = c.apply(cmd, at=100.0)
    assert result.status is CommandStatus.REJECTED
    assert result.reason == "expired"
    assert c.mode is ModeName.MASCOT


def test_empty_payload_is_rejected():
    c = Coordinator()
    result = c.apply(Command(CommandKind.SHOW_QR, "e", {}), at=100.0)
    assert result.status is CommandStatus.REJECTED
    assert result.reason == "empty_payload"


def test_unsupported_mode_is_rejected_honestly():
    """Нереалізований режим має бути відхилений, а не мовчки проковтнутий."""
    c = Coordinator()
    result = c.apply(Command(CommandKind.SET_MODE, "m", {"mode": "voice"}), at=100.0)
    assert result.status is CommandStatus.REJECTED
    assert result.reason == "unsupported_mode"


def test_unknown_mode_is_rejected():
    c = Coordinator()
    result = c.apply(Command(CommandKind.SET_MODE, "m", {"mode": "dance"}), at=100.0)
    assert result.reason == "unknown_mode"


def test_user_interaction_preempts_crm():
    """Активна взаємодія важливіша за команду CRM (architecture.md)."""
    c = Coordinator()
    c.apply(qr_command(duration_ms=30_000), at=100.0)
    assert c.user_interaction(ModeName.MASCOT, ttl=10.0, at=101.0)
    assert c.active.priority is Priority.USER


def test_crm_cannot_preempt_active_user():
    c = Coordinator()
    c.user_interaction(ModeName.MASCOT, ttl=10.0, at=100.0)
    result = c.apply(qr_command(cid="late", duration_ms=5000), at=101.0)
    assert result.status is CommandStatus.REJECTED
    assert result.reason == "preempted"


def test_crm_may_take_over_after_user_ttl_ends():
    c = Coordinator()
    c.user_interaction(ModeName.MASCOT, ttl=10.0, at=100.0)
    result = c.apply(qr_command(cid="later", duration_ms=5000), at=111.0)
    assert result.status is CommandStatus.ACCEPTED


def test_cancel_returns_to_base():
    c = Coordinator()
    c.apply(qr_command(cid="c1", duration_ms=30_000), at=100.0)
    c.apply(Command(CommandKind.CANCEL, "c2", {"target_command_id": "c1"}), at=101.0)
    assert c.mode is ModeName.MASCOT


def test_cancel_of_other_command_is_ignored():
    c = Coordinator()
    c.apply(qr_command(cid="c1", duration_ms=30_000), at=100.0)
    c.apply(Command(CommandKind.CANCEL, "c2", {"target_command_id": "other"}), at=101.0)
    assert c.mode is ModeName.QR


def test_payload_travels_with_activation():
    """Режим має отримати саме той payload, який прийшов у команді."""
    c = Coordinator()
    c.apply(qr_command(value="https://example.org/pay", title="Оплата"), at=100.0)
    assert c.active.payload["value"] == "https://example.org/pay"
    assert c.active.payload["title"] == "Оплата"


def test_command_memory_has_upper_bound():
    """Пам'ять про команди не має рости безмежно."""
    c = Coordinator()
    for i in range(700):
        c.apply(qr_command(cid=f"c{i}", duration_ms=1), at=100.0 + i)
    c.forget_older_than(0)
    assert len(c._seen_commands) <= 512
