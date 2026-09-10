"""Меню з CRM: сувора перевірка й кеш.

Охороняються дві обіцянки. Перша — біля стійки не буває глухого кута:
набір, що не пройшов би перевірку контенту, не заміняє робочий. Друга —
кіоск не гасне від мережі: останній вдалий набір лишається на диску.
"""

import io
import json
import urllib.error
import urllib.request

import pytest

from robi.content_store import ContentStore

URL = "https://crm.example.org/api/device/content"
COVER = "https://cdn.example.org/covers/robotics.webp"


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


@pytest.fixture
def web(monkeypatch):
    """Підміна мережі: адреса → тіло відповіді або виняток."""
    routes: dict[str, object] = {}

    def urlopen(request, timeout=None):
        url = getattr(request, "full_url", request)
        body = routes.get(url)
        if body is None:
            raise urllib.error.URLError("unreachable")
        if isinstance(body, Exception):
            raise body
        return _Response(body if isinstance(body, bytes) else json.dumps(body).encode("utf-8"))

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    return routes


def tree(**level_extra) -> dict:
    level = {"id": "level-10", "kind": "card", "title": "Lego WeDo", "price": "1400 ₴ / місяць",
             "age_min": 6, "age_max": 8, "image_url": COVER}
    level.update(level_extra)
    return {
        "root": "root",
        "node": [
            {"id": "root", "kind": "menu", "title": "Обрати заняття", "items": ["pathway-1"]},
            {"id": "pathway-1", "kind": "menu", "title": "Робототехніка", "items": ["level-10"],
             "accent": "#3b82f6"},
            level,
        ],
    }


def test_no_cache_means_no_set(tmp_path):
    assert ContentStore(tmp_path).load() == (False, None)


def test_broken_cache_counts_as_absent(tmp_path):
    """Тоді діє локальний файл, а не порожній екран."""
    (tmp_path / "content.json").write_text("{не json", encoding="utf-8")
    assert ContentStore(tmp_path).load() == (False, None)


def test_refresh_stores_the_tree_with_its_images(tmp_path, web):
    web[URL] = tree()
    web[COVER] = b"RIFF....WEBPimage"
    store = ContentStore(tmp_path)

    assert store.refresh(URL, "secret") == (True, "")
    has_set, content = store.load()
    assert has_set
    level = content.node("level-10")
    assert level.age_min == 6
    assert level.image == store.image_name("level-10", COVER)
    assert (tmp_path / level.image).read_bytes() == b"RIFF....WEBPimage"
    assert content.node("pathway-1").accent == "#3b82f6"


def test_invalid_set_keeps_the_previous_one(tmp_path, web):
    """Глухий кут з CRM не має замінити робоче меню."""
    store = ContentStore(tmp_path)
    web[URL] = tree()
    web[COVER] = b"img"
    assert store.refresh(URL, "secret")[0]

    broken = tree()
    broken["node"][1]["items"] = ["level-404"]
    web[URL] = broken
    ok, reason = store.refresh(URL, "secret")
    assert not ok
    assert reason.startswith("invalid")
    assert store.load()[1].node("pathway-1").items == ("level-10",)


def test_empty_set_turns_the_menu_off(tmp_path, web):
    """Нічого не ввімкнено в CRM — це рішення, а не збій."""
    store = ContentStore(tmp_path)
    web[URL] = {"root": "root", "node": []}
    assert store.refresh(URL, "secret") == (True, "")
    assert store.load() == (True, None)


def test_unreachable_crm_keeps_the_cache(tmp_path, web):
    store = ContentStore(tmp_path)
    web[URL] = tree()
    web[COVER] = b"img"
    store.refresh(URL, "secret")

    del web[URL]
    ok, reason = store.refresh(URL, "secret")
    assert not ok
    assert reason.startswith("net_")
    assert store.load()[1] is not None


def test_server_error_keeps_the_cache(tmp_path, web):
    store = ContentStore(tmp_path)
    web[URL] = tree()
    web[COVER] = b"img"
    store.refresh(URL, "secret")

    web[URL] = urllib.error.HTTPError(URL, 500, "boom", {}, None)
    assert store.refresh(URL, "secret") == (False, "http_500")
    assert store.load()[1] is not None


def test_missing_image_keeps_the_card(tmp_path, web):
    """Без обкладинки картка лишається карткою — D-048 вимагає fallback."""
    web[URL] = tree()
    store = ContentStore(tmp_path)
    assert store.refresh(URL, "secret") == (True, "")
    assert store.load()[1].node("level-10").image == ""


@pytest.mark.parametrize("extra", [
    {"image": "../../secrets.txt"},
    {"image_url": "http://cdn.example.org/plain.webp"},
    {"image_url": "file:///C:/Windows/win.ini"},
])
def test_crm_cannot_choose_a_local_file(tmp_path, web, extra):
    """Шлях на диску пристрою вирішує пристрій, а не відповідь сервера."""
    web[URL] = tree(**extra)
    web["http://cdn.example.org/plain.webp"] = b"img"
    store = ContentStore(tmp_path)
    assert store.refresh(URL, "secret")[0]
    assert store.load()[1].node("level-10").image == ""


def test_replaced_cover_removes_the_old_file(tmp_path, web):
    store = ContentStore(tmp_path)
    web[URL] = tree()
    web[COVER] = b"old"
    store.refresh(URL, "secret")
    old = store.image_name("level-10", COVER)

    new_cover = "https://cdn.example.org/covers/robotics-2.webp"
    web[URL] = tree(image_url=new_cover)
    web[new_cover] = b"new"
    store.refresh(URL, "secret")
    assert not (tmp_path / old).exists()
    assert (tmp_path / store.image_name("level-10", new_cover)).read_bytes() == b"new"


def test_garbage_response_is_rejected(tmp_path, web):
    web[URL] = b"<html>login</html>"
    assert ContentStore(tmp_path).refresh(URL, "secret") == (False, "bad_response")


def test_refresh_without_configuration(tmp_path):
    assert ContentStore(tmp_path).refresh("", "secret") == (False, "not_configured")


def test_non_ascii_secret_is_named_not_crashed(tmp_path):
    ok, reason = ContentStore(tmp_path).refresh("http://127.0.0.1:1/nope", "секрет", timeout=0.5)
    assert (ok, reason) == (False, "bad_secret")


def test_image_name_does_not_follow_the_remote_path(tmp_path):
    store = ContentStore(tmp_path)
    name = store.image_name("../level", "https://cdn.example.org/../../evil.webp")
    assert "/" not in name and "\\" not in name and not name.startswith(".")
