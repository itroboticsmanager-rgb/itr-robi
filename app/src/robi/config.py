"""Завантаження й валідація конфігурації.

Секрети сюди не потрапляють: у файлі лише те, що не соромно тримати в Git
(див. принцип 6 у README). CRM-токени приходять окремо під час provisioning.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    """Конфігурація непридатна. Пристрій не має стартувати з такою."""


@dataclass(slots=True)
class DisplayConfig:
    width: int = 800
    height: int = 480
    fullscreen: bool = False
    target_fps: int = 60


@dataclass(slots=True)
class CrmConfig:
    url: str = "ws://127.0.0.1:8765"
    enabled: bool = True
    reconnect_min_s: float = 1.0
    reconnect_max_s: float = 30.0
    allowed_url_schemes: tuple[str, ...] = ("https",)
    allowed_domains: tuple[str, ...] = ()


@dataclass(slots=True)
class FeaturesConfig:
    camera: bool = True
    nfc: bool = True
    voice: bool = False
    rgb: bool = True


@dataclass(slots=True)
class VisionConfig:
    """Вибір джерела детекції (D-053).

    `fake` програє записаний сценарій без камери й не потребує OpenCV.
    `camera` бере кадри з пристрою; для нього треба extra `camera`.
    """

    backend: str = "fake"
    device_index: int = 0
    fps: float = 8.0
    detect_width: int = 320
    min_face_frac: float = 0.12


@dataclass(slots=True)
class Config:
    device_id: str = "robi-dev"
    site: str = "local"
    display: DisplayConfig = field(default_factory=DisplayConfig)
    crm: CrmConfig = field(default_factory=CrmConfig)
    features: FeaturesConfig = field(default_factory=FeaturesConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)

    @staticmethod
    def load(path: str | Path | None) -> "Config":
        if path is None:
            return Config()
        p = Path(path)
        if not p.exists():
            raise ConfigError(f"конфігурацію не знайдено: {p}")
        try:
            raw = tomllib.loads(p.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{p}: {exc}") from exc
        return Config.from_dict(raw)

    @staticmethod
    def from_dict(raw: dict) -> "Config":
        cfg = Config()
        cfg.device_id = str(raw.get("device_id", cfg.device_id))
        cfg.site = str(raw.get("site", cfg.site))

        d = raw.get("display", {})
        cfg.display = DisplayConfig(
            width=int(d.get("width", 800)),
            height=int(d.get("height", 480)),
            fullscreen=bool(d.get("fullscreen", False)),
            target_fps=int(d.get("target_fps", 60)),
        )

        c = raw.get("crm", {})
        cfg.crm = CrmConfig(
            url=str(c.get("url", "ws://127.0.0.1:8765")),
            enabled=bool(c.get("enabled", True)),
            reconnect_min_s=float(c.get("reconnect_min_s", 1.0)),
            reconnect_max_s=float(c.get("reconnect_max_s", 30.0)),
            allowed_url_schemes=tuple(c.get("allowed_url_schemes", ["https"])),
            allowed_domains=tuple(c.get("allowed_domains", [])),
        )

        f = raw.get("features", {})
        cfg.features = FeaturesConfig(
            camera=bool(f.get("camera", True)),
            nfc=bool(f.get("nfc", True)),
            voice=bool(f.get("voice", False)),
            rgb=bool(f.get("rgb", True)),
        )

        v = raw.get("vision", {})
        cfg.vision = VisionConfig(
            backend=str(v.get("backend", "fake")),
            device_index=int(v.get("device_index", 0)),
            fps=float(v.get("fps", 8.0)),
            detect_width=int(v.get("detect_width", 320)),
            min_face_frac=float(v.get("min_face_frac", 0.12)),
        )

        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not self.device_id:
            raise ConfigError("device_id не може бути порожнім")
        if self.display.width < 320 or self.display.height < 240:
            raise ConfigError("надто мала роздільність дисплея")
        if not 1 <= self.display.target_fps <= 240:
            raise ConfigError("target_fps поза розумним діапазоном")
        if self.crm.reconnect_min_s <= 0 or self.crm.reconnect_max_s < self.crm.reconnect_min_s:
            raise ConfigError("некоректне вікно reconnect")
        if self.features.voice:
            raise ConfigError("voice ще не реалізовано; лишайте features.voice = false")
        if self.vision.backend not in ("fake", "camera"):
            raise ConfigError(f"невідомий vision.backend: {self.vision.backend!r}")
        if not 0.5 <= self.vision.fps <= 60:
            raise ConfigError("vision.fps поза розумним діапазоном")
        if not 120 <= self.vision.detect_width <= 1920:
            raise ConfigError("vision.detect_width поза розумним діапазоном")
        if not 0.02 <= self.vision.min_face_frac <= 0.9:
            raise ConfigError("vision.min_face_frac поза розумним діапазоном")
