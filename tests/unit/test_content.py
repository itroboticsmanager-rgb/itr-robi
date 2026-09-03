"""Контент-меню: модель і валідація (D-048).

Головне, що тут охороняється, — не формат, а обіцянка: батько біля
стійки не має впертися в глухий кут. Тому посилання в нікуди, порожнє
меню й недосяжний вузол мусять валити завантаження, а не з'являтися на
екрані.
"""

import pytest

from robi.content import MAX_BODY, MAX_ITEMS, MAX_TITLE, Content, ContentError


def build(*nodes, root="root"):
    return Content.from_dict({"root": root, "node": list(nodes)})


def menu(node_id, items, title=None):
    return {"id": node_id, "kind": "menu", "title": title or node_id, "items": items}


def card(node_id, **extra):
    return {"id": node_id, "kind": "card", "title": extra.pop("title", node_id), **extra}


def test_loads_a_simple_tree():
    c = build(menu("root", ["a"]), card("a", title="Курс", price="100 грн"))
    assert c.root == "root"
    assert c.node("a").title == "Курс"
    assert not c.node("a").is_menu
    assert c.node("root").is_menu


def test_menu_label_comes_from_the_target_title():
    c = build(menu("root", ["a"]), card("a", title="Робототехніка"))
    assert c.label_for("a") == "Робототехніка"


# --- глухі кути -----------------------------------------------------------


def test_link_to_nowhere_is_rejected():
    with pytest.raises(ContentError, match="неіснуючий"):
        build(menu("root", ["missing"]))


def test_self_link_is_rejected():
    with pytest.raises(ContentError, match="сам на себе"):
        build(menu("root", ["root"]))


def test_empty_menu_is_rejected():
    with pytest.raises(ContentError, match="порожнє"):
        build(menu("root", []))


def test_unreachable_node_is_rejected():
    """Вузол, якого ніхто не побачить, — це недороблений контент, а не дрібниця."""
    with pytest.raises(ContentError, match="недосяжні"):
        build(menu("root", ["a"]), card("a"), card("orphan"))


def test_missing_root_is_rejected():
    with pytest.raises(ContentError, match="кореневий"):
        build(menu("root", ["a"]), card("a"), root="nope")


def test_card_cannot_carry_menu_items():
    with pytest.raises(ContentError, match="не може мати пунктів"):
        build(menu("root", ["a"]), {"id": "a", "kind": "card", "title": "A", "items": ["root"]})


# --- межі екрана ----------------------------------------------------------


def test_too_many_items_rejected():
    targets = [f"n{i}" for i in range(MAX_ITEMS + 1)]
    nodes = [menu("root", targets)] + [card(t) for t in targets]
    with pytest.raises(ContentError, match="максимум"):
        build(*nodes)


def test_too_long_title_rejected():
    with pytest.raises(ContentError, match="title"):
        build(menu("root", ["a"]), card("a", title="я" * (MAX_TITLE + 1)))


def test_too_long_body_rejected():
    with pytest.raises(ContentError, match="body"):
        build(menu("root", ["a"]), card("a", body="я" * (MAX_BODY + 1)))


def test_duplicate_id_rejected():
    with pytest.raises(ContentError, match="дубльований"):
        build(menu("root", ["a"]), card("a"), card("a"))


def test_repeated_item_rejected():
    with pytest.raises(ContentError, match="повторюється"):
        build(menu("root", ["a", "a"]), card("a"))


def test_unknown_kind_rejected():
    with pytest.raises(ContentError, match="kind"):
        build(menu("root", ["a"]), {"id": "a", "kind": "video", "title": "A"})


def test_empty_content_rejected():
    with pytest.raises(ContentError, match="порожній"):
        Content.from_dict({"node": []})


# --- приклад із репозиторію -----------------------------------------------


def test_shipped_example_is_valid():
    """Приклад у репозиторії має бути робочим, інакше він гірший за відсутній."""
    from pathlib import Path

    example = Path(__file__).resolve().parents[2] / "app" / "config" / "content.example.toml"
    content = Content.load(example)
    assert content.node(content.root).is_menu
    assert len(content.nodes) > 3
