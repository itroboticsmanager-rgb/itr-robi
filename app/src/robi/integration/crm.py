"""Клієнт CRM.

Живе в окремому потоці з власним asyncio-циклом і спілкується з
головним циклом через черги. Причина проста: головний цикл — ігровий,
і будь-яке очікування мережі в ньому означає просідання кадрів.

Reconnect з backoff і jitter; прострочені команди не відтворюються після
відновлення зв'язку (crm-integration.md).

Протокол — той самий, що в `ws-server` CRM (`D-056`): вхід
`/ws?token=<jwt>&channels=device:<id>`, вхідні повідомлення у вигляді
`{event, data, ts}`.

**Клієнт не питає CRM, що показувати, і це навмисно.** Мовлення в CRM є
fire-and-forget, тож команда, надіслана поки пристрій перепідключався,
втрачається. Спокуса — запитати бажаний стан при відновленні зв'язку,
але це не той інструмент: небезпечний випадок стається саме тоді, коли
зв'язку немає, і жодне питання при поверненні його не застає.

Пристрій, до якого не достукатися, мусить виходити з чутливого стану
сам. За це відповідає стеля часу життя активації в координаторі
(`MAX_CRM_ACTIVATION_S`), а не діалог із сервером. Відновлювати
попередню команду було б навіть гірше: за `D-038` платіжні посилання
одноразові, тож повторно показаний QR — це прострочений чужий рахунок.
"""

from __future__ import annotations

import asyncio
import json
import queue
import random
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import websockets

from ..events import Command, CommandKind, CommandResult, now

#: Верхня межа вхідної черги. Без неї відновлення зв'язку після довгого
#: простою вивалило б на пристрій усе, що накопичилось.
INBOX_LIMIT = 64



@dataclass(slots=True)
class LinkStatus:
    connected: bool = False
    attempts: int = 0
    last_error: str = ""


class CrmClient:
    def __init__(
        self,
        url: str,
        device_id: str,
        reconnect_min_s: float = 1.0,
        reconnect_max_s: float = 30.0,
        device_no: int = 1,
        token: str = "",
        token_url: str = "",
        secret_path: str = "",
    ) -> None:
        self._url = url.rstrip("/")
        self._device_id = device_id
        self._device_no = device_no
        self._static_token = token
        self._token = token
        self._token_url = token_url
        self._secret_path = secret_path
        self._min = reconnect_min_s
        self._max = reconnect_max_s

        self.inbox: queue.Queue[Command] = queue.Queue(maxsize=INBOX_LIMIT)
        self.outbox: queue.Queue[dict] = queue.Queue(maxsize=INBOX_LIMIT)

        self.status = LinkStatus()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- життєвий цикл -----------------------------------------------------

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="crm", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def report(self, result: CommandResult) -> None:
        self.send({
            "type": "command.status",
            "command_id": result.command_id,
            "status": result.status.value,
            "reason": result.reason,
        })

    def send(self, message: dict) -> None:
        try:
            self.outbox.put_nowait(message)
        except queue.Full:
            # Телеметрія не важливіша за роботу пристрою: гілка мовчки
            # відкидає найновіше, замість блокувати виклик.
            pass

    def drain(self, limit: int = 8) -> list[Command]:
        """Забирає команди у головний цикл. Обмежено, щоб не з'їсти кадр."""
        out: list[Command] = []
        for _ in range(limit):
            try:
                out.append(self.inbox.get_nowait())
            except queue.Empty:
                break
        return out

    # -- внутрішнє ---------------------------------------------------------

    # -- обмін секрету на токен -------------------------------------------

    def read_secret(self) -> str:
        """Читає секрет із файлу. Порожній файл дорівнює відсутньому.

        Секрет живе окремо від `device.toml` навмисно: конфігурацію не
        соромно показати чи покласти в Git, а це — обліковий запис
        пристрою (принцип 6). У журнал він не потрапляє ніколи.
        """
        if not self._secret_path:
            return ""
        try:
            return Path(self._secret_path).read_text(encoding="ascii").strip()
        except OSError:
            return ""

    async def _ensure_token(self) -> bool:
        """Готує токен до підключення. False — причина вже в `status`."""
        if self._static_token:
            self._token = self._static_token
            return True
        if not self._token_url:
            self.status = LinkStatus(connected=False, last_error="no_token_url")
            return False

        secret = self.read_secret()
        if not secret:
            self.status = LinkStatus(connected=False, last_error="no_secret")
            return False

        # urllib замість http-бібліотеки: залежності проєкту навмисно
        # мінімальні, а запит тут рідкий і простий. У потік винесено, бо
        # мережа в циклі asyncio блокувати не має.
        token, error = await asyncio.to_thread(self._exchange, secret)
        if token is None:
            self.status = LinkStatus(
                connected=False,
                attempts=self.status.attempts + 1,
                last_error=error or "token_failed",
            )
            return False
        self._token = token
        return True

    def _exchange(self, secret: str) -> tuple[str | None, str]:
        """Синхронний обмін. Секрет іде в заголовку, не в адресі.

        Адреси осідають у логах проксі та в історії; заголовки — ні.
        """
        request = urllib.request.Request(
            self._token_url,
            data=b"",
            method="POST",
            headers={"Authorization": f"Bearer {secret}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Код відмови важливий: 401 означає, що секрет не той, і
            # повторювати його вічно немає сенсу — це справа адміністратора.
            return None, f"token_http_{exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return None, f"token_net_{type(exc).__name__}"
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, "token_bad_response"

        token = payload.get("token")
        if not isinstance(token, str) or not token:
            return None, "token_missing"
        return token, ""

    def endpoint(self) -> str:
        """Адреса з токеном і каналом. Токен у логи не потрапляє."""
        channel = f"device:{self._device_no}"
        return f"{self._url}/ws?token={quote(self._token, safe='')}&channels={quote(channel, safe=':')}"

    def _run(self) -> None:
        asyncio.run(self._loop())

    async def _loop(self) -> None:
        delay = self._min
        while not self._stop.is_set():
            # Свіжий токен береться перед кожним підключенням, і цього
            # досить: сервер перевіряє його на рукостисканні, а далі
            # з'єднання живе, навіть коли токен уже протух. Фонового
            # оновлення не треба — воно тільки додало б таймерів.
            #
            # Невдача обміну не кидає виняток навмисно: інакше загальний
            # обробник нижче перезаписав би точну причину («секрет не той»,
            # «немає файлу») на безлике `ConnectionError`, а саме заради
            # цих причин `_ensure_token` їх і розрізняє.
            if not await self._ensure_token():
                if self._stop.is_set():
                    return
                await asyncio.sleep(delay * random.uniform(0.7, 1.3))
                delay = min(self._max, delay * 2)
                continue

            try:
                async with websockets.connect(self.endpoint(), open_timeout=5) as ws:
                    self.status = LinkStatus(connected=True, attempts=0)
                    delay = self._min
                    await self._hello(ws)
                    await self._pump(ws)
            except Exception as exc:  # мережа падає різними способами
                # Код відмови варто зберегти: 401 означає протухлий токен,
                # 403 — канал не за роллю, і це різні дії адміністратора.
                detail = type(exc).__name__
                status_code = getattr(getattr(exc, "response", None), "status_code", None)
                if status_code is not None:
                    detail = f"{detail}:{status_code}"
                self.status = LinkStatus(
                    connected=False,
                    attempts=self.status.attempts + 1,
                    last_error=detail,
                )

            if self._stop.is_set():
                return
            # Jitter розводить у часі перепідключення кількох пристроїв,
            # інакше вони синхронно б'ють у CRM після її перезапуску.
            await asyncio.sleep(delay * random.uniform(0.7, 1.3))
            delay = min(self._max, delay * 2)

    async def _hello(self, ws) -> None:
        await ws.send(json.dumps({
            "type": "device.hello",
            "device_id": self._device_id,
            "capabilities": ["mascot", "qr"],
        }))

    async def _pump(self, ws) -> None:
        async def reader() -> None:
            async for raw in ws:
                cmd = self._parse(raw)
                if cmd is None:
                    continue
                try:
                    self.inbox.put_nowait(cmd)
                except queue.Full:
                    # Черга повна — найстаріша команда вже неактуальна.
                    try:
                        self.inbox.get_nowait()
                        self.inbox.put_nowait(cmd)
                    except (queue.Empty, queue.Full):
                        pass

        async def writer() -> None:
            while not self._stop.is_set():
                try:
                    msg = self.outbox.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.05)
                    continue
                await ws.send(json.dumps(msg))

        await asyncio.gather(reader(), writer())

    def _parse(self, raw: str | bytes) -> Command | None:
        """Розбирає конверт `{event, data, ts}` у команду.

        Транспорт CRM про команди не знає: `/broadcast` передає лише
        подію й довільні дані. Тому `command_id`, TTL та ідемпотентність
        живуть усередині `data` і перевіряються тут, на пристрої.
        """
        try:
            message = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
        if not isinstance(message, dict):
            return None

        event = str(message.get("event", ""))
        data = message.get("data")
        if not isinstance(data, dict):
            data = {}

        try:
            kind = CommandKind(event)
        except ValueError:
            return None

        command_id = str(data.get("command_id") or "")
        if not command_id:
            return None

        payload = data.get("payload")
        if not isinstance(payload, dict):
            payload = {}

        # Wall-clock дедлайн переводиться в монотонний одразу при прийомі:
        # далі в системі корекція системного годинника вже не впливає.
        expires_at = None
        raw_expiry = data.get("expires_in_ms")
        if isinstance(raw_expiry, (int, float)) and raw_expiry > 0:
            expires_at = now() + float(raw_expiry) / 1000.0

        return Command(kind=kind, command_id=command_id, payload=payload, expires_at=expires_at)

