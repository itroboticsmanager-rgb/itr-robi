"""Налаштування стійки з CRM: яскравість, гучність, розклад, поведінка кіоску (D-068).

Чому набір, а не команда. Документ `crm-integration.md` уже провів межу:
команда — тимчасова дія з таймером, а постійний режим — це конфігурація.
Яскравість, гучність і години роботи якраз постійні: вони мають пережити
перезапуск і розрив зв'язку. Тому вони ходять так само, як меню й банери:
пристрій сам забирає набір із CRM, перевіряє його й тримає останній вдалий
на диску. Сигнал `settings.changed` у real-time каналі лише будить це
забирання, щоб зміна в CRM дійшла за секунди, а не за хвилини.

Чому за замовчуванням нічого не керується. Пристрій, якому CRM ще нічого не
сказала, не має смикати яскравість і гучність, виставлені руками на самому
планшеті. Тому керування екраном і звуком вмикається окремими прапорцями.

Перевірка сувора, як у контенту (`D-048`): набір із бодай одним полем поза
межами відкидається цілком, і діє попередній. Невідомі поля пропускаються —
так новіша CRM не ламає старіший пристрій.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field, fields, replace
from datetime import datetime, time as clock_time
from pathlib import Path

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
AFTER_HOURS = ("same", "dim", "sleep")
MAX_PAYLOAD_BYTES = 64 * 1024
CACHE = "settings.json"
PENDING = "settings.pending.json"

_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class SettingsError(ValueError):
    """Набір непридатний. Діє попередній."""


#: Межі числових полів. Нижня межа яскравості не нуль: темний екран у холі
#: виглядає як зламаний пристрій, а не як «сон».
RANGES: dict[str, tuple[int, int]] = {
    "brightness": (5, 100),
    "night_brightness": (5, 100),
    "volume": (0, 100),
    "night_volume": (0, 100),
    "idle_timeout_s": (15, 600),
    "banner_interval_s": (4, 120),
    "video_volume": (0, 100),
}


@dataclass(frozen=True, slots=True)
class KioskSettings:
    """Повний набір із типовими значеннями. Дзеркало `kiosk-settings-core.ts` у CRM."""

    manage_display: bool = False
    brightness: int = 80
    night_brightness: int = 30
    manage_volume: bool = False
    volume: int = 50
    night_volume: int = 15
    schedule_enabled: bool = False
    #: День → (відкриття, закриття) або None — вихідний.
    schedule: dict[str, tuple[str, str] | None] = field(
        default_factory=lambda: {day: ("08:00", "21:00") for day in DAYS}
    )
    after_hours: str = "dim"
    idle_timeout_s: int = 45
    banner_interval_s: int = 14
    reduced_motion: bool = False
    video_sound: bool = True
    video_volume: int = 80
    show_wifi: bool = True
    show_scanner: bool = True
    camera_open_hours_only: bool = True

    @staticmethod
    def from_dict(raw: object) -> "KioskSettings":
        if not isinstance(raw, dict):
            raise SettingsError("налаштування мають бути об'єктом")
        values: dict[str, object] = {}
        for f in fields(KioskSettings):
            if f.name not in raw:
                continue
            value = raw[f.name]
            if f.name == "schedule":
                values["schedule"] = _schedule(value)
            elif f.name == "after_hours":
                if value not in AFTER_HOURS:
                    raise SettingsError(f"after_hours: невідоме значення {value!r}")
                values["after_hours"] = value
            elif f.name in RANGES:
                low, high = RANGES[f.name]
                # bool у Python — підклас int, але `true` гучністю бути не може.
                if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                    raise SettingsError(f"{f.name}: очікується ціле {low}–{high}")
                values[f.name] = value
            else:
                if not isinstance(value, bool):
                    raise SettingsError(f"{f.name}: очікується true/false")
                values[f.name] = value
        return replace(KioskSettings(), **values)

    def is_open(self, now: datetime) -> bool:
        """Чи зараз години роботи. Без розкладу — завжди."""
        if not self.schedule_enabled:
            return True
        hours = self.schedule.get(DAYS[now.weekday()])
        if hours is None:
            return False
        start, end = (_parse(t) for t in hours)
        moment = now.time()
        if start < end:
            return start <= moment < end
        # Закриття після півночі, наприклад 10:00–01:00.
        return moment >= start or moment < end

    def effective(self, now: datetime) -> "Effective":
        open_now = self.is_open(now)
        night = not open_now and self.after_hours != "same"
        return Effective(
            open_now=open_now,
            sleeping=not open_now and self.after_hours == "sleep",
            brightness=(self.night_brightness if night else self.brightness) if self.manage_display else None,
            volume=(self.night_volume if night else self.volume) if self.manage_volume else None,
            camera_allowed=open_now or not self.camera_open_hours_only,
        )

    def for_web(self, effective: "Effective") -> dict:
        """Те, що потрібно веб-кіоску. Гучність системи йому ні до чого."""
        return {
            "idle_timeout_s": self.idle_timeout_s,
            "banner_interval_s": self.banner_interval_s,
            "reduced_motion": self.reduced_motion,
            "video_sound": self.video_sound,
            "video_volume": self.video_volume,
            "show_wifi": self.show_wifi,
            "show_scanner": self.show_scanner,
            "open_now": effective.open_now,
            "sleeping": effective.sleeping,
        }


@dataclass(frozen=True, slots=True)
class Effective:
    """Що діє саме зараз з урахуванням розкладу."""

    open_now: bool
    sleeping: bool
    #: None — не керувати, лишити як виставлено на планшеті.
    brightness: int | None
    volume: int | None
    camera_allowed: bool


def _parse(text: str) -> clock_time:
    hh, mm = text.split(":")
    return clock_time(int(hh), int(mm))


def _schedule(raw: object) -> dict[str, tuple[str, str] | None]:
    if not isinstance(raw, dict):
        raise SettingsError("schedule: очікується об'єкт днів")
    out: dict[str, tuple[str, str] | None] = {}
    for day in DAYS:
        value = raw.get(day)
        if value is None:
            out[day] = None
            continue
        if (
            not isinstance(value, list) or len(value) != 2
            or not all(isinstance(t, str) and _HHMM.match(t) for t in value)
        ):
            raise SettingsError(f"schedule.{day}: очікується [\"HH:MM\", \"HH:MM\"] або null")
        if value[0] == value[1]:
            raise SettingsError(f"schedule.{day}: відкриття й закриття збігаються")
        out[day] = (value[0], value[1])
    return out


@dataclass(frozen=True, slots=True)
class SettingsSet:
    revision: int
    settings: KioskSettings


class SettingsStore:
    """Останній вдалий набір на диску: пристрій піднімається з ним без мережі."""

    def __init__(self, directory: str | Path) -> None:
        self.dir = Path(directory)
        self.path = self.dir / CACHE

    def load(self) -> SettingsSet | None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return _set_from(raw)
        except (OSError, json.JSONDecodeError, SettingsError):
            return None

    def refresh(
        self, url: str, secret: str, *, applied: int = 0, report: str = "", timeout: float = 10.0
    ) -> tuple[SettingsSet | None, str]:
        """Свіжий набір або `(None, причина)`; невдача лишає кеш як був.

        `applied` і `report` ідуть заголовками: так CRM бачить, яку версію
        пристрій справді застосував і чи вдалося керувати екраном і звуком.
        """
        if not url or not secret:
            return None, "not_configured"
        request = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {secret}",
            "X-Robi-Applied-Revision": str(applied),
            "X-Robi-Controls": report[:200],
        })
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read(MAX_PAYLOAD_BYTES + 1)
        except urllib.error.HTTPError as exc:
            return None, f"http_{exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return None, f"net_{type(exc).__name__}"
        except UnicodeEncodeError:
            return None, "bad_secret"
        if len(body) > MAX_PAYLOAD_BYTES:
            return None, "too_large"
        try:
            raw = json.loads(body.decode("utf-8"))
            settings_set = _set_from(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, "bad_response"
        except SettingsError as exc:
            return None, f"invalid: {exc}"
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            pending = self.dir / PENDING
            pending.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            pending.replace(self.path)
        except OSError as exc:
            return settings_set, f"write_{type(exc).__name__}"
        return settings_set, ""


def _set_from(raw: object) -> SettingsSet:
    if not isinstance(raw, dict):
        raise SettingsError("відповідь має бути об'єктом")
    revision = raw.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        raise SettingsError("revision має бути невід'ємним цілим")
    return SettingsSet(revision, KioskSettings.from_dict(raw.get("settings", {})))
