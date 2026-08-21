"""Fake CRM: WebSocket-сервер для розробки без справжнього backend.

Дозволяє перевірити те, що в реальній CRM перевірити важко: дублікати
команд, прострочені команди, посилання з недозволеного домену і розрив
зв'язку посеред сценарію.

    python app/tools/fake_crm.py
    python app/tools/fake_crm.py --scenario phishing
"""

from __future__ import annotations

import argparse
import asyncio
import json
import uuid

import websockets

HOST, PORT = "127.0.0.1", 8765


def log(message: str) -> None:
    """Друкує одразу: у перенаправленому виводі буферизація ховає весь лог."""
    print(f"[fake-crm] {message}", flush=True)


def command(kind: str, payload: dict, expires_in_ms: int | None = None, cid: str | None = None) -> str:
    msg = {
        "type": kind,
        "command_id": cid or uuid.uuid4().hex[:12],
        "payload": payload,
    }
    if expires_in_ms is not None:
        msg["expires_in_ms"] = expires_in_ms
    return json.dumps(msg)


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


SCENARIOS = {
    "normal": scenario_normal,
    "duplicate": scenario_duplicate,
    "expired": scenario_expired,
    "phishing": scenario_phishing,
}


async def handler(ws, scenario: str) -> None:
    log(f"пристрій підключився, сценарій: {scenario}")
    sender = asyncio.create_task(SCENARIOS[scenario](ws))
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                log(f"сміття: {raw!r}")
                continue
            kind = msg.get("type")
            if kind == "device.ready":
                log(f"ready: {msg.get('device_id')} {msg.get('capabilities')}")
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


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), default="normal")
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()

    async with websockets.serve(lambda ws: handler(ws, args.scenario), HOST, args.port):
        log(f"слухає ws://{HOST}:{args.port} ({args.scenario})")
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
