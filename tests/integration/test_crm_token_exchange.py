"""Обмін секрету пристрою на короткий токен (D-056).

Пристрій зберігає ключ, а не перепустку: токен CRM живе хвилини, тож
покласти його в конфігурацію неможливо. Тут перевіряється, що обмін
працює, а кожна причина відмови називається окремо — «немає зв'язку» і
«секрет не той» вимагають різних дій адміністратора.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from robi.integration.crm import CrmClient

SECRET = "s" * 24


class TokenHandler(BaseHTTPRequestHandler):
    """Мінімальний двійник endpoint-а CRM."""

    seen_auth: list[str] = []
    mode = "ok"

    def do_POST(self):  # noqa: N802 — так вимагає BaseHTTPRequestHandler
        TokenHandler.seen_auth.append(self.headers.get("Authorization", ""))
        if TokenHandler.mode == "unauthorized":
            return self._json(401, {"error": "unauthorized"})
        if TokenHandler.mode == "garbage":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"not json")
            return
        if TokenHandler.mode == "no_token":
            return self._json(200, {"deviceId": 1})
        return self._json(200, {"token": "minted-token", "deviceId": 1,
                                "channel": "device:1", "expiresInSeconds": 600})

    def _json(self, code: int, body: dict) -> None:
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):  # тиша в тестах
        return


@pytest.fixture
def token_server():
    TokenHandler.seen_auth = []
    TokenHandler.mode = "ok"
    srv = HTTPServer(("127.0.0.1", 0), TokenHandler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv, f"http://127.0.0.1:{srv.server_port}/api/device/realtime-token"
    srv.shutdown()


@pytest.fixture
def secret_file(tmp_path):
    path = tmp_path / "device-secret.txt"
    path.write_text(SECRET, encoding="ascii")
    return path


def client(url: str, secret_path) -> CrmClient:
    return CrmClient("ws://127.0.0.1:1", "robi-test", device_no=1,
                     token_url=url, secret_path=str(secret_path))


# --- читання секрету ------------------------------------------------------


def test_secret_is_read_from_its_own_file(token_server, secret_file):
    _, url = token_server
    assert client(url, secret_file).read_secret() == SECRET


def test_surrounding_whitespace_is_ignored(token_server, tmp_path):
    """Файл, створений редактором, зазвичай має кінцевий перенос рядка."""
    _, url = token_server
    path = tmp_path / "s.txt"
    path.write_text(f"  {SECRET}\n", encoding="ascii")
    assert client(url, path).read_secret() == SECRET


def test_missing_file_is_not_a_crash(token_server, tmp_path):
    _, url = token_server
    assert client(url, tmp_path / "немає.txt").read_secret() == ""


# --- обмін ----------------------------------------------------------------


def test_exchange_returns_a_token(token_server, secret_file):
    _, url = token_server
    token, error = client(url, secret_file)._exchange(SECRET)
    assert token == "minted-token"
    assert error == ""


def test_secret_travels_in_the_header(token_server, secret_file):
    """В адресі секрету бути не має: адреси осідають у логах проксі."""
    _, url = token_server
    c = client(url, secret_file)
    c._exchange(SECRET)
    assert TokenHandler.seen_auth[-1] == f"Bearer {SECRET}"
    assert SECRET not in c.endpoint()


def test_wrong_secret_is_named_distinctly(token_server, secret_file):
    """401 — справа адміністратора, а не привід перепідключатися вічно."""
    _, url = token_server
    TokenHandler.mode = "unauthorized"
    token, error = client(url, secret_file)._exchange(SECRET)
    assert token is None
    assert error == "token_http_401"


def test_unreachable_endpoint_is_named_distinctly(secret_file):
    """Мережа й хибний секрет — різні причини, і плутати їх не можна."""
    c = client("http://127.0.0.1:1/nope", secret_file)
    token, error = c._exchange(SECRET)
    assert token is None
    assert error.startswith("token_net_")


def test_broken_response_does_not_crash(token_server, secret_file):
    _, url = token_server
    TokenHandler.mode = "garbage"
    token, error = client(url, secret_file)._exchange(SECRET)
    assert token is None
    assert error == "token_bad_response"


def test_response_without_token_is_rejected(token_server, secret_file):
    _, url = token_server
    TokenHandler.mode = "no_token"
    token, error = client(url, secret_file)._exchange(SECRET)
    assert token is None
    assert error == "token_missing"


# --- причини відмови у health --------------------------------------------


def test_missing_secret_is_reported(token_server, tmp_path):
    import asyncio

    _, url = token_server
    c = client(url, tmp_path / "немає.txt")
    assert asyncio.run(c._ensure_token()) is False
    assert c.status.last_error == "no_secret"


def test_missing_url_is_reported(secret_file):
    import asyncio

    c = CrmClient("ws://127.0.0.1:1", "robi", device_no=1, secret_path=str(secret_file))
    assert asyncio.run(c._ensure_token()) is False
    assert c.status.last_error == "no_token_url"


def test_static_token_skips_the_exchange(token_server, secret_file):
    """Готовий токен лишається для розробки: обмін тоді не потрібен."""
    import asyncio

    _, url = token_server
    c = CrmClient("ws://127.0.0.1:1", "robi", device_no=1, token="dev-token",
                  token_url=url, secret_path=str(secret_file))
    assert asyncio.run(c._ensure_token()) is True
    assert c._token == "dev-token"
    assert TokenHandler.seen_auth == []
