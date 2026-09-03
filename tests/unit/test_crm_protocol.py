"""Контракт із CRM: токени й доступ до каналів (D-056).

Ці перевірки охороняють не код фейкового сервера, а правило, заради
якого воно існує: **пристрій стоїть у публічному приміщенні, і його
токен слід вважати таким, що рано чи пізно витече.** Тому роль `device`
не має відкривати нічого, крім власного каналу — тоді витік коштує рівно
одного пристрою, а не доступу до уроків і учнів.

Реалізація дослівно повторює `ws-server/src/jwt.ts` у CRM, тож тут же
ловиться розходження між двома боками контракту.
"""

import time

import pytest

from fake_crm import DEV_SECRET, authorize_channel, mint, verify


def payload_for(sub: int = 1, role: str = "device") -> dict:
    return {"sub": sub, "role": role}


# --- токен ----------------------------------------------------------------


def test_minted_token_verifies():
    token = mint(7, "device")
    payload = verify(token)
    assert payload is not None
    assert payload["sub"] == 7
    assert payload["role"] == "device"


def test_tampered_signature_is_rejected():
    token = mint(7)
    head, body, sig = token.split(".")
    assert verify(f"{head}.{body}.{sig[:-2]}xx") is None


def test_payload_cannot_be_swapped_without_the_secret():
    """Підміна sub має ламати підпис — інакше пристрій читав би чужий канал."""
    import base64
    import json

    head, body, sig = mint(7).split(".")
    forged = base64.urlsafe_b64encode(
        json.dumps({"sub": 999, "role": "admin", "iat": 0, "exp": 2**31}).encode()
    ).decode().rstrip("=")
    assert verify(f"{head}.{forged}.{sig}") is None


def test_wrong_secret_is_rejected():
    assert verify(mint(7, secret="інший-секрет")) is None


def test_expired_token_is_rejected():
    assert verify(mint(7, ttl_s=-1)) is None


def test_unknown_role_is_rejected():
    assert verify(mint(7, role="superuser")) is None


def test_garbage_is_rejected_without_raising():
    for junk in ("", "abc", "a.b", "a.b.c", "....", "x" * 500):
        assert verify(junk) is None


# --- доступ до каналів ----------------------------------------------------


def test_device_opens_only_its_own_channel():
    assert authorize_channel("device:1", payload_for(1))
    assert not authorize_channel("device:2", payload_for(1))


@pytest.mark.parametrize(
    "channel",
    ["lesson:42", "student:7", "admin:dashboard", "gartic:abc", "teacher:3"],
)
def test_device_cannot_reach_anything_else(channel):
    """Витік токена з рецепції має коштувати один пристрій, не школу."""
    assert not authorize_channel(channel, payload_for(1))


def test_admin_sees_any_device():
    assert authorize_channel("device:1", payload_for(9, "admin"))
    assert authorize_channel("device:99", payload_for(9, "admin"))


@pytest.mark.parametrize("role", ["teacher", "student"])
def test_other_roles_have_no_device_access(role):
    assert not authorize_channel("device:1", payload_for(5, role))


@pytest.mark.parametrize("channel", ["", "device", "device:", ":1", ":", "devices"])
def test_malformed_channel_is_rejected(channel):
    assert not authorize_channel(channel, payload_for(1))


def test_device_id_is_compared_as_a_whole():
    """`device:11` не має відкриватися токеном пристрою 1."""
    assert not authorize_channel("device:11", payload_for(1))
    assert not authorize_channel("device:1x", payload_for(1))
