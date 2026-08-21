"""Системні стани пристрою.

Це не те саме, що режими контенту: `offline + mascot` — валідна комбінація
(software.md). Стан описує здоров'я пристрою, режим — що на екрані.
"""

from __future__ import annotations

from enum import Enum


class SystemState(str, Enum):
    BOOTING = "booting"
    READY = "ready"
    INTERACTING = "interacting"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    SERVICE = "service"
    SHUTTING_DOWN = "shutting_down"
    FAULT = "fault"


#: Дозволені переходи. Усе, чого тут немає, є помилкою програміста,
#: а не станом, який треба «якось обробити».
TRANSITIONS: dict[SystemState, frozenset[SystemState]] = {
    SystemState.BOOTING: frozenset(
        {SystemState.READY, SystemState.DEGRADED, SystemState.FAULT, SystemState.SHUTTING_DOWN}
    ),
    SystemState.READY: frozenset(
        {
            SystemState.INTERACTING,
            SystemState.OFFLINE,
            SystemState.DEGRADED,
            SystemState.SERVICE,
            SystemState.SHUTTING_DOWN,
            SystemState.FAULT,
        }
    ),
    SystemState.INTERACTING: frozenset(
        {
            SystemState.READY,
            SystemState.OFFLINE,
            SystemState.DEGRADED,
            SystemState.SHUTTING_DOWN,
            SystemState.FAULT,
        }
    ),
    SystemState.OFFLINE: frozenset(
        {
            SystemState.READY,
            SystemState.INTERACTING,
            SystemState.DEGRADED,
            SystemState.SERVICE,
            SystemState.SHUTTING_DOWN,
            SystemState.FAULT,
        }
    ),
    SystemState.DEGRADED: frozenset(
        {
            SystemState.READY,
            SystemState.INTERACTING,
            SystemState.OFFLINE,
            SystemState.SERVICE,
            SystemState.SHUTTING_DOWN,
            SystemState.FAULT,
        }
    ),
    SystemState.SERVICE: frozenset(
        {SystemState.READY, SystemState.SHUTTING_DOWN, SystemState.FAULT}
    ),
    SystemState.SHUTTING_DOWN: frozenset(),
    SystemState.FAULT: frozenset({SystemState.SERVICE, SystemState.SHUTTING_DOWN}),
}


class IllegalTransition(RuntimeError):
    pass


class StateMachine:
    def __init__(self, initial: SystemState = SystemState.BOOTING) -> None:
        self._state = initial
        self._history: list[tuple[SystemState, str]] = [(initial, "start")]

    @property
    def state(self) -> SystemState:
        return self._state

    @property
    def history(self) -> list[tuple[SystemState, str]]:
        return list(self._history)

    def can(self, target: SystemState) -> bool:
        return target in TRANSITIONS[self._state]

    def to(self, target: SystemState, reason: str = "") -> None:
        if target is self._state:
            return
        if not self.can(target):
            raise IllegalTransition(f"{self._state.value} -> {target.value}")
        self._state = target
        self._history.append((target, reason))

    def is_terminal(self) -> bool:
        return not TRANSITIONS[self._state]
