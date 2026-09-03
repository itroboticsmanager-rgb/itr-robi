"""Fake CRM: локальний сервер, який говорить протоколом справжньої CRM.

Раніше тут був саморобний протокол. Тепер він повторює `ws-server` з
репозиторію CRM (`D-056`), бо контракт має існувати як щось виконуване:
документ, з яким код тихо розходиться за місяць, контрактом не є.

Що саме відтворено:

- вхід `ws://host/ws?token=<jwt>&channels=<через кому>`;
- JWT HS256 з payload `{sub, role, exp, iat}` на спільному секреті;
- авторизація кожного каналу окремо; якщо не пройшов жоден — 401/403;
- **роль `device` бачить лише власний `device:<sub>`** — головне правило
  безпеки `D-056`: пристрій стоїть у публічному місці, і його токен
  слід вважати таким, що рано чи пізно витече;
- доставка підписникам у вигляді `{event, data, ts}`.

Понад це сервер уміє те, чого на живому backend не відтвориш: дублікат
`command_id`, прострочену команду, чужий домен у QR.

    python app/tools/fake_crm.py
    python app/tools/fake_crm.py --scenario phishing

**Звірки стану тут навмисно немає.** `POST /broadcast` у справжній CRM є
fire-and-forget, і спокуса — навчити пристрій питати «що мені показувати»
при кожному підключенні. Але небезпечний випадок стається саме тоді, коли
зв'язку немає, і питання при його поверненні вже нічого не рятує. За це
відповідає стеля часу життя активації на самому пристрої, а не діалог
із сервером.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import hmac
import json
import sys
import time
import uuid

import websockets

HOST, PORT = "127.0.0.1", 8765

#: Той самий секрет, що й `REALTIME_JWT_SECRET` у CRM. Для розробки —
#: фіксований; на пристрої справжній приходить під час provisioning і в
#: Git не потрапляє (принцип 6).
DEV_SECRET = "dev-realtime-secret"

ROLES = frozenset({"admin", "teacher", "student", "device"})

NEWLINE = chr(10)


# Консоль Windows приходить у cp1251, і на кирилиці чи стрілці `print`
# кидає UnicodeEncodeError. Для сервера це не косметика: виняток у логу
# вбивав обробник з'єднання, і клієнт отримував 1011 замість команди.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def log(message: str) -> None:
    """Друкує одразу: у перенаправленому виводі буферизація ховає весь лог.

    Ловить усе: журнал не має права ронити те, про що він звітує.
    """
    try:
        print(f"[fake-crm] {message}", flush=True)
    except Exception:  # noqa: BLE001 — тиша краща за впалий сервер
        pass


# -- JWT -------------------------------------------------------------------
#
# Реалізація дослівно повторює `ws-server/src/jwt.ts`: HS256, base64url без
# padding, перевірка алгоритму й строку. Тримається тут, а не в застосунку,
# бо підписує токени сервер, а пристрій лише пред'являє готовий.


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def mint(sub: int, role: str = "device", ttl_s: int = 3600, secret: str = DEV_SECRET) -> str:
    now = int(time.time())
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    payload = _b64(
        json.dumps(
            {"sub": sub, "role": role, "iat": now, "exp": now + ttl_s}, separators=(",", ":")
        ).encode()
    )
    signing_input = f"{header}.{payload}".encode()
    sig = _b64(hmac.new(secret.encode(), signing_input, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def verify(token: str, secret: str = DEV_SECRET) -> dict | None:
    """Повертає payload або None. Причина відмови назовні не йде."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    header_b64, payload_b64, sig_b64 = parts
    try:
        header = json.loads(_unb64(header_b64))
        if header.get("alg") != "HS256" or header.get("typ") != "JWT":
            return None
        expected = hmac.new(
            secret.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(_unb64(sig_b64), expected):
            return None
        payload = json.loads(_unb64(payload_b64))
    except (ValueError, json.JSONDecodeError):
        return None

    if not isinstance(payload.get("sub"), int):
        return None
    if payload.get("role") not in ROLES:
        return None
    if not isinstance(payload.get("exp"), int) or payload["exp"] <= int(time.time()):
        return None
    return payload


def authorize_channel(channel: str, payload: dict) -> bool:
    """Головне правило `D-056`: пристрій відкриває лише власний канал."""
    kind, _, ident = channel.partition(":")
    if not kind or not ident:
        return False
    if payload["role"] == "admin":
        return True
    if payload["role"] == "device":
        return kind == "device" and ident == str(payload["sub"])
    return False


# -- протокол --------------------------------------------------------------


def envelope(event: str, data: dict) -> str:
    """Те, що справжній сервер шле підписникам."""
    return json.dumps({"event": event, "data": data, "ts": int(time.time() * 1000)})


def command(kind: str, payload: dict, expires_in_ms: int | None = None, cid: str | None = None) -> str:
    """Конверт команди живе в `data`, бо транспорт про команди не знає.

    `/broadcast` у CRM передає лише `{channel, event, data}` — жодного
    `command_id`, TTL чи ідемпотентності там немає. Тому весь конверт
    складається тут і перевіряється на пристрої.
    """
    data = {"command_id": cid or uuid.uuid4().hex[:12], "payload": payload}
    if expires_in_ms is not None:
        data["expires_in_ms"] = expires_in_ms
    return envelope(kind, data)


# -- сценарії --------------------------------------------------------------


async def scenario_normal(ws) -> None:
    """Звичайний цикл: показати QR, повернутися до обличчя, повторити."""
    while True:
        await asyncio.sleep(8)
        await ws.send(command(
            "command.show_qr",
            {"value": "https://example.org/robi", "title": "Запис на пробне заняття",
             "duration_ms": 6000},
            expires_in_ms=30_000,
        ))


async def scenario_duplicate(ws) -> None:
    """Той самий command_id двічі: фізична дія не має повторитися."""
    cid = uuid.uuid4().hex[:12]
    await asyncio.sleep(3)
    for _ in range(2):
        await ws.send(command(
            "command.show_qr",
            {"value": "https://example.org/dup", "duration_ms": 5000},
            expires_in_ms=30_000,
            cid=cid,
        ))
        await asyncio.sleep(1)


async def scenario_expired(ws) -> None:
    """Прострочена команда має бути відхилена, а не показана."""
    await asyncio.sleep(3)
    await ws.send(command(
        "command.show_qr",
        {"value": "https://example.org/late"},
        expires_in_ms=1,
    ))


async def scenario_phishing(ws) -> None:
    """Головна перевірка D-038: CRM просить показати чужий домен."""
    await asyncio.sleep(3)
    for url in (
        "https://evil.example.net/pay",
        "http://example.org/insecure",
        "https://user:pass@example.org/creds",
        "https://example.org.attacker.net/pay",
    ):
        await ws.send(command("command.show_qr", {"value": url, "duration_ms": 4000}))
        await asyncio.sleep(2)


async def scenario_idle(ws) -> None:
    """Нічого не надсилає: для тестів, де важлива лише поведінка з'єднання."""
    await asyncio.Future()


SCENARIOS = {
    "normal": scenario_normal,
    "duplicate": scenario_duplicate,
    "expired": scenario_expired,
    "phishing": scenario_phishing,
    "idle": scenario_idle,
}


def parse_query(raw_path: str) -> tuple[str, dict[str, str]]:
    route, _, query = raw_path.partition("?")
    params: dict[str, str] = {}
    for chunk in query.split("&"):
        key, _, value = chunk.partition("=")
        if key:
            params[key] = value
    return route, params


def process_request(connection, request, secret: str = DEV_SECRET):
    """Відмова **до** рукостискання, як у справжньому сервері.

    Це не дрібниця реалізації. Справжній `ws-server` пише `401`/`403` у
    сокет ще на етапі upgrade, тож клієнт отримує помилку з'єднання. Якби
    фейк приймав з'єднання й закривав його одразу після, пристрій бачив
    би зовсім інше — успішне підключення й миттєвий розрив, — і логіка
    reconnect тестувалася б проти неіснуючої поведінки.
    """
    route, params = parse_query(request.path)
    if route != "/ws":
        return connection.respond(404, "not found" + NEWLINE)

    payload = verify(params.get("token", ""), secret)
    if payload is None:
        log("відмова: токен непридатний")
        return connection.respond(401, "unauthorized" + NEWLINE)

    requested = [c for c in params.get("channels", "").split(",") if c]
    allowed = [c for c in requested if authorize_channel(c, payload)]
    if not requested or not allowed:
        log(f"відмова: жоден канал не дозволено ({requested})")
        return connection.respond(403, "forbidden" + NEWLINE)

    connection.robi_payload = payload
    connection.robi_channels = allowed
    return None


async def handler(ws, scenario: str, secret: str = DEV_SECRET, on_message=None) -> None:
    """`on_message` — гачок для тестів.

    Читач сокета має бути один: якщо тест підключить власний паралельно,
    вони почнуть відбирати повідомлення один в одного, і збій виглядатиме
    як загублені повідомлення клієнта.
    """
    payload = getattr(ws, "robi_payload", None)
    allowed = getattr(ws, "robi_channels", [])
    if payload is None:
        # Сюди можна потрапити лише якщо сервер підняли без process_request.
        await ws.close(code=4401, reason="unauthorized")
        return

    log(f"підключився {payload['role']}:{payload['sub']} → {allowed}, сценарій: {scenario}")
    sender = asyncio.create_task(SCENARIOS[scenario](ws))
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                log(f"сміття: {raw!r}")
                continue
            if on_message is not None:
                on_message(msg)
            kind = msg.get("type")
            if kind == "device.hello":
                log(f"hello: {msg.get('device_id')} {msg.get('capabilities')}")
            elif kind == "command.status":
                reason = f" ({msg['reason']})" if msg.get("reason") else ""
                log(f"{msg.get('command_id')}: {msg.get('status')}{reason}")
            else:
                log(f"{msg}")
    except websockets.ConnectionClosed:
        pass
    finally:
        sender.cancel()
        log("пристрій відключився")


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="normal")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--device", type=int, default=1, help="id пристрою для --print-token")
    parser.add_argument("--print-token", action="store_true", help="надрукувати токен і вийти")
    args = parser.parse_args()

    if args.print_token:
        print(mint(args.device))
        return 0

    token = mint(args.device)
    async with websockets.serve(
        lambda ws: handler(ws, args.scenario),
        HOST,
        args.port,
        process_request=process_request,
    ):
        log(f"слухає ws://{HOST}:{args.port} ({args.scenario})")
        log(f"токен пристрою {args.device}: {token}")
        log(f"url: ws://{HOST}:{args.port}/ws?token=<токен>&channels=device:{args.device}")
        await asyncio.Future()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        pass
