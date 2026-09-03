"""Клієнт CRM.

Живе в окремому потоці з власним asyncio-циклом і спілкується з
головним циклом через черги. Причина проста: головний цикл — ігровий,
і будь-яке очікування мережі в ньому означає просідання кадрів.

Reconnect з backoff і jitter; прострочені команди не відтворюються після
відновлення зв'язку (crm-integration.md).

Протокол — той самий, що в `ws-server` CRM (`D-056`): вхід
`/ws?token=<jwt>&channels=device:<id>`, вхідні повідомлення у вигляді
`{event, data, ts}`.

**Після кожного з'єднання клієнт питає, що показувати.** Мовлення в CRM
є fire-and-forget: команда, надіслана поки пристрій перепідключався,
втрачається безслідно, і жоден `command_id` цього не виправить. Тому
надійність тут будується на звірці бажаного стану (`device.sync` →
`device.state`), а не на сподіванні, що нічого не проґавлено. Практична
різниця видима на стійці: після мережевого збою пристрій повертається до
маскота сам, замість лишитися з чужим платіжним QR, бо `cancel` не дійшов.
"""

from __future__ import annotations

import asyncio
import json
import queue
import random
import threading
import time
from dataclasses import dataclass
from urllib.parse import quote

import websockets

from ..events import Command, CommandKind, CommandResult, now

#: Верхня межа вхідної черги. Без неї відновлення зв'язку після довгого
#: простою вивалило б на пристрій усе, що накопичилось.
INBOX_LIMIT = 64

#: Відповідь CRM на `device.sync`: бажаний стан пристрою.
DEVICE_STATE_EVENT = "device.state"


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
    ) -> None:
        self._url = url.rstrip("/")
        self._device_id = device_id
        self._device_no = device_no
        self._token = token
        self._min = reconnect_min_s
        self._max = reconnect_max_s

        self.inbox: queue.Queue[Command] = queue.Queue(maxsize=INBOX_LIMIT)
        self.outbox: queue.Queue[dict] = queue.Queue(maxsize=INBOX_LIMIT)

        self.status = LinkStatus()
        self._sync_seq = 0
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

    def endpoint(self) -> str:
        """Адреса з токеном і каналом. Токен у логи не потрапляє."""
        channel = f"device:{self._device_no}"
        return f"{self._url}/ws?token={quote(self._token, safe='')}&channels={quote(channel, safe=':')}"

    def _run(self) -> None:
        asyncio.run(self._loop())

    async def _loop(self) -> None:
        if not self._token:
            # Без токена стукати в CRM немає сенсу: сервер відмовить на
            # рукостисканні. Чесніше стояти offline і сказати про причину.
            self.status = LinkStatus(connected=False, last_error="no_token")
            return

        delay = self._min
        while not self._stop.is_set():
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
        # Одразу питаємо, що показувати. Це не ввічливість, а єдиний
        # спосіб дізнатися про команди, надіслані поки нас не було.
        await ws.send(json.dumps({"type": "device.sync"}))

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

        if event == DEVICE_STATE_EVENT:
            return self._state_command(data)

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

    def _state_command(self, data: dict) -> Command | None:
        """Відповідь на `device.sync` — бажаний стан, а не команда.

        Виражаємо його наявним `set_mode` навмисно: інакше в системі
        з'явився б другий шлях зміни режиму, який довелося б окремо
        узгоджувати з пріоритетами координатора. Тут же він проходить
        рівно ті самі перевірки, що й команда від CRM.

        `command_id` із префіксом `sync:` — щоб у журналі було видно, що
        режим змінився звіркою, а не надісланою командою.
        """
        mode = str(data.get("mode") or "").strip()
        if not mode:
            return None
        payload = data.get("payload")
        if not isinstance(payload, dict):
            payload = {}
        self._sync_seq += 1
        return Command(
            kind=CommandKind.SET_MODE,
            command_id=f"sync:{self._sync_seq}",
            payload={"mode": mode, **payload},
            expires_at=None,
        )
