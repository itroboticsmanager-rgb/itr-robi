import pytest

from robi.lessons_today import MAX_LESSONS, parse_lessons


def lesson(**over):
    item = {
        "id": 1, "course": "Робототехніка Lego", "group": "Пн 16:30 Lego",
        "start": "2026-11-19T14:30:00Z", "end": "2026-11-19T16:00:00Z",
        "color": "#3b82f6", "icon": "rocket",
    }
    item.update(over)
    return item


def test_valid_lesson_passes_through():
    [one] = parse_lessons({"lessons": [lesson()]})
    assert one.for_web() == {
        "id": 1, "course": "Робототехніка Lego", "group": "Пн 16:30 Lego",
        "start": "2026-11-19T14:30:00Z", "end": "2026-11-19T16:00:00Z",
        "color": "#3b82f6", "icon": "rocket",
    }


def test_broken_records_are_dropped_not_shown():
    lessons = parse_lessons({"lessons": [
        lesson(id="1"),                     # id не число
        lesson(id=2, start="вчора"),        # час не ISO
        lesson(id=3, course=""),            # без назви
        lesson(id=4, end="2026-11-19T14:00:00Z"),  # кінець раніше початку
        "сміття",
        lesson(id=5),
    ]})
    assert [l.id for l in lessons] == [5]


def test_unsafe_color_and_icon_become_empty():
    [one] = parse_lessons({"lessons": [lesson(color="red;background:url(x)", icon="<svg>")]})
    assert one.color == "" and one.icon == ""


def test_list_is_capped_and_shape_is_checked():
    many = [lesson(id=i) for i in range(MAX_LESSONS + 10)]
    assert len(parse_lessons({"lessons": many})) == MAX_LESSONS
    with pytest.raises(ValueError):
        parse_lessons({"lessons": "немає"})
