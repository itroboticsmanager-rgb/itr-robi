"""Стани маскота — спільний словник із рештою продуктів школи.

Ключі тут **дослівно повторюють** `docs/mascot/mascot-states.md` у CRM.
Це не запозичення для краси: той самий персонаж живе в трьох місцях —
асистент у CRM, маскот у порталах і цей пристрій. Якби ROBI вигадав свій
набір емоцій, CRM довелося б перекладати один словник в інший, і рано чи
пізно вони розійшлися б.

Чому вигляд описаний саме так. У CRM емоція виражається очима, антеною,
руками й ногами. На планшеті кінцівки статичні (`D-019`), антена не має
світлодіода (`D-045`), а канал RGB знято (`D-043`). Тому кожен стан
переведено у мову face-display: форма очей, погляд, маленька усмішка та
короткі семантичні акценти.

Очі лишаються головним каналом і ніколи не замінюються текстом чи лише
кольором.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class MascotState(str, Enum):
    """Дванадцять станів із гайда CRM. Порядок і значення — звідти."""

    IDLE = "idle"
    HAPPY = "happy"
    SUCCESS = "success"
    ERROR = "error"
    WARNING = "warning"
    LOADING = "loading"
    EMPTY = "empty"
    POINTING = "pointing"
    ACHIEVEMENT = "achievement"
    THINKING = "thinking"
    SAD = "sad"
    SLEEPING = "sleeping"


#: Форми ока, які вміє малювати рендер.
EYE_OPEN = "open"
EYE_CRESCENT = "crescent"
EYE_WIDE = "wide"
EYE_NARROW = "narrow"
EYE_CLOSED = "closed"

EYE_SHAPES = frozenset({EYE_OPEN, EYE_CRESCENT, EYE_WIDE, EYE_NARROW, EYE_CLOSED})


@dataclass(frozen=True, slots=True)
class Look:
    """Як стан виглядає на пристрої.

    `gaze` — зміщення погляду в тих самих -1..1, що й `FaceSeen`: воно
    накладається, коли обличчя людини не веде погляд.

    `hold_s` — скільки стан тримається, перш ніж повернутися в `idle`.
    `None` означає, що стан лишається, поки його не змінять: людині біля
    стійки не можна показувати «помилку», яка сама зникла й повернулася.
    """

    eye: str
    gaze: tuple[float, float] = (0.0, 0.0)
    sparkle: bool = False
    zzz: bool = False
    hold_s: float | None = 1.4
    follows_face: bool = False


#: Переклад станів гайда в те, що ROBI вміє показати.
LOOKS: dict[MascotState, Look] = {
    # «відкриті, слідкують» — єдиний стан, у якому працює стеження.
    MascotState.IDLE: Look(EYE_OPEN, hold_s=None, follows_face=True),
    # «півмісяці / зірки»
    MascotState.HAPPY: Look(EYE_CRESCENT, sparkle=True, hold_s=1.6),
    # «підморгують / зірки»
    MascotState.SUCCESS: Look(EYE_CRESCENT, sparkle=True, hold_s=1.8),
    # «великі круглі»
    MascotState.ERROR: Look(EYE_WIDE, hold_s=1.8),
    # «звужені»
    MascotState.WARNING: Look(EYE_NARROW, hold_s=1.8),
    # Під час завантаження відкриті очі плавно сканують екран.
    MascotState.LOADING: Look(EYE_CLOSED, hold_s=None),
    # «сумні, вбік»
    MascotState.EMPTY: Look(EYE_NARROW, gaze=(-0.55, 0.35), hold_s=None),
    # «зацікавлені»
    MascotState.POINTING: Look(EYE_WIDE, gaze=(0.0, 0.15), hold_s=2.2),
    # «зірки, блиск»
    MascotState.ACHIEVEMENT: Look(EYE_CRESCENT, sparkle=True, hold_s=2.6),
    # «дивляться вгору»
    MascotState.THINKING: Look(EYE_OPEN, gaze=(0.25, -0.6), hold_s=None),
    # «сльозинка / опущені»
    MascotState.SAD: Look(EYE_NARROW, gaze=(0.0, 0.5), hold_s=2.2),
    # «Zzz»
    MascotState.SLEEPING: Look(EYE_CLOSED, zzz=True, hold_s=None),
}


def look_for(state: MascotState) -> Look:
    return LOOKS[state]


def parse(value: str) -> MascotState | None:
    """Розбирає стан із команди CRM. Невідомий — не аварія, а мовчазне «ні».

    Пристрій на стійці не має падати від того, що CRM надіслала стан із
    новішої версії словника: він просто лишається в поточному.
    """
    try:
        return MascotState(str(value).strip().lower())
    except ValueError:
        return None
