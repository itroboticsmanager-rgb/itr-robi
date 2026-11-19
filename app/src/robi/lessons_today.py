"""«Що зараз на заняттях» — сьогоднішні групові заняття з CRM.

CRM віддає лише курс, групу, час і колір курсу — без імен дітей і
викладачів (`/api/device/lessons-today`). Що «зараз», а що «далі», рахує
сама сторінка кіоску за часом, тож список лишається правдивим між
запитами раз на 5 хв.

Відповідь перевіряється суворо, як і все з мережі: криве поле — запис
відкидається, а не потрапляє на екран у холі. Кеш на диску не потрібен:
список живе один день, а без мережі кнопка просто не показується.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime

MAX_LESSONS = 40
MAX_PAYLOAD_BYTES = 64 * 1024
_COLOR = re.compile(r"^#[0-9a-fA-F]{6}$")
_ICON = re.compile(r"^[a-z0-9-]{1,40}$")


@dataclass(frozen=True, slots=True)
class TodayLesson:
    id: int
    course: str
    group: str
    start: str
    end: str
    color: str
    icon: str

    def for_web(self) -> dict:
        return {
            "id": self.id, "course": self.course, "group": self.group,
            "start": self.start, "end": self.end, "color": self.color, "icon": self.icon,
        }


def _iso(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 40:
        return None
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return value


def _text(value: object, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def parse_lessons(raw: object) -> list[TodayLesson]:
    """Перевірений список занять; записи з кривими полями пропускаються."""
    items = raw.get("lessons") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise ValueError("lessons is not a list")
    out: list[TodayLesson] = []
    for item in items[:MAX_LESSONS]:
        if not isinstance(item, dict):
            continue
        lesson_id = item.get("id")
        start, end = _iso(item.get("start")), _iso(item.get("end"))
        course = _text(item.get("course"), 120)
        if not isinstance(lesson_id, int) or not start or not end or not course or end <= start:
            continue
        color = item.get("color") if isinstance(item.get("color"), str) and _COLOR.match(item["color"]) else ""
        icon = item.get("icon") if isinstance(item.get("icon"), str) and _ICON.match(item["icon"]) else ""
        out.append(TodayLesson(lesson_id, course, _text(item.get("group"), 120), start, end, color, icon))
    return out


def fetch_lessons(url: str, secret: str, timeout: float = 10.0) -> tuple[list[TodayLesson] | None, str]:
    """Свіжий список або `(None, причина)`."""
    if not url or not secret:
        return None, "not_configured"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {secret}"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(MAX_PAYLOAD_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return None, f"http_{exc.code}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return None, f"net_{type(exc).__name__}"
    if len(body) > MAX_PAYLOAD_BYTES:
        return None, "too_large"
    try:
        return parse_lessons(json.loads(body.decode("utf-8"))), ""
    except (ValueError, UnicodeDecodeError):
        return None, "bad_response"
