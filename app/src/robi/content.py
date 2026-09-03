"""Контент-меню: модель, завантаження й валідація (D-048).

Звідки береться контент. CRM ще немає (`D-010`), а offline-стійкість є
вимогою, а не зручністю: пристрій на рецепції мусить показувати курси й
ціни при мертвій мережі. Тому контент живе у файлі поруч із конфігурацією
пристрою. Коли CRM з'явиться, вона віддаватиме **цю саму структуру** —
міняється джерело, не модель.

Чому структура, а не розмітка. `D-048` прямо забороняє виконувати
довільний HTML або код, що прийшов ззовні. Тут нема чого виконувати:
вузол — це дані з фіксованим набором полів, а рендер вирішує застосунок.
Скомпрометована CRM зможе показати неправдивий текст, але не запустити
код на пристрої в школі.

Чому валідація сувора й падає на завантаженні. Посилання в нікуди — це
не попередження в журналі, а глухий кут перед батьком біля стійки, який
уже нікуди звідти не натисне. Краще не стартувати з битим контентом, ніж
завести людину в порожній екран.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

#: Межі з `D-048`: «кожен екран має обмеження довжини й кількості сторінок».
MAX_TITLE = 60
MAX_BODY = 600
MAX_PRICE = 40
#: Більше восьми пунктів не влізе на екран без прокрутки, а прокрутки у v1
#: немає навмисно: список, який доводиться гортати, вже не є меню.
MAX_ITEMS = 8
MAX_NODES = 200

KINDS = frozenset({"menu", "card"})


class ContentError(ValueError):
    """Контент непридатний. Краще не стартувати, ніж завести в глухий кут."""


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    kind: str
    title: str
    items: tuple[str, ...] = ()
    body: str = ""
    price: str = ""
    #: Шлях відносно теки ассетів. Відсутній файл — не помилка: картка
    #: показується без картинки (D-048 вимагає fallback, а не порожній екран).
    image: str = ""

    @property
    def is_menu(self) -> bool:
        return self.kind == "menu"


@dataclass(frozen=True, slots=True)
class Content:
    root: str
    nodes: Mapping[str, Node]

    def node(self, node_id: str) -> Node:
        return self.nodes[node_id]

    def label_for(self, node_id: str) -> str:
        """Підпис пункту меню — це заголовок вузла, куди він веде.

        Окремого поля під підпис навмисно немає: два джерела назви для
        однієї сторінки розходяться першої ж правки.
        """
        return self.nodes[node_id].title

    @staticmethod
    def load(path: str | Path) -> "Content":
        p = Path(path)
        if not p.exists():
            raise ContentError(f"контент не знайдено: {p}")
        try:
            raw = tomllib.loads(p.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ContentError(f"{p}: {exc}") from exc
        return Content.from_dict(raw)

    @staticmethod
    def from_dict(raw: dict) -> "Content":
        entries = raw.get("node", [])
        if not isinstance(entries, list) or not entries:
            raise ContentError("контент порожній: немає жодного [[node]]")
        if len(entries) > MAX_NODES:
            raise ContentError(f"забагато вузлів: {len(entries)} > {MAX_NODES}")

        nodes: dict[str, Node] = {}
        for entry in entries:
            node = _node_from(entry)
            if node.id in nodes:
                raise ContentError(f"дубльований id вузла: {node.id!r}")
            nodes[node.id] = node

        root = str(raw.get("root", "root"))
        content = Content(root=root, nodes=nodes)
        content.validate()
        return content

    def validate(self) -> None:
        if self.root not in self.nodes:
            raise ContentError(f"кореневий вузол {self.root!r} не існує")

        for node in self.nodes.values():
            for target in node.items:
                if target not in self.nodes:
                    raise ContentError(
                        f"вузол {node.id!r} веде в неіснуючий {target!r}"
                    )
                if target == node.id:
                    raise ContentError(f"вузол {node.id!r} посилається сам на себе")
            if node.is_menu and not node.items:
                raise ContentError(f"меню {node.id!r} порожнє")
            if not node.is_menu and node.items:
                raise ContentError(f"картка {node.id!r} не може мати пунктів меню")

        unreachable = set(self.nodes) - self._reachable()
        if unreachable:
            # Не помилка рендеру, а помилка автора: такий вузол ніхто ніколи
            # не побачить, і мовчати про це означає ховати недороблений контент.
            raise ContentError(
                "вузли недосяжні з кореня: " + ", ".join(sorted(unreachable))
            )

    def _reachable(self) -> set[str]:
        seen: set[str] = set()
        stack = [self.root]
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(self.nodes[current].items)
        return seen


def _node_from(entry: dict) -> Node:
    if not isinstance(entry, dict):
        raise ContentError("вузол має бути таблицею [[node]]")

    node_id = str(entry.get("id", "")).strip()
    if not node_id:
        raise ContentError("вузол без id")

    kind = str(entry.get("kind", "")).strip()
    if kind not in KINDS:
        raise ContentError(f"{node_id}: невідомий kind {kind!r}, очікується menu або card")

    title = str(entry.get("title", "")).strip()
    if not title:
        raise ContentError(f"{node_id}: порожній заголовок")
    _limit(node_id, "title", title, MAX_TITLE)

    body = str(entry.get("body", "")).strip()
    _limit(node_id, "body", body, MAX_BODY)

    price = str(entry.get("price", "")).strip()
    _limit(node_id, "price", price, MAX_PRICE)

    items_raw = entry.get("items", [])
    if not isinstance(items_raw, list):
        raise ContentError(f"{node_id}: items має бути списком")
    if len(items_raw) > MAX_ITEMS:
        raise ContentError(f"{node_id}: {len(items_raw)} пунктів, максимум {MAX_ITEMS}")
    items = tuple(str(i).strip() for i in items_raw)
    if any(not i for i in items):
        raise ContentError(f"{node_id}: порожній пункт меню")
    if len(set(items)) != len(items):
        raise ContentError(f"{node_id}: пункт меню повторюється")

    return Node(
        id=node_id,
        kind=kind,
        title=title,
        items=items,
        body=body,
        price=price,
        image=str(entry.get("image", "")).strip(),
    )


def _limit(node_id: str, field: str, value: str, limit: int) -> None:
    if len(value) > limit:
        raise ContentError(
            f"{node_id}: {field} задовгий — {len(value)} символів, максимум {limit}"
        )
