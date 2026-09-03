"""Рукостискання з CRM живцем (D-056).

Юніт-тести перевіряють правило доступу як функцію. Тут піднімається
справжній сервер і справжнє з'єднання — бо між правильною функцією і
працюючим протоколом лежить розбір URL, коди відмови й порядок обміну,
і саме там ламається на живому пристрої.
"""

import asyncio
import json

import pytest
import websockets

from fake_crm import handler, mint, process_request


@pytest.fixture
def server():
    """Піднімає фейкову CRM на вільному порту у власному циклі."""
    loop = asyncio.new_event_loop()

    async def start():
        srv = await websockets.serve(
            lambda ws: handler(ws, "idle"),
            "127.0.0.1",
            0,
            process_request=process_request,
        )
        port = srv.sockets[0].getsockname()[1]
        return srv, port

    srv, port = loop.run_until_complete(start())
    yield loop, port
    srv.close()
    loop.run_until_complete(srv.wait_closed())
    loop.close()


def url(port: int, token: str, channels: str) -> str:
    return f"ws://127.0.0.1:{port}/ws?token={token}&channels={channels}"


def connect(loop, address, send=None, expect_reply=False):
    """Повертає (успіх, відповідь). Відмова сервера — не виняток тесту."""

    async def run():
        try:
            async with websockets.connect(address) as ws:
                if send is not None:
                    await ws.send(json.dumps(send))
                if expect_reply:
                    raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
                    return True, json.loads(raw)
                # Дати серверу мить, щоб закрити з'єднання, якщо він мав.
                await asyncio.sleep(0.05)
                return True, None
        except Exception:
            return False, None

    return loop.run_until_complete(run())


def test_device_connects_to_its_own_channel(server):
    loop, port = server
    ok, _ = connect(loop, url(port, mint(1), "device:1"))
    assert ok


def test_device_is_refused_on_someone_elses_channel(server):
    loop, port = server
    ok, _ = connect(loop, url(port, mint(1), "device:2"))
    assert not ok


def test_device_is_refused_on_a_lesson_channel(server):
    """Найважливіша відмова: витік токена не має відкривати уроки."""
    loop, port = server
    ok, _ = connect(loop, url(port, mint(1), "lesson:42"))
    assert not ok


def test_bad_token_is_refused(server):
    loop, port = server
    ok, _ = connect(loop, url(port, "не-токен", "device:1"))
    assert not ok


def test_expired_token_is_refused(server):
    loop, port = server
    ok, _ = connect(loop, url(port, mint(1, ttl_s=-1), "device:1"))
    assert not ok


def test_missing_channels_is_refused(server):
    loop, port = server
    ok, _ = connect(loop, f"ws://127.0.0.1:{port}/ws?token={mint(1)}")
    assert not ok


def test_wrong_route_is_refused(server):
    loop, port = server
    ok, _ = connect(loop, f"ws://127.0.0.1:{port}/nope?token={mint(1)}&channels=device:1")
    assert not ok


def test_sync_returns_the_desired_state(server):
    """Осердя контракту: пристрій питає, що показувати, а не сподівається."""
    loop, port = server
    ok, reply = connect(
        loop,
        url(port, mint(1), "device:1"),
        send={"type": "device.sync"},
        expect_reply=True,
    )
    assert ok
    assert reply["event"] == "device.state"
    assert reply["data"]["mode"] == "mascot"
    assert "ts" in reply


def test_admin_may_watch_a_device(server):
    loop, port = server
    ok, _ = connect(loop, url(port, mint(9, "admin"), "device:1"))
    assert ok
