"""Локальна служба, з якої веб-інтерфейс читає стан пристрою.

Чому вона взагалі з'явилася. Майстерня Робі — сцена на WebGL, а кіоск
малює через pygame у 2D-поверхню, без OpenGL-контексту й без вбудованого
браузера. Вивести сцену в поверхню застосунку неможливо, тому інтерфейс
переїжджає у веб. Python лишається тим, у чому він тут сильний: CRM, токен
пристрою, камера, контент, здоров'я. Веб читає це звідси, а не дублює.

Чому лише 127.0.0.1, і чому це перевіряється, а не документується. Пристрій
стоїть у холі школи, і на ньому працює анкета з персональними даними
батьків (`D-049`). Зайвий порт, відкритий у мережу, — це нова поверхня
атаки без жодної потреби. Тому не-локальна адреса не «не рекомендується»,
а відхиляється на старті: конфігурацію правлять руками, і одруківка в ній
не повинна тихо виставити пристрій назовні.

Чому крок 1 лише читає. Поки веб-частина не доведена на самому планшеті,
старий шлях мусить лишатися робочим і незмінним. Служба нічого не змінює в
стані кіоску й вимикається одним прапорцем, тому цей крок оборотний.
"""

from __future__ import annotations

import json
import threading
import socket
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import unquote, urlparse

from ..content import Content
from ..mascot_state import MascotState

#: Адреси, з яких служба погоджується стартувати. Іменований `localhost`
#: свідомо не приймається: він залежить від hosts-файлу, а тут потрібна
#: гарантія, а не збіг налаштувань.
LOOPBACK = frozenset({"127.0.0.1", "::1"})

#: Типи, які веб-інтерфейс реально забирає. Усе інше віддавати немає
#: причин, а короткий список простіше перевірити очима, ніж заперечення.
CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".avif": "image/avif",
    ".webp": "image/webp",
    ".woff2": "font/woff2",
}


class WebServiceError(RuntimeError):
    """Службу не можна підняти безпечно. Краще не стартувати."""


def snapshot(
    content: Content | None,
    state: MascotState,
    *,
    device_id: str,
    site: str,
    revision: int = 0,
) -> dict:
    """Знімок, який веб-інтерфейс показує.

    Це дані, не розмітка. `D-048` забороняє виконувати HTML або код, що
    прийшов ззовні, і межа тут проходить так само, як у pygame-версії:
    вузол — набір полів, а рендер вирішує клієнт. Скомпрометована CRM
    зможе показати неправдивий текст, але не запустити код у браузері.
    """
    nodes: list[dict] = []
    if content is not None:
        for node in content.nodes.values():
            nodes.append(
                {
                    "id": node.id,
                    "kind": node.kind,
                    "title": node.title,
                    "items": list(node.items),
                    "body": node.body,
                    "price": node.price,
                    "icon": node.icon,
                    "image": node.image,
                    "age_min": node.age_min,
                    "age_max": node.age_max,
                    "duration_months": node.duration_months,
                    "highlights": list(node.highlights),
                    "accent": node.accent,
                }
            )
    return {
        "revision": revision,
        "device": {"id": device_id, "site": site},
        "mascot": {"state": state.value},
        "content": {
            "root": content.root if content is not None else "",
            "nodes": nodes,
        },
    }


@dataclass(frozen=True, slots=True)
class _Route:
    root: Path | None
    provider: Callable[[], Mapping]
    action: Callable | None = None
    asset: Callable | None = None


class _Handler(BaseHTTPRequestHandler):
    server_version = "robi-local"
    sys_version = ""
    route: _Route

    def log_message(self, *args) -> None:  # noqa: D102 - журнал кіоску веде застосунок
        return

    def do_GET(self) -> None:  # noqa: N802 - ім'я задає BaseHTTPRequestHandler
        if not self._local_request():
            self._reject(HTTPStatus.FORBIDDEN)
            return
        path = unquote(urlparse(self.path).path)
        if path == "/api/snapshot":
            self._json(dict(self.route.provider()))
            return
        if path.startswith("/media/") and self.route.asset is not None:
            target = self.route.asset(path)
            if target is None:
                self._reject(HTTPStatus.NOT_FOUND)
            else:
                self._file(target)
            return
        self._static(path)

    def _local_request(self):
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        host = self.headers.get("Host", "")
        origin = self.headers.get("Origin")
        return host in hosts and (origin is None or origin == f"http://{host}")

    def _reject(self, status: HTTPStatus) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        if self.route.action is None or self.path != "/api/action":
            self._reject(HTTPStatus.METHOD_NOT_ALLOWED)
            return
        if not self._local_request() or self.headers.get("Content-Type") != "application/json":
            self._reject(HTTPStatus.FORBIDDEN)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 2048:
                raise ValueError("length")
            self.connection.settimeout(3)
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("object required")
        except (ValueError, OSError):
            self._reject(HTTPStatus.BAD_REQUEST)
            return
        self._json(self.route.action(payload))

    def do_PUT(self):
        self._reject(HTTPStatus.METHOD_NOT_ALLOWED)

    do_PATCH = do_PUT
    do_DELETE = do_PUT

    def _json(self, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path: str) -> None:
        root = self.route.root
        if root is None:
            self._reject(HTTPStatus.NOT_FOUND)
            return
        relative = path.lstrip("/") or "index.html"
        target = (root / relative).resolve()
        # Порівнюємо вже розв'язані шляхи: перевірка рядка не витримує ні
        # `..`, ні символьного посилання, що веде за межі теки.
        if not target.is_relative_to(root) or not target.is_file():
            self._reject(HTTPStatus.NOT_FOUND)
            return
        self._file(target)

    def _file(self, target: Path) -> None:
        suffix = target.suffix.lower()
        try:
            body = target.read_bytes()
        except OSError:
            self._reject(HTTPStatus.NOT_FOUND)
            return
        content_type = CONTENT_TYPES.get(suffix)
        if content_type is None and suffix == ".img":
            if body.startswith(b"\x89PNG\r\n\x1a\n"):
                content_type = "image/png"
            elif body.startswith(b"\xff\xd8\xff"):
                content_type = "image/jpeg"
            elif body.startswith((b"GIF87a", b"GIF89a")):
                content_type = "image/gif"
            elif body.startswith(b"RIFF") and body[8:12] == b"WEBP":
                content_type = "image/webp"
        if content_type is None:
            self._reject(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)


class LocalWebService:
    """HTTP-служба на петлі, яку читає веб-інтерфейс.

    Живе у власному потоці: кіоск має свій цикл кадрів і не може блокуватися
    на мережі. Постачальник знімка передається ззовні, тому служба не лізе
    у внутрішній стан застосунку й лишається придатною до тестів без сокета.
    """

    def __init__(
        self,
        provider: Callable[[], Mapping],
        *,
        host: str = "127.0.0.1",
        port: int = 4173,
        root: str | Path = "",
        action: Callable | None = None,
        asset: Callable | None = None,
    ) -> None:
        if host not in LOOPBACK:
            raise WebServiceError(
                f"служба слухає лише петлю, а не {host!r}: пристрій стоїть у холі школи"
            )
        static: Path | None = None
        if root:
            static = Path(root).resolve()
            if not static.is_dir():
                raise WebServiceError(f"тека веб-інтерфейсу не знайдена: {static}")
        self._route = _Route(root=static, provider=provider, action=action, asset=asset)
        self._host = host
        self._port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        """Фактичний порт. Нуль у конфігурації означає «будь-який вільний»."""
        return self._server.server_address[1] if self._server else self._port

    def start(self) -> None:
        if self._server is not None:
            return
        handler = type("_BoundHandler", (_Handler,), {"route": self._route})
        # `HTTPServer` вмикає SO_REUSEADDR, а на Windows це дозволяє стати
        # другим слухачем на вже зайнятому порту. Для кіоску це найгірший
        # варіант: замість чесної помилки — два процеси на одній адресі й
        # запити, що дістаються то одному, то іншому. Хай краще падає.
        server = type("_ExclusiveServer", (ThreadingHTTPServer,), {
            "allow_reuse_address": False,
            "address_family": socket.AF_INET6 if self._host == "::1" else socket.AF_INET,
        })
        try:
            self._server = server((self._host, self._port), handler)
        except OSError as exc:
            raise WebServiceError(f"не вдалося зайняти {self._host}:{self._port}: {exc}") from exc
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, name="robi-web", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self._server = None
        self._thread = None

    def __enter__(self) -> "LocalWebService":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()
