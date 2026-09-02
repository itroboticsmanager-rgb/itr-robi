"""Межа vision — тест заборони D-027.

Заборона розпізнавання людей реалізована архітектурно: тип, який шар
віддає назовні, просто не має поля під кадр чи ідентифікатор. Ці тести
охороняють саме це — щоб згодом ніхто не додав `frame` «на часок для
дебагу» і не помітив, що межа зникла.
"""

import dataclasses

from robi.events import FaceSeen
from robi.vision.fake import FakeVision

#: Поля, поява яких у події означала б, що межа зламана.
FORBIDDEN = {"frame", "image", "buffer", "jpeg", "png", "embedding",
             "descriptor", "identity", "person_id", "name", "age", "gender", "emotion"}


def test_face_event_carries_no_frame_and_no_identity():
    fields = {f.name for f in dataclasses.fields(FaceSeen)}
    assert not (fields & FORBIDDEN), f"межу D-027 зламано: {fields & FORBIDDEN}"


def test_face_event_fields_are_only_geometry():
    fields = {f.name for f in dataclasses.fields(FaceSeen)}
    assert fields == {"source", "at", "count", "x", "y", "size"}


def test_capture_is_off_until_asked():
    """Камера не вмикається сама: захоплення починає лише режим."""
    v = FakeVision()
    v.initialize()
    assert not v.capturing
    assert v.poll(1.0) == []


def test_stop_capture_is_real():
    """Індикатор гасне за станом захоплення (D-029), тож стоп має бути справжнім."""
    v = FakeVision()
    v.initialize()
    v.start_capture()
    assert v.capturing
    v.stop_capture()
    assert not v.capturing
    assert v.poll(1.0) == []


def test_uninitialised_vision_never_captures():
    v = FakeVision()
    v.start_capture()
    assert not v.capturing


def test_shutdown_stops_capture():
    v = FakeVision()
    v.initialize()
    v.start_capture()
    v.shutdown()
    assert not v.capturing


def test_stats_expose_counts_but_not_content():
    v = FakeVision()
    v.initialize()
    v.start_capture()
    for _ in range(30):
        v.poll(0.2)
    stats = v.stats()
    assert stats.frames > 0
    assert set(dataclasses.asdict(stats)) == {"frames", "detections", "capturing"}


def test_face_leaves_frame_and_returns():
    """Сценарій має включати зникнення людини — інакше повернення погляду не перевірено."""
    v = FakeVision()
    v.initialize()
    v.start_capture()
    counts = set()
    for _ in range(400):
        for event in v.poll(0.1):
            counts.add(event.count)
    assert counts == {0, 1}


# --- те саме, але для будь-якої реалізації, а не лише для fake ------------
#
# Досі ці гарантії перевірялися на `FakeVision`, у якої камери немає в
# принципі, — тобто найлегший можливий випадок. Реальний адаптер (D-053)
# кадр таки тримає, тож саме він і є тим місцем, де межу D-027 можна
# зламати непомітно. Тести нижче тримають обидві реалізації в одних рамках.

import pytest

from robi.vision.camera import CameraVision


def implementations():
    """CameraVision конструюється без OpenCV: імпорт cv2 живе в initialize()."""
    return [FakeVision(), CameraVision()]


@pytest.mark.parametrize("vision", implementations(), ids=["fake", "camera"])
def test_no_public_attribute_can_hold_a_frame(vision):
    # `name` тут — власна назва адаптера ("vision"), а не ім'я людини,
    # тому з переліку заборонених для атрибутів вона виключена.
    forbidden_attrs = FORBIDDEN - {"name"}
    public = {n for n in dir(vision) if not n.startswith("_")}
    assert not (public & forbidden_attrs), f"межу D-027 зламано: {public & forbidden_attrs}"


@pytest.mark.parametrize("vision", implementations(), ids=["fake", "camera"])
def test_capture_never_starts_by_itself(vision):
    assert not vision.capturing
    assert vision.poll(1.0) == []


@pytest.mark.parametrize("vision", implementations(), ids=["fake", "camera"])
def test_stats_shape_is_identical(vision):
    assert set(dataclasses.asdict(vision.stats())) == {"frames", "detections", "capturing"}


@pytest.mark.parametrize("vision", implementations(), ids=["fake", "camera"])
def test_shutdown_leaves_capture_off(vision):
    vision.shutdown()
    assert not vision.capturing


def test_camera_without_opencv_degrades_and_stays_silent(monkeypatch):
    """Без OpenCV адаптер має чесно сказати «не ok», а не впасти.

    Це і є ціна необов'язкової залежності з D-053: застосунок стартує,
    переходить у degraded і працює далі без камери.
    """
    import builtins

    real_import = builtins.__import__

    def no_cv2(name, *args, **kwargs):
        if name == "cv2":
            raise ImportError("no cv2")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_cv2)

    v = CameraVision()
    health = v.initialize()
    assert not health.ok
    v.start_capture()
    assert not v.capturing
    assert v.poll(1.0) == []


def test_camera_geometry_is_normalised_to_minus_one_plus_one():
    """Центр кадру дає 0.0, кути — ±1: FaceSeen обіцяє саме це."""
    centre = CameraVision._largest([(40, 30, 20, 20)], 100, 80)
    assert centre[0] == 1
    assert centre[1] == pytest.approx(0.0)
    assert centre[2] == pytest.approx(0.0)

    empty = CameraVision._largest([], 100, 80)
    assert empty == (0, 0.0, 0.0, 0.0)


def test_camera_picks_the_largest_face():
    """Найбільше обличчя — найближча людина; на неї ROBI й дивиться."""
    faces = [(0, 0, 10, 10), (60, 40, 30, 30), (20, 20, 5, 5)]
    count, x, y, size = CameraVision._largest(faces, 100, 80)
    assert count == 3
    assert size == pytest.approx(0.3)
    assert x > 0 and y > 0


def test_model_ships_with_the_package():
    """Модель має лежати поруч із кодом, а не завантажуватись у рантаймі.

    Пристрій на рецепції мусить піднятися без мережі (offline-стійкість),
    тому відсутність цього файлу — не дрібниця пакування, а зламаний старт.
    """
    from robi.vision.camera import MODEL

    assert MODEL.exists(), f"модель YuNet не знайдено: {MODEL}"
    assert MODEL.stat().st_size > 100_000, "файл моделі підозріло малий"


def test_camera_reports_why_it_is_unavailable():
    """`health.detail` має пояснювати причину, інакше degraded не діагностується."""
    v = CameraVision()
    assert v.health().detail
    assert not v.health().ok
