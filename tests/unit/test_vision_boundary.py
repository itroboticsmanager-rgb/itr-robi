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
