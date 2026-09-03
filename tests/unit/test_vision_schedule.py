"""Розклад камери й сповільнення в спокої.

Камера — найдорожча постійна робота пристрою (18 % ядра за вимірюванням
у `D-053`), і водночас та частина, яку найважче пояснити батькам. Тому її
робочий час і поведінка в спокої заслуговують тестів, а не сподівання.
"""

from datetime import time as clock_time

import pytest

from robi.config import Config, ConfigError, VisionConfig


def cfg(start: str, end: str) -> VisionConfig:
    return VisionConfig(active_from=start, active_to=end)


def test_default_has_no_schedule():
    """Дефолт не має залежати від годинника машини, де запущено код."""
    v = VisionConfig()
    assert v.camera_allowed_at(clock_time(3, 0))
    assert v.camera_allowed_at(clock_time(14, 0))
    assert v.camera_allowed_at(clock_time(23, 59))


@pytest.mark.parametrize(
    "now,allowed",
    [
        (clock_time(6, 59), False),
        (clock_time(7, 0), True),
        (clock_time(13, 0), True),
        (clock_time(19, 59), True),
        (clock_time(20, 0), False),
        (clock_time(23, 0), False),
        (clock_time(2, 0), False),
    ],
)
def test_daytime_window(now, allowed):
    assert cfg("07:00", "20:00").camera_allowed_at(now) is allowed


@pytest.mark.parametrize(
    "now,allowed",
    [
        (clock_time(21, 0), True),
        (clock_time(0, 0), True),
        (clock_time(6, 59), True),
        (clock_time(7, 0), False),
        (clock_time(12, 0), False),
        (clock_time(19, 59), False),
        (clock_time(20, 0), True),
    ],
)
def test_window_across_midnight(now, allowed):
    """Вікно через північ — не наш випадок, але помилка тут була б тихою."""
    assert cfg("20:00", "07:00").camera_allowed_at(now) is allowed


def test_equal_bounds_mean_always_on():
    assert cfg("09:00", "09:00").camera_allowed_at(clock_time(3, 0))


def test_broken_time_is_rejected_at_load():
    """Крива година має валити конфігурацію, а не тихо вимикати камеру."""
    with pytest.raises(ConfigError):
        Config.from_dict({"vision": {"active_from": "не час"}})
    with pytest.raises(ConfigError):
        Config.from_dict({"vision": {"active_to": "25:00"}})


def test_idle_fps_cannot_exceed_active():
    with pytest.raises(ConfigError):
        Config.from_dict({"vision": {"fps": 2.0, "idle_fps": 4.0}})


# --- сповільнення в спокої -----------------------------------------------


def test_idle_slowdown_kicks_in_after_the_grace():
    """Поки когось видно — повна частота; далі сповільнення."""
    from robi.vision.camera import CameraVision

    v = CameraVision(fps=4.0, idle_fps=1.0, idle_after_s=3.0)
    active = 1.0 / 4.0
    idle = 1.0 / 1.0

    import time

    v._last_seen = time.monotonic()
    assert v._next_interval() == pytest.approx(active)

    # Обличчя не бачили довше за grace.
    v._last_seen = time.monotonic() - 10.0
    assert v._next_interval() == pytest.approx(idle)

    # Повернення до повної частоти миттєве.
    v._last_seen = time.monotonic()
    assert v._next_interval() == pytest.approx(active)
