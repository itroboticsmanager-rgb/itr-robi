"""Обслуговування стійки з CRM: перезапуск і знімок екрана."""

from __future__ import annotations

import os
import time

from robi.config import Config
from robi.events import Command, CommandKind, CommandStatus


def _app(web: bool = True, crm: bool = False):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    from robi.bootstrap import App

    cfg = Config.from_dict({
        "device_id": "robi-1",
        "site": "kyiv",
        "crm": {
            "enabled": crm,
            "url": "wss://realtime.example.org",
            "token_url": "https://crm.example.org/api/device/realtime-token",
        },
        "features": {"camera": False},
        "web": {"enabled": web, "port": 0},
    })
    return App(cfg, headless=True)


def test_restart_is_accepted_only_under_the_web_kiosk():
    app = _app(web=True)
    result = app.accept_command(Command(CommandKind.RESTART, "restart-abc123-0a0b0c", {}))
    assert result.status is CommandStatus.ACCEPTED
    assert app._restart_due is not None and app._restart_due > time.monotonic()

    bare = _app(web=False)
    result = bare.accept_command(Command(CommandKind.RESTART, "restart-abc123-0a0b0d", {}))
    assert result.status is CommandStatus.REJECTED
    assert bare._restart_due is None


def test_screenshot_without_crm_is_rejected():
    app = _app(crm=False)
    result = app.accept_command(Command(CommandKind.SCREENSHOT, "shot-abc123-0a0b0c", {}))
    assert result.status is CommandStatus.REJECTED
    assert result.reason == "not_configured"


def test_crm_api_uses_the_token_host_and_https_only():
    app = _app()
    assert app._crm_api("/api/device/screenshot-upload") == "https://crm.example.org/api/device/screenshot-upload"
    app.config.crm.token_url = "http://crm.example.org/api/device/realtime-token"
    app.config.settings.url = ""
    assert app._crm_api("/api/device/screenshot-upload") == ""


def test_release_name_is_the_release_folder():
    from robi.bootstrap import RELEASE_NAME

    # У репозиторії код лежить у <repo>/app/src/robi → «реліз» — тека репозиторію.
    assert RELEASE_NAME and "/" not in RELEASE_NAME and "\\" not in RELEASE_NAME
