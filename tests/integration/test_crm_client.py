"""Клієнт CRM проти справжнього протоколу (D-056).

Перевіряється не «клієнт не падає», а те, заради чого писався стенд:
обидві сторони розуміють один конверт, і пристрій після з'єднання питає,
що показувати, замість сподіватися, що нічого не проґавив.
"""

import asyncio
import json
import threading
import time

import pytest
import websockets

from fake_crm import DEV_SECRET, envelope, handler, mint, process_request
from robi.events import CommandKind
from robi.integration.crm import CrmClient


class Server:
    """Фейкова CRM у власному потоці — клієнт теж має свій."""

    def __init__(self, scenario: str = "idle") -> None:
        self.scenario = scenario
        self.port = 0
        self._loop = None
        self._thread = None
        self._srv = None
        self.seen: list[dict] = []

    def start(self) -> None:
        ready = threading.Event()

        def run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)

            async def wrapped(ws):
                # Читач має бути один — гачок фейку, а не паралельний цикл.
                await handler(ws, self.scenario, on_message=self.seen.append)

            async def boot():
                self._srv = await websockets.serve(
                    wrapped, "127.0.0.1", 0, process_request=process_request
                )
                self.port = self._srv.sockets[0].getsockname()[1]
                ready.set()
                await asyncio.Future()

            try:
                self._loop.run_until_complete(boot())
            except asyncio.CancelledError:
                pass

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        assert ready.wait(5.0), "сервер не піднявся"

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}"

    def stop(self) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)


@pytest.fixture
def server():
    srv = Server()
    srv.start()
    yield srv
    srv.stop()


def wait_for(predicate, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.03)
    return False


def client_for(server: Server, **kwargs) -> CrmClient:
    return CrmClient(server.url, "robi-test", 0.1, 0.4, device_no=1,
                     token=kwargs.pop("token", mint(1)), **kwargs)


# --- з'єднання ------------------------------------------------------------


def test_client_connects_and_says_hello(server):
    c = client_for(server)
    c.start()
    try:
        assert wait_for(lambda: c.status.connected)
        assert wait_for(lambda: any(m.get("type") == "device.hello" for m in server.seen))
    finally:
        c.stop()


def test_client_asks_what_to_show_on_connect(server):
    """Осердя контракту: мовлення CRM є fire-and-forget."""
    c = client_for(server)
    c.start()
    try:
        assert wait_for(lambda: any(m.get("type") == "device.sync" for m in server.seen))
    finally:
        c.stop()


def test_desired_state_arrives_as_a_command(server):
    c = client_for(server)
    got: list = []

    def collected() -> bool:
        got.extend(c.drain())
        return any(cmd.command_id.startswith("sync:") for cmd in got)

    c.start()
    try:
        assert collected() or wait_for(collected, timeout=5.0), f"звірка не дійшла: {got}"
        sync = next(cmd for cmd in got if cmd.command_id.startswith("sync:"))
        assert sync.kind is CommandKind.SET_MODE
        assert sync.payload["mode"] == "mascot"
    finally:
        c.stop()


def test_without_token_client_stays_offline(server):
    """Стукати в CRM без токена немає сенсу — сервер відмовить на рукостисканні."""
    c = client_for(server, token="")
    c.start()
    try:
        assert wait_for(lambda: c.status.last_error == "no_token")
        assert not c.status.connected
    finally:
        c.stop()


def test_bad_token_is_reported_not_hidden(server):
    """401 має бути видно в health: це протухлий токен, а не мережа."""
    c = client_for(server, token=mint(1, secret="чужий-секрет"))
    c.start()
    try:
        assert wait_for(lambda: c.status.attempts >= 1)
        assert not c.status.connected
        assert c.status.last_error
    finally:
        c.stop()


def test_foreign_channel_is_refused(server):
    """Пристрій 2 з токеном пристрою 1 не має підключитися (D-056)."""
    c = CrmClient(server.url, "robi-test", 0.1, 0.4, device_no=2, token=mint(1))
    c.start()
    try:
        assert wait_for(lambda: c.status.attempts >= 1)
        assert not c.status.connected
    finally:
        c.stop()


def test_endpoint_carries_token_and_channel():
    c = CrmClient("ws://host:1/", "robi", device_no=7, token="tok en")
    url = c.endpoint()
    assert url.startswith("ws://host:1/ws?")
    assert "channels=device:7" in url
    assert "token=tok%20en" in url


# --- команди --------------------------------------------------------------


def test_commands_are_parsed_from_the_real_envelope(server):
    c = client_for(server)
    assert c._parse(envelope("command.show_qr", {
        "command_id": "abc", "payload": {"value": "https://example.org/x"},
        "expires_in_ms": 5000,
    })).kind is CommandKind.SHOW_QR


def test_old_protocol_no_longer_parses(server):
    """Саморобний конверт має перестати працювати, інакше їх стало б два."""
    c = client_for(server)
    assert c._parse(json.dumps({
        "type": "command.show_qr", "command_id": "abc", "payload": {},
    })) is None


def test_command_without_id_is_dropped(server):
    c = client_for(server)
    assert c._parse(envelope("command.show_qr", {"payload": {}})) is None


def test_unknown_event_is_dropped(server):
    c = client_for(server)
    assert c._parse(envelope("command.launch_rocket", {"command_id": "x"})) is None


def test_garbage_is_dropped(server):
    c = client_for(server)
    for junk in ("", "{", "[]", '"str"', b"\x00\x01"):
        assert c._parse(junk) is None
