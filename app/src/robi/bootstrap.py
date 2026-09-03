"""Складання застосунку й головний цикл.

Тут єдине місце, де компоненти знають одне про одного. Усе інше
спілкується через контракти з `hardware.base`, `vision.base` і `modes.base`,
тому заміна fake-адаптера на реальний не зачіпає жодного режиму.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pygame

from .config import Config
from .content import Content, ContentError
from .events import Command, CommandKind, CommandResult, CommandStatus, Event, Source, Touch, now
from .hardware.fake import FakeNfc, FakeOutputs, FakeToF
from .health.metrics import FrameStats, Metrics
from .integration.crm import CrmClient
from .integration.policy import UrlPolicy
from .modes.info import InfoMode
from .modes.mascot import MascotMode
from .modes.qr import QrMode
from .state.coordinator import Coordinator, ModeName, Priority
from .state.machine import StateMachine, SystemState
from .ui.overlay import Overlay
from .vision.fake import FakeVision

#: Верхня межа кроку симуляції. Цикл може заблокуватися надовго з причин,
#: які не є рендером: перетягування вікна на Windows блокує event pump,
#: на пристрої це буде throttling, гикавка носія або сплячий watchdog.
#: Живий прогін дав кадр на 4.5 с при медіані 17 мс.
#:
#: Без обмеження такий dt телепортує анімацію й миттєво з'їдає TTL намірів.
#: У метриках лишається справжній час кадру: приховувати затримку не можна,
#: її треба бачити.
MAX_STEP_S = 0.1


def _claim_dpi_awareness() -> None:
    """Сказати Windows, що застосунок рахує пікселі сам.

    Без цього процес вважається DPI-необізнаним, і система бреше про
    розмір екрана: на Surface Go 2 з його 1920x1280 `pygame` отримував
    1024x768. Далі Windows малює вікно в цих вигаданих координатах і
    розтягує результат — краї обрізаються, а текст стає нечітким.

    Помітити це на ноутбуці зі стандартним масштабом неможливо: там
    брехні немає. Тому виклик стоїть тут, до `pygame.init()`, а не в
    налаштуваннях пристрою — це властивість застосунку, а не машини.
    """
    if os.name != "nt":
        return
    import ctypes

    try:
        # PROCESS_PER_MONITOR_DPI_AWARE: правильна поведінка при переносі
        # між екранами з різним масштабом.
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            # Старий Windows або нестандартна збірка: краще нечіткий
            # рендер, ніж застосунок, який не стартує.
            pass


class App:
    def __init__(
        self,
        config: Config,
        headless: bool = False,
        uncapped: bool = False,
        clock: "Callable[[], float]" = now,
    ) -> None:
        self.config = config
        self.headless = headless
        self.uncapped = uncapped
        self.clock_fn = clock

        if headless:
            os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

        _claim_dpi_awareness()
        pygame.init()
        pygame.display.set_caption("ROBI")

        size = (config.display.width, config.display.height)
        flags = pygame.FULLSCREEN if config.display.fullscreen and not headless else 0
        self.screen = pygame.display.set_mode(size, flags)
        self.clock = pygame.time.Clock()

        self.machine = StateMachine()
        # Контент необов'язковий: без нього меню просто немає, а команда на
        # `info` відхиляється як непідтримана (D-048).
        self.content = self._load_content(config)
        unsupported = set(Coordinator.UNSUPPORTED)
        if self.content is not None:
            unsupported.discard(ModeName.INFO)
        self.coordinator = Coordinator(
            ModeName.MASCOT, clock=self.clock_fn, unsupported=frozenset(unsupported)
        )
        self.metrics = Metrics()
        self.overlay = Overlay(size)
        self.policy = UrlPolicy(config.crm.allowed_url_schemes, config.crm.allowed_domains)

        self.tof = FakeToF()
        self.nfc = FakeNfc()
        self.outputs = FakeOutputs()
        # Реальний адаптер імпортується лише коли його справді обрано:
        # OpenCV — необов'язкова залежність (D-053).
        if config.vision.backend == "camera":
            from .vision.camera import CameraVision

            self.vision = CameraVision(
                device_index=config.vision.device_index,
                fps=config.vision.fps,
                detect_width=config.vision.detect_width,
                min_face_frac=config.vision.min_face_frac,
                mirror=config.vision.mirror,
                idle_fps=config.vision.idle_fps,
                idle_after_s=config.vision.idle_after_s,
            )
        else:
            self.vision = FakeVision()

        self.modes: dict[ModeName, object] = {
            ModeName.MASCOT: MascotMode(size),
            ModeName.QR: QrMode(size),
        }
        if self.content is not None:
            assets = Path(config.content.assets) if config.content.assets else None
            self.modes[ModeName.INFO] = InfoMode(size, self.content, assets)
        self._current = ModeName.MASCOT

        self.crm: CrmClient | None = None
        if config.crm.enabled:
            self.crm = CrmClient(
                config.crm.url,
                config.device_id,
                config.crm.reconnect_min_s,
                config.crm.reconnect_max_s,
                device_no=config.crm.device_no,
                token=config.crm.token,
                token_url=config.crm.token_url,
                secret_path=config.crm.secret_path,
            )

        self._intent_ttl = 0.0
        self._running = False
        self._camera_check_acc = 0.0

    @staticmethod
    def _load_content(config: Config) -> Content | None:
        """Битий контент не має валити пристрій — він має вимикати меню.

        Маскот на стійці цінніший за меню: якщо в контенті помилка, ROBI
        далі вітає людей і показує QR, а адміністратор бачить причину в
        health, а не чорний екран.
        """
        if not config.content.path:
            return None
        try:
            return Content.load(config.content.path)
        except ContentError as exc:
            print(f"[content] меню вимкнено: {exc}")
            return None

    # -- запуск і зупинка --------------------------------------------------

    def boot(self) -> None:
        """Self-check. `ready` оголошується лише після нього (software.md)."""
        checks = [self.tof.initialize(), self.nfc.initialize(), self.outputs.initialize()]
        if self.config.features.camera:
            checks.append(self.vision.initialize())

        failed = [c.name for c in checks if not c.ok]
        if failed:
            # Необов'язковий модуль переводить у degraded, а не в crash loop.
            self.machine.to(SystemState.DEGRADED, f"failed: {','.join(failed)}")
        else:
            self.machine.to(SystemState.READY, "self-check ok")

        self.modes[ModeName.MASCOT].enter({})
        self._sync_camera()

        if self.crm is not None:
            self.crm.start()

    def shutdown(self) -> None:
        if self.machine.state is not SystemState.SHUTTING_DOWN:
            self.machine.to(SystemState.SHUTTING_DOWN, "requested")
        if self.crm is not None:
            self.crm.stop()
        self.vision.shutdown()
        self.tof.shutdown()
        self.nfc.shutdown()
        self.outputs.shutdown()
        pygame.quit()

    def run(self, max_seconds: float | None = None) -> FrameStats:
        self.boot()
        self._running = True
        elapsed = 0.0
        try:
            while self._running:
                dt = self._tick_clock()
                elapsed += dt
                self.step(dt)
                if max_seconds is not None and elapsed >= max_seconds:
                    break
        finally:
            self.shutdown()
        return self.metrics.snapshot()

    def _tick_clock(self) -> float:
        if self.uncapped:
            return self.clock.tick() / 1000.0
        return self.clock.tick(self.config.display.target_fps) / 1000.0

    # -- один кадр ---------------------------------------------------------

    def step(self, dt: float) -> None:
        # Логіка йде обмеженим кроком, метрики — справжнім часом кадру.
        # TTL команд це не зачіпає: координатор живе на годиннику, а не на
        # dt, тож реальна затримка коректно погасить прострочений сценарій.
        sim_dt = min(dt, MAX_STEP_S)

        # Розклад камери перевіряється раз на секунду, а не раз на кадр:
        # інакше зміна режиму була б єдиним моментом, коли ROBI помічає,
        # що тихі години настали.
        self._camera_check_acc += dt
        if self._camera_check_acc >= 1.0:
            self._camera_check_acc = 0.0
            self._sync_camera()

        events: list[Event] = []
        events.extend(self._pump_window())
        events.extend(self.tof.poll(sim_dt))
        events.extend(self.nfc.poll(sim_dt))
        if self.vision.capturing:
            events.extend(self.vision.poll(sim_dt))

        events = self._route_touches(events)

        self._pump_crm()
        changed = self.coordinator.tick()
        if changed or self.coordinator.mode is not self._current:
            self._switch_to(self.coordinator.mode)

        mode = self.modes[self._current]
        for event in events:
            mode.handle(event)

        intent = mode.update(sim_dt)
        if mode.wants_release():
            # Режим лише повідомляє, що закінчив; звільняє екран координатор.
            self.coordinator.release()
        self._apply_intent(intent, sim_dt)
        self._sync_state()

        mode.draw(self.screen)
        self.overlay.draw(
            self.screen,
            state=self.machine.state.value,
            mode=self._current.value,
            online=self.crm is not None and self.crm.status.connected,
            capturing=self.vision.capturing,
            metrics=self.metrics,
        )
        pygame.display.flip()
        self.metrics.frame(dt)

    def _route_touches(self, events: list[Event]) -> list[Event]:
        """Дотик відкриває меню й тримає його відкритим (D-048).

        Пріоритет `USER` захоплює саме той режим, який дотик відкриває —
        як і передбачав коментар у `_pump_window`. Кожен наступний дотик
        оновлює TTL, тож меню не зникає під пальцем; коли людина пішла,
        активація спливає сама й координатор повертає `mascot`.
        """
        if ModeName.INFO not in self.modes:
            return events
        if not any(isinstance(e, Touch) for e in events):
            return events

        ttl = self.config.content.timeout_s
        if self._current is ModeName.MASCOT:
            if self.coordinator.user_interaction(ModeName.INFO, ttl):
                # Дотик, що відкрив меню, не має ще й натиснути пункт у
                # ньому: координати були з екрана маскота, і будь-яке
                # влучання тут було б випадковим.
                return [e for e in events if not isinstance(e, Touch)]
        elif self._current is ModeName.INFO:
            self.coordinator.user_interaction(ModeName.INFO, ttl)
        return events

    def _pump_window(self) -> list[Event]:
        out: list[Event] = []
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_q):
                    self._running = False
                elif event.key == pygame.K_F1:
                    self.overlay.visible = not self.overlay.visible
                elif event.key == pygame.K_n:
                    self.nfc.simulate_touch()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                w, h = self.screen.get_size()
                out.append(
                    Touch(Source.TOUCH, x=event.pos[0] / w, y=event.pos[1] / h)
                )
                # Пріоритет захоплює не сам дотик, а режим, який він
                # відкриває — див. `_route_touches`. Якби кожен доторк
                # claim'ив USER, випадкове торкання екрана на рецепції
                # глушило б CRM на десятки секунд, і зовні це виглядало б
                # як «ROBI перестав показувати QR» без видимої причини.
        return out

    def accept_command(self, cmd: Command) -> CommandResult:
        """Єдина брама для команд CRM.

        Allowlist перевіряється тут, до координатора й до рендеру: посилання
        з недозволеного домену не має жодного шляху опинитися на екрані
        (D-038). Метод названий і публічний саме тому, що це місце треба
        тестувати прямо, а не через побічні ефекти.
        """
        if cmd.kind is CommandKind.SHOW_QR:
            verdict = self.policy.check(str(cmd.payload.get("value", "")))
            if not verdict.ok:
                return CommandResult(cmd.command_id, CommandStatus.REJECTED, verdict.reason)
        return self.coordinator.apply(cmd)

    def _pump_crm(self) -> None:
        if self.crm is None:
            return
        for cmd in self.crm.drain():
            self.crm.report(self.accept_command(cmd))
        self.coordinator.forget_older_than(0)

    def _switch_to(self, target: ModeName) -> None:
        if target not in self.modes:
            return
        self.modes[self._current].exit()
        self._current = target
        self.modes[target].enter(self.coordinator.active.payload)
        self._sync_camera()

    def _sync_camera(self) -> None:
        """Єдине місце, де вмикається й вимикається захоплення.

        Крім бажання режиму тут діє й розклад: поза тихими годинами
        камера не вмикається взагалі. Це не економія заради економії —
        безвентиляторний планшет гріється, а всередині живе акумулятор,
        якому це скорочує вік.
        """
        mode = self.modes[self._current]
        wants = (
            mode.wants_camera()
            and self.config.features.camera
            and self.config.vision.camera_allowed_at(datetime.now().time())
        )
        if wants and not self.vision.capturing:
            self.vision.start_capture()
        elif not wants and self.vision.capturing:
            self.vision.stop_capture()

    def _apply_intent(self, intent, dt: float) -> None:
        if intent is not None:
            self.outputs.apply(intent.rgb, intent.sound)
            self._intent_ttl = intent.ttl
            return
        if self._intent_ttl > 0.0:
            self._intent_ttl -= dt
            if self._intent_ttl <= 0.0:
                # Сценарій скасовано або добіг кінця: підсвітка гасне.
                self.outputs.apply(None, None)

    def _sync_state(self) -> None:
        current = self.machine.state
        if current in (SystemState.FAULT, SystemState.SERVICE, SystemState.SHUTTING_DOWN):
            return

        offline = self.crm is not None and not self.crm.status.connected
        interacting = self.coordinator.active.priority >= Priority.USER

        if offline and current is not SystemState.OFFLINE and current is not SystemState.DEGRADED:
            self.machine.to(SystemState.OFFLINE, "crm unreachable")
        elif not offline and current is SystemState.OFFLINE:
            self.machine.to(
                SystemState.INTERACTING if interacting else SystemState.READY, "crm restored"
            )
        elif not offline and interacting and current is SystemState.READY:
            self.machine.to(SystemState.INTERACTING, "user")
        elif not offline and not interacting and current is SystemState.INTERACTING:
            self.machine.to(SystemState.READY, "idle")
