"""Координатор режимів: єдине джерело правди про те, що зараз на екрані.

Правила пріоритетів узяті з architecture.md. Головне, що тут закодовано:
режим не «володіє» обладнанням і не вирішує сам, коли йому поступитися —
рішення про витіснення ухвалює координатор за пріоритетом і TTL.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, IntEnum

from ..events import Command, CommandKind, CommandResult, CommandStatus, now


class ModeName(str, Enum):
    MASCOT = "mascot"
    QR = "qr"
    INFO = "info"
    NFC = "nfc"
    VOICE = "voice"


class Priority(IntEnum):
    """Більше число витісняє менше. Порядок — з architecture.md."""

    BACKGROUND = 10   # фоновий mascot/info
    CRM = 20          # команда CRM з обмеженим часом життя
    USER = 30         # активна взаємодія користувача
    SERVICE = 40      # сервісний режим і штатне вимкнення
    CRITICAL = 50     # перегрів, критична помилка живлення


@dataclass(slots=True)
class Activation:
    """Те, що зараз займає екран."""

    mode: ModeName
    priority: Priority
    started_at: float
    expires_at: float | None = None
    command_id: str | None = None
    payload: dict = field(default_factory=dict)

    def expired(self, at: float) -> bool:
        return self.expires_at is not None and at >= self.expires_at


#: Стеля часу життя будь-якої активації від CRM.
#:
#: Пристрій стоїть на рецепції й може будь-якої миті втратити мережу. Поки
#: її немає, CRM не може ні скасувати команду, ні виправити її — тож
#: єдиний, хто здатен вивести ROBI з чутливого стану, це він сам.
#:
#: Тому команда без строку — не «показувати завжди», а помилка контракту,
#: яку пристрій виправляє на свою користь. Інакше зниклий `cancel` лишав би
#: чужий платіжний QR на екрані до приходу адміністратора.
#:
#: Звірка стану при перепідключенні цього не замінює: розрив триває саме
#: тоді, коли звірки не буде. І відновлювати команду після нього було б
#: гірше — за `D-038` платіжні посилання одноразові, тож «згадати» QR
#: п'ятихвилинної давнини означає показати прострочений чужий рахунок.
MAX_CRM_ACTIVATION_S = 300.0


class Coordinator:
    """Тримає активний режим і вирішує, хто кого витісняє."""

    #: Режими, які ще не реалізовані. Команду на них треба чесно відхилити,
    #: а не мовчки проковтнути. Перелік задається при створенні, бо
    #: реалізованість не є властивістю коду: `info` існує лише тоді, коли
    #: пристрою даний контент (D-048), і без нього команду на нього слід
    #: відхиляти так само чесно, як і на нереалізований `voice`.
    UNSUPPORTED = frozenset({ModeName.INFO, ModeName.NFC, ModeName.VOICE})

    def __init__(
        self,
        base: ModeName = ModeName.MASCOT,
        clock: Callable[[], float] = now,
        unsupported: frozenset[ModeName] | None = None,
        max_activation_s: float = MAX_CRM_ACTIVATION_S,
    ) -> None:
        # Годинник інжектується, бо вся ця логіка — про час: TTL, expiry
        # й витіснення неможливо перевірити на реальному монотонному часі.
        self._clock = clock
        self._base = base
        self.unsupported = self.UNSUPPORTED if unsupported is None else unsupported
        self._max_activation = max_activation_s
        self._active = Activation(base, Priority.BACKGROUND, clock())
        self._seen_commands: dict[str, CommandResult] = {}

    @property
    def active(self) -> Activation:
        return self._active

    @property
    def mode(self) -> ModeName:
        return self._active.mode

    # -- життєвий цикл -----------------------------------------------------

    def tick(self, at: float | None = None) -> bool:
        """Знімає активацію, у якої вийшов час. True, якщо режим змінився."""
        at = self._clock() if at is None else at
        if self._active.priority is not Priority.BACKGROUND and self._active.expired(at):
            self._fall_back(at)
            return True
        return False

    def _fall_back(self, at: float) -> None:
        self._active = Activation(self._base, Priority.BACKGROUND, at)

    def request(
        self,
        mode: ModeName,
        priority: Priority,
        ttl: float | None = None,
        command_id: str | None = None,
        at: float | None = None,
        payload: dict | None = None,
    ) -> bool:
        """Просить показати режим. False — якщо поточний важливіший."""
        at = self._clock() if at is None else at
        if priority < self._active.priority and not self._active.expired(at):
            return False
        self._active = Activation(
            mode=mode,
            priority=priority,
            started_at=at,
            expires_at=None if ttl is None else at + ttl,
            command_id=command_id,
            payload=dict(payload or {}),
        )
        return True

    def release(self, command_id: str | None = None, at: float | None = None) -> None:
        """Дострокове завершення. Без command_id знімає будь-яку активацію."""
        at = self._clock() if at is None else at
        if command_id is not None and self._active.command_id != command_id:
            return
        self._fall_back(at)

    # -- команди CRM -------------------------------------------------------

    def apply(self, cmd: Command, at: float | None = None) -> CommandResult:
        """Виконує команду CRM з перевіркою idempotency й строку дії."""
        at = self._clock() if at is None else at

        prior = self._seen_commands.get(cmd.command_id)
        if prior is not None:
            # Дубль не повторює фізичну дію — повертаємо той самий вердикт.
            return prior

        result = self._apply_fresh(cmd, at)
        self._seen_commands[cmd.command_id] = result
        return result

    def _apply_fresh(self, cmd: Command, at: float) -> CommandResult:
        if cmd.expired(at):
            return CommandResult(cmd.command_id, CommandStatus.REJECTED, "expired")

        if cmd.kind is CommandKind.SET_MODE:
            raw = str(cmd.payload.get("mode", ""))
            try:
                mode = ModeName(raw)
            except ValueError:
                return CommandResult(cmd.command_id, CommandStatus.REJECTED, "unknown_mode")
            if mode in self.unsupported:
                return CommandResult(cmd.command_id, CommandStatus.REJECTED, "unsupported_mode")
            ttl = self._bounded_ttl(_ttl_from(cmd, at))
            ok = self.request(mode, Priority.CRM, ttl, cmd.command_id, at, cmd.payload)
            return CommandResult(
                cmd.command_id,
                CommandStatus.ACCEPTED if ok else CommandStatus.REJECTED,
                "" if ok else "preempted",
            )

        if cmd.kind is CommandKind.SHOW_QR:
            if not cmd.payload.get("value"):
                return CommandResult(cmd.command_id, CommandStatus.REJECTED, "empty_payload")
            ttl = self._bounded_ttl(_ttl_from(cmd, at) or 15.0)
            ok = self.request(ModeName.QR, Priority.CRM, ttl, cmd.command_id, at, cmd.payload)
            return CommandResult(
                cmd.command_id,
                CommandStatus.ACCEPTED if ok else CommandStatus.REJECTED,
                "" if ok else "preempted",
            )

        if cmd.kind is CommandKind.CANCEL:
            self.release(cmd.payload.get("target_command_id"), at)
            return CommandResult(cmd.command_id, CommandStatus.COMPLETED)

        if cmd.kind is CommandKind.REQUEST_STATUS:
            return CommandResult(cmd.command_id, CommandStatus.COMPLETED)

        return CommandResult(cmd.command_id, CommandStatus.REJECTED, "unknown_command")

    def forget_older_than(self, age_s: float, at: float | None = None) -> None:
        """Обмежує пам'ять про команди — черга не має рости безмежно."""
        # Вердикти не мають часу, тож тримаємо просту верхню межу за розміром.
        limit = 512
        if len(self._seen_commands) > limit:
            drop = len(self._seen_commands) - limit
            for key in list(self._seen_commands)[:drop]:
                del self._seen_commands[key]

    def _bounded_ttl(self, ttl: float | None) -> float:
        """Обмежує час життя команди від CRM.

        `None` означає, що CRM строку не назвала. Це не «показувати
        завжди»: пристрій, який втратив мережу, більше не отримає ні
        `cancel`, ні виправлення, тож вічна активація перетворюється на
        застряглий екран до приходу людини.

        Явний строк теж обмежується: ризик той самий, різниця лише в тому,
        чи назвала CRM велике число навмисно.
        """
        if ttl is None:
            return self._max_activation
        return min(ttl, self._max_activation)

    # -- взаємодія користувача --------------------------------------------

    def user_interaction(self, mode: ModeName, ttl: float = 20.0, at: float | None = None) -> bool:
        """Дотик користувача важливіший за фонову команду CRM."""
        return self.request(mode, Priority.USER, ttl, None, at)


def _ttl_from(cmd: Command, at: float) -> float | None:
    ms = cmd.payload.get("duration_ms")
    if isinstance(ms, (int, float)) and ms > 0:
        return float(ms) / 1000.0
    if cmd.expires_at is not None:
        return max(0.0, cmd.expires_at - at)
    return None
