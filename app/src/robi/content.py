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

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

#: Межі з `D-048`: «кожен екран має обмеження довжини й кількості сторінок».
MAX_TITLE = 60
MAX_BODY = 600
MAX_PRICE = 40
MAX_ICON = 32
#: Пункти «чого навчиться дитина»: біля стійки їх прочитують, а не гортають.
MAX_HIGHLIGHTS = 4
MAX_HIGHLIGHT = 120
#: Погоджена сітка 2x5 показує до десяти великих сенсорних цілей без
#: прокрутки. Більше не стискається: це вже окрема сторінка меню.
MAX_ITEMS = 10
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
    #: Семантичний ключ із дозволеного набору UI. Невідомий ключ безпечно
    #: переходить у generic-іконку, тому контент не може виконувати код.
    icon: str = ""
    #: Шлях відносно теки ассетів. Відсутній файл — не помилка: картка
    #: показується без картинки (D-048 вимагає fallback, а не порожній екран).
    image: str = ""
    #: Вік і тривалість — числа, а не текст: підпис і підбір за віком
    #: складає інтерфейс, а контент лише каже, для кого курс.
    age_min: int | None = None
    age_max: int | None = None
    duration_months: int | None = None
    #: Короткі пункти «чого навчиться дитина». Лише текст, без розмітки.
    highlights: tuple[str, ...] = ()
    #: Колір акценту `#rrggbb`. Нічого, крім шістнадцяткового кольору: веб
    #: підставляє його в CSS, і рядок довільної форми туди не має пройти.
    accent: str = ""

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

    def icon_for(self, node_id: str) -> str:
        return self.nodes[node_id].icon

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

    icon = str(entry.get("icon", "")).strip().lower()
    _limit(node_id, "icon", icon, MAX_ICON)

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

    age_min = _bounded_int(node_id, entry, "age_min", 0, 99)
    age_max = _bounded_int(node_id, entry, "age_max", 0, 99)
    if age_min is not None and age_max is not None and age_max < age_min:
        raise ContentError(f"{node_id}: age_max менший за age_min")
    duration_months = _bounded_int(node_id, entry, "duration_months", 1, 60)

    highlights_raw = entry.get("highlights", [])
    if not isinstance(highlights_raw, list) or not all(isinstance(h, str) for h in highlights_raw):
        raise ContentError(f"{node_id}: highlights має бути списком рядків")
    if len(highlights_raw) > MAX_HIGHLIGHTS:
        raise ContentError(
            f"{node_id}: {len(highlights_raw)} пунктів highlights, максимум {MAX_HIGHLIGHTS}"
        )
    highlights = tuple(h.strip() for h in highlights_raw)
    if any(not h for h in highlights):
        raise ContentError(f"{node_id}: порожній пункт highlights")
    for highlight in highlights:
        _limit(node_id, "highlights", highlight, MAX_HIGHLIGHT)

    accent = str(entry.get("accent", "")).strip().lower()
    if accent and not re.fullmatch(r"#[0-9a-f]{6}", accent):
        raise ContentError(f"{node_id}: accent має бути кольором #rrggbb")

    return Node(
        id=node_id,
        kind=kind,
        title=title,
        items=items,
        body=body,
        price=price,
        icon=icon,
        image=str(entry.get("image", "")).strip(),
        age_min=age_min,
        age_max=age_max,
        duration_months=duration_months,
        highlights=highlights,
        accent=accent,
    )


def _bounded_int(node_id: str, entry: dict, field: str, low: int, high: int) -> int | None:
    value = entry.get(field)
    if value is None:
        return None
    # bool у Python — підклас int, але `true` роком бути не може.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContentError(f"{node_id}: {field} має бути цілим числом")
    if not low <= value <= high:
        raise ContentError(f"{node_id}: {field} поза межами {low}–{high}")
    return value


def _limit(node_id: str, field: str, value: str, limit: int) -> None:
    if len(value) > limit:
        raise ContentError(
            f"{node_id}: {field} задовгий — {len(value)} символів, максимум {limit}"
        )
