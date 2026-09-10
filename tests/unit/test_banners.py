"""Банери вітрини: розбір і кеш.

Головне, що охороняється, — вітрина не гасне від негараздів. Мережа на
рецепції ненадійна, а порожній екран об 8:30, коли в холі найбільше
людей, — найгірший момент для «зараз нема зв'язку».
"""

import json

import pytest

from robi.banners import MAX_BANNERS, Banner, BannerStore, parse_banners


def payload(*entries) -> dict:
    return {"banners": list(entries)}


def entry(**over) -> dict:
    base = {"id": 1, "title": "Курс робототехніки", "description": "опис",
            "image_url": "https://cdn.example.org/a.webp"}
    base.update(over)
    return base


# --- розбір ---------------------------------------------------------------


def test_parses_a_banner():
    [b] = parse_banners(payload(entry()))
    assert b.id == 1
    assert b.title == "Курс робототехніки"


def test_broken_entry_does_not_take_down_the_rest():
    """Краще показати три банери з чотирьох, ніж порожній екран."""
    got = parse_banners(payload(entry(id=1), "сміття", entry(id=2, title=""), entry(id=3)))
    assert [b.id for b in got] == [1, 3]


@pytest.mark.parametrize("bad", [None, [], "текст", {"banners": "не список"}])
def test_garbage_payload_gives_nothing(bad):
    assert parse_banners(bad) == []


def test_untitled_banner_is_skipped():
    assert parse_banners(payload(entry(title="   "))) == []


def test_bad_id_is_skipped():
    assert parse_banners(payload(entry(id="abc"))) == []
    assert parse_banners(payload(entry(id=0))) == []


def test_too_many_are_trimmed():
    """Вітрина — не каталог: решта лише роздуває кеш."""
    got = parse_banners(payload(*[entry(id=i) for i in range(1, MAX_BANNERS + 10)]))
    assert len(got) == MAX_BANNERS


def test_long_text_is_cut():
    [b] = parse_banners(payload(entry(title="я" * 500, description="о" * 900)))
    assert len(b.title) <= 80
    assert len(b.description) <= 200


def test_targeting_fields_are_ignored():
    """CRM їх і не шле, але пристрій не має їх приймати навіть випадково."""
    [b] = parse_banners(payload(entry(target_min_age=7, target_group_ids=[1, 2])))
    assert not hasattr(b, "target_min_age")
    assert not hasattr(b, "target_group_ids")


# --- кеш ------------------------------------------------------------------


def test_empty_cache_is_not_an_error(tmp_path):
    assert BannerStore(tmp_path).load() == []


def test_broken_index_is_not_an_error(tmp_path):
    (tmp_path / "banners.json").write_text("{не json", encoding="utf-8")
    assert BannerStore(tmp_path).load() == []


def test_cached_set_survives_without_network(tmp_path):
    store = BannerStore(tmp_path)
    (tmp_path / "banners.json").write_text(json.dumps(payload(entry())), encoding="utf-8")
    (tmp_path / "1.webp").write_bytes(b"x")
    [b] = store.load()
    assert b.title == "Курс робототехніки"


def test_banner_without_its_image_is_dropped(tmp_path):
    """Живлення могло зникнути між записом опису й завантаженням файлу."""
    store = BannerStore(tmp_path)
    (tmp_path / "banners.json").write_text(json.dumps(payload(entry())), encoding="utf-8")
    assert store.load() == []


def test_banner_without_an_image_at_all_is_kept(tmp_path):
    store = BannerStore(tmp_path)
    (tmp_path / "banners.json").write_text(
        json.dumps(payload(entry(image_url=""))), encoding="utf-8"
    )
    assert len(store.load()) == 1


def test_refresh_without_configuration_keeps_the_cache(tmp_path):
    store = BannerStore(tmp_path)
    ok, reason = store.refresh("", "secret")
    assert not ok
    assert reason == "not_configured"


def test_unreachable_crm_keeps_the_cache(tmp_path):
    """Найважливіше: збій мережі не має спорожнити вітрину."""
    store = BannerStore(tmp_path)
    (tmp_path / "banners.json").write_text(json.dumps(payload(entry())), encoding="utf-8")
    (tmp_path / "1.webp").write_bytes(b"x")

    ok, reason = store.refresh("http://127.0.0.1:1/nope", "secret", timeout=0.5)
    assert not ok
    assert reason.startswith("net_")
    assert len(store.load()) == 1


def test_non_ascii_secret_is_named_not_crashed(tmp_path):
    """Заголовки HTTP кодуються в latin-1, і кирилиця в секреті валила запит.

    Пристрій на стійці не має падати від того, що адміністратор вставив
    не той рядок: причина мусить бути названа.
    """
    store = BannerStore(tmp_path)
    ok, reason = store.refresh("http://127.0.0.1:1/nope", "секрет", timeout=0.5)
    assert not ok
    assert reason == "bad_secret"


def test_image_path_uses_the_id_not_the_remote_name(tmp_path):
    """Ім'я з чужої адреси не має вирішувати, куди писати на нашому диску."""
    store = BannerStore(tmp_path)
    b = Banner(id=5, title="a", image="https://cdn.example.org/../../evil.webp")
    assert store.image_path(b).parent == tmp_path
    assert store.image_path(b).name.startswith("5")


def test_odd_extension_falls_back(tmp_path):
    store = BannerStore(tmp_path)
    b = Banner(id=5, title="a", image="https://cdn.example.org/file")
    assert store.image_path(b).suffix == ".img"


def test_changed_artwork_gets_a_different_cache_file(tmp_path):
    store = BannerStore(tmp_path)
    old = Banner(id=5, title="a", image="https://cdn.example.org/old.png")
    new = Banner(id=5, title="a", image="https://cdn.example.org/new.png")
    store.image_path(old).write_bytes(b"old artwork")
    assert store.image_path(new) != store.image_path(old)
    assert not store.image_path(new).exists()


def test_kiosk_target_survives_cache(tmp_path):
    store = BannerStore(tmp_path)
    store.index.write_text(json.dumps(payload(entry(image_url="", target_node="courses"))), encoding="utf-8")
    assert store.load()[0].target_node == "courses"


@pytest.mark.parametrize("target", ["https://example.com", "../../secret", "javascript:alert(1)", ["courses"], 42])
def test_invalid_navigation_is_not_executable(target):
    assert parse_banners(payload(entry(target_node=target)))[0].target_node == ""
