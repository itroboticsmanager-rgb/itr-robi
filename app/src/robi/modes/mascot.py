"""Режим `mascot` — фонова поведінка за замовчуванням.

Це єдиний режим, який вмикає камеру (D-033). Наслідок, який варто
пам'ятати: оскільки mascot фоновий, камера працює майже весь час роботи
пристрою, а видимої події «сканування» не існує. Саме тому апаратний
індикатор активності є вимогою, а не покращенням (D-029).
"""

from __future__ import annotations

import pygame

from ..events import Event, FaceSeen, Intent, NfcTouched, Presence, Swipe, Touch
from ..state.coordinator import ModeName
from ..ui.face import FaceRenderer
from ..mascot_state import MascotState, parse as parse_state
from ..banners import Banner
from ..ui.showcase import NavAction, Showcase
from ..ui.theme import PALETTE

#: Скільки секунд без детекції обличчя треба, щоб ROBI повернув погляд
#: у нейтраль. Миттєве повернення виглядає смиканням.
# При 4 к/с (D-053) кадр приходить раз на 250 мс, тож 0.8 с — це лише три
# спроби. Профіль обличчя детектується гірше за анфас, і людина біля стійки
# губилася на звичайному повороті голови. 1.5 с переживає кілька промахів
# поспіль і все одно повертає погляд у нейтраль, коли людина справді пішла.
FACE_LOST_GRACE_S = 1.5

#: Мінімальний проміжок між RGB-акцентами, щоб підсвітка не блимала
#: безперервно при кожному русі перед столом.
ACCENT_COOLDOWN_S = 6.0

#: Скільки інтерактивний режим тримається без дотиків.
#:
#: Відлік скидає саме дотик, а не побачене обличчя. Інакше вийшло б
#: замкнене коло: камера лишалася б увімкненою тому, що бачить людину,
#: яка нічого не робить, — а це рівно те постійне спостереження, від
#: якого цей режим і рятує.
INTERACTIVE_TIMEOUT_S = 120.0


class MascotMode:
    name = ModeName.MASCOT

    def __init__(self, size: tuple[int, int]) -> None:
        self.face = FaceRenderer(size)
        self._since_face = 999.0
        self._present = False
        self._accent_cooldown = 0.0
        self._pending_accent: tuple[int, int, int] | None = None
        self._interactive = False
        self._idle_since = 0.0

        # Вітрина й друге обличчя — для смужки. Два підготовлені рендери
        # замість одного з перебудовою: `resize` наново готує всі поверхні,
        # і робити це під час жесту означало б ривок саме в той момент,
        # коли людина дивиться на екран.
        self.showcase = Showcase(size)
        self.strip_face = FaceRenderer(self.showcase.face_size(), compact=True)
        self.strip_face.show_handle = False
        self.banners: list[Banner] = []
        self.buttons: list[NavAction] = []
        self._pending_node: str | None = None
        self._image_for = lambda banner: None

    def wants_camera(self) -> bool:
        """Камера працює лише в інтерактивному режимі.

        Це головна зміна в поведінці пристрою: замість того, щоб дивитися
        в порожній хол цілодобово й сповільнюватися за розкладом, ROBI
        вмикає камеру тоді, коли людина сама потягнула його вниз.

        Крім тепла й струму це змінює й розмову з батьками: не «камера
        працює завжди, але нічого не зберігає», а «камера вмикається,
        коли ви самі відкриваєте режим гри».
        """
        return self._interactive

    def wants_release(self) -> bool:
        return False

    def set_state_from(self, value: str) -> bool:
        """Стан із команди CRM. Невідомий ключ ігнорується, а не валить режим.

        Словник спільний із CRM (`mascot_state`), тож команда може
        називати емоцію тим самим словом, яким її називає портал.
        """
        state = parse_state(value)
        if state is None:
            return False
        self.face.set_state(state)
        return True

    def enter(self, payload: dict) -> None:
        # Повернення в mascot завжди починається зі спокою: наступна
        # людина не має заставати камеру ввімкненою від попередньої.
        self._interactive = False
        self._idle_since = 0.0
        self._since_face = 999.0

    def exit(self) -> None:
        self.face.look_away()

    def resize(self, size: tuple[int, int]) -> None:
        self.face.resize(size)
        self.showcase.resize(size)
        self.strip_face.resize(self.showcase.face_size())
        self.strip_face.show_handle = False

    # -- інтерактивний режим ------------------------------------------

    @property
    def interactive(self) -> bool:
        return self._interactive

    def expand(self) -> None:
        """Людина потягнула ROBI вниз: вмикаємо камеру й погляд."""
        self._interactive = True
        self._idle_since = 0.0
        self.face.show_handle = False
        self.face.set_state(MascotState.HAPPY)

    def collapse(self) -> None:
        """Повернення в спокій. Камера гасне разом зі станом (D-029)."""
        self._interactive = False
        self._idle_since = 0.0
        self.face.show_handle = True
        self.face.look_away()
        self.face.set_state(MascotState.IDLE)

    def handle(self, event: Event) -> None:
        if isinstance(event, Swipe):
            # Тягнути вниз — розгорнути. Вгору — згорнути назад, щоб вихід
            # був таким самим жестом, а не лише очікуванням таймера.
            # Розгортає лише жест, що почався на смужці ROBI: інакше
            # горизонтальне гортання каруселі з невеликим нахилом вниз
            # раптово відкривало б обличчя на весь екран.
            if event.direction == "down" and not self._interactive:
                if self.showcase.hit_strip(event.x, event.y):
                    self.expand()
            elif event.direction == "up" and self._interactive:
                self.collapse()
            return

        if isinstance(event, FaceSeen):
            if event.count > 0:
                was_away = self._since_face > FACE_LOST_GRACE_S
                self._since_face = 0.0
                self.face.look_at(event.x, event.y)
                if was_away:
                    self.face.react_greeting()
                    self.face.set_state(MascotState.HAPPY)
            return

        if isinstance(event, Presence):
            was = self._present
            self._present = event.present
            if event.present and not was:
                self.face.react_greeting()
                self.face.set_state(MascotState.HAPPY)
                self._request_accent(PALETTE.accent)
            return

        if isinstance(event, Touch):
            # У вітрині дотик по кнопці відкриває гілку меню, а не гладить
            # обличчя: воно там лише визирає зі смужки.
            if not self._interactive and self.buttons:
                index = self.showcase.hit_button(event.x, event.y, len(self.buttons))
                if index is not None:
                    self._pending_node = self.buttons[index].key
                    return

            # Дотик — єдине, що продовжує інтерактивний режим.
            self._idle_since = 0.0
            self.face.react_touch(event.x, event.y)
            self.face.set_state(MascotState.HAPPY)
            self._request_accent(PALETTE.ok)
            return

        if isinstance(event, NfcTouched):
            if event.ok:
                self.face.react_success()
                self.face.set_state(MascotState.SUCCESS)
            else:
                self.face.react_error()
                self.face.set_state(MascotState.ERROR)
            self._request_accent(PALETTE.ok if event.ok else PALETTE.error)

    def _request_accent(self, rgb: tuple[int, int, int]) -> None:
        if self._accent_cooldown > 0.0:
            return
        self._pending_accent = rgb
        self._accent_cooldown = ACCENT_COOLDOWN_S

    def take_pending_node(self) -> str | None:
        """Кнопка вітрини просить відкрити гілку меню.

        Режим лише повідомляє про намір: рішення, хто займає екран,
        лишається за координатором (`architecture.md`).
        """
        node, self._pending_node = self._pending_node, None
        return node

    def update(self, dt: float) -> Intent | None:
        if not self._interactive:
            self.showcase.update(dt, len(self.banners))
            self.strip_face.update(dt)

        if self._interactive:
            self._idle_since += dt
            if self._idle_since >= INTERACTIVE_TIMEOUT_S:
                self.collapse()

        self._since_face += dt
        self._accent_cooldown = max(0.0, self._accent_cooldown - dt)

        if self._since_face > FACE_LOST_GRACE_S:
            self.face.look_away()

        self.face.update(dt)

        if self._pending_accent is not None:
            rgb, self._pending_accent = self._pending_accent, None
            return Intent(rgb=rgb, ttl=1.5)
        return None

    def draw(self, surface: pygame.Surface) -> None:
        if not self._interactive:
            face = pygame.Surface(self.showcase.face_size(), pygame.SRCALPHA)
            self.strip_face.draw(face)
            self.showcase.draw(
                surface, face, self.banners, self.buttons, self._image_for,
            )
            return
        self.face.draw(surface)
