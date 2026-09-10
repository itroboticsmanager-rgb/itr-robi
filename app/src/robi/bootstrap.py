"""Складання застосунку й головний цикл.

Тут єдине місце, де компоненти знають одне про одного. Усе інше
спілкується через контракти з `hardware.base`, `vision.base` і `modes.base`,
тому заміна fake-адаптера на реальний не зачіпає жодного режиму.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import pygame

from .banners import BannerStore
from .content_store import ContentStore
from .config import Config
from .content import Content, ContentError
from .events import (
    Command,
    CommandKind,
    CommandResult,
    CommandStatus,
    Event,
    Source,
    Swipe,
    Touch,
    now,
)
from .hardware.fake import FakeNfc, FakeOutputs, FakeToF
from .health.metrics import FrameStats, Metrics
from .integration.crm import CrmClient
from .integration.policy import UrlPolicy
from .modes.info import InfoMode
from .modes.mascot import MascotMode
from .modes.qr import QrMode
from .state.coordinator import Coordinator, ModeName, Priority
from .state.machine import StateMachine, SystemState
from .web import LocalWebService, WebServiceError, snapshot
from .web.bridge import WebBridge
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

#: Наскільки далеко може поїхати палець, і рух ще рахується натисканням.
TAP_SLOP = 0.03

#: Наскільки довгим має бути протягування, щоб вважатися свайпом. Частка
#: висоти екрана: на 1280 px це приблизно 150 px — достатньо, щоб не
#: спрацьовувати від тремтіння руки, і мало, щоб жест був невимушеним.
SWIPE_MIN = 0.12


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
        # `info` відхиляється як непідтримана (D-048). Набір із CRM, якщо він
        # уже приходив, важливіший за локальний файл.
        self._content_store = ContentStore(config.content.cache_dir) if config.content.cache_dir else None
        self._content_pending: tuple[Content | None] | None = None
        self._content_thread: threading.Thread | None = None
        self._content_stop = threading.Event()
        self.content, self._content_assets = self._initial_content(config)
        unsupported = set(Coordinator.UNSUPPORTED)
        if self.content is not None:
            unsupported.discard(ModeName.INFO)
        self.coordinator = Coordinator(
            ModeName.MASCOT, clock=self.clock_fn, unsupported=frozenset(unsupported)
        )
        self.metrics = Metrics()
        self._web: LocalWebService | None = None
        self._web_revision = 0
        self._web_bridge = WebBridge(self.clock_fn)
        self._entered_activation = None
        self._web_qr_key = None
        self._web_qr = None
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
            self.modes[ModeName.INFO] = InfoMode(size, self.content, self._content_assets)
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

        self._banners = self._make_banner_store(config)
        self._banner_images: dict[int, object] = {}
        self._banner_thread: threading.Thread | None = None
        self._banner_stop = threading.Event()
        self._wire_showcase()

        self._intent_ttl = 0.0
        self._running = False
        self._press: tuple[float, float] | None = None

    @staticmethod
    def _make_banner_store(config: Config) -> BannerStore | None:
        if not config.banners.cache_dir:
            return None
        return BannerStore(config.banners.cache_dir)

    def _wire_showcase(self) -> None:
        """Дає вітрині те, що вона показує: банери з кешу й кнопки з меню.

        Кнопки беруться з кореня контент-меню (`D-048`), а не з окремого
        списку: два переліки того самого розійшлися б першої ж правки.
        """
        mascot = self.modes.get(ModeName.MASCOT)
        if mascot is None:
            return
        if self._banners is not None:
            mascot.banners = self._banners.load()
            mascot._image_for = self._banner_image
        if self.content is not None:
            root = self.content.node(self.content.root)
            from .ui.showcase import NavAction

            mascot.buttons = [
                NavAction(
                    self.content.label_for(node_id),
                    node_id,
                    self.content.icon_for(node_id),
                )
                for node_id in root.items
            ]
        else:
            mascot.buttons = []

    def _banner_image(self, banner):
        """Картинка з кешу. Битий чи відсутній файл дає банер без картинки."""
        if self._banners is None:
            return None
        cached = self._banner_images.get(banner.id)
        if cached is not None:
            return cached
        path = self._banners.image_path(banner)
        if not path.is_file():
            return None
        try:
            surface = pygame.image.load(str(path)).convert_alpha()
        except pygame.error:
            return None
        self._banner_images[banner.id] = surface
        return surface

    def _refresh_banners_forever(self) -> None:
        """Оновлення вітрини у власному потоці.

        Мережа в головному циклі означала б завмирання кадру, а вітрина
        стоїть перед людьми: рвана анімація помітніша за старий банер.
        """
        secret = ""
        if self.crm is not None:
            secret = self.crm.read_secret()
        while not self._banner_stop.is_set():
            if self._banners is not None and self.config.banners.url and secret:
                ok, _ = self._banners.refresh(self.config.banners.url, secret)
                if ok:
                    mascot = self.modes.get(ModeName.MASCOT)
                    if mascot is not None:
                        # Список замінюється цілком, а кеш картинок чиститься:
                        # інакше зниклий банер лишався б у пам'яті назавжди.
                        mascot.banners = self._banners.load()
                        self._banner_images.clear()
            self._banner_stop.wait(self.config.banners.refresh_s)

    def _initial_content(self, config: Config) -> tuple[Content | None, Path | None]:
        """Меню з CRM, якщо набір уже був; інакше локальний файл.

        Порожній набір із CRM — рішення адміністратора, а не збій, тому
        локальний приклад на його місце не підставляється.
        """
        if self._content_store is not None:
            has_set, content = self._content_store.load()
            if has_set:
                return content, self._content_store.dir
        assets = Path(config.content.assets) if config.content.assets else None
        return self._load_content(config), assets

    def _refresh_content_forever(self) -> None:
        """Меню з CRM у власному потоці: мережа не має смикати кадр."""
        secret = self.crm.read_secret() if self.crm is not None else ""
        while not self._content_stop.is_set():
            if self._content_store is not None and secret:
                ok, reason = self._content_store.refresh(self.config.content.url, secret)
                if ok:
                    has_set, content = self._content_store.load()
                    if has_set and content != self.content:
                        # Підміна — лише в головному циклі: там живуть режими
                        # й координатор, і там видно, чи хтось зараз у меню.
                        self._content_pending = (content,)
                elif reason.startswith("invalid"):
                    print(f"[content] набір із CRM відхилено, лишається попередній: {reason}")
            self._content_stop.wait(self.config.content.refresh_s)

    def _apply_pending_content(self) -> None:
        """Нове меню з CRM стає на місце, лише коли в ньому ніхто не гортає.

        Батько, що читає опис курсу, не має побачити, як сторінка зникає з-під
        пальця: набір дочекається повернення кіоску на головну.
        """
        pending = self._content_pending
        if pending is None or self._current is ModeName.INFO:
            return
        self._content_pending = None
        self.content = pending[0]
        self._content_assets = self._content_store.dir if self._content_store is not None else None
        unsupported = set(self.coordinator.unsupported)
        if self.content is None:
            unsupported.add(ModeName.INFO)
            self.modes.pop(ModeName.INFO, None)
        else:
            unsupported.discard(ModeName.INFO)
            self.modes[ModeName.INFO] = InfoMode(
                self.screen.get_size(), self.content, self._content_assets
            )
        self.coordinator.unsupported = frozenset(unsupported)
        self._wire_showcase()
        self._web_revision += 1

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

        if self._banners is not None and self.config.banners.url:
            self._banner_thread = threading.Thread(
                target=self._refresh_banners_forever, name="robi-banners", daemon=True
            )
            self._banner_thread.start()

        if self._content_store is not None and self.config.content.url:
            self._content_thread = threading.Thread(
                target=self._refresh_content_forever, name="robi-content", daemon=True
            )
            self._content_thread.start()

        self._entered_activation = self.coordinator.active
        self._publish_web()
        self._start_web()

    def _start_web(self) -> None:
        """Підняти локальну службу для веб-інтерфейсу, якщо її ввімкнено.

        Зайнятий порт переводить у `degraded`, а не валить застосунок: на
        рецепції кіоск без веб-частини все одно корисніший за темний екран.
        """
        if not self.config.web.enabled:
            return
        cfg = self.config.web
        try:
            self._web = LocalWebService(
                self._web_snapshot, host=cfg.host, port=cfg.port, root=cfg.root,
                action=self._web_bridge.submit, asset=self._web_asset,
            )
            self._web.start()
        except WebServiceError as exc:
            self._web = None
            self.machine.to(SystemState.DEGRADED, f"web: {exc}")

    def _web_snapshot(self) -> dict:
        return self._web_bridge.read()

    def _publish_web(self) -> None:
        if not self.config.web.enabled:
            return
        mascot = self.modes[ModeName.MASCOT]
        active = self.coordinator.active
        state = snapshot(
            self.content,
            mascot.face.state,
            device_id=self.config.device_id,
            site=self.config.site,
            revision=self._web_revision,
        )
        mode = active.mode.value
        if mode == "mascot":
            mode = "home"
        # Only the validated, current QR is retained. Never persist payment data.
        if active is not self._web_qr_key:
            self._web_qr_key, self._web_qr = active, None
            value = str(active.payload.get("value", ""))
            if mode == "qr" and self.policy.check(value).ok:
                import segno
                self._web_qr = [list(row) for row in segno.make(value, micro=False).matrix]
        state["display"] = {
            "mode": mode, "node": str(active.payload.get("node", "")),
            "qr": self._web_qr,
            "title": str(active.payload.get("title") or "Продовжимо на телефоні"),
            "priority": int(active.priority),
        }
        state["idle_timeout_s"] = self.config.content.timeout_s
        state["mascot"]["gaze"] = list(mascot.face._gaze) if self.vision.capturing and mascot._since_face < 1.5 else None
        state["banners"] = [
            {"id": b.id, "title": b.title, "description": b.description,
             "image": f"/media/banner/{b.id}" if b.image else "",
             "image_version": b.image_version,
             "bg_color": b.bg_color, "text_color": b.text_color,
             "target_node": b.target_node}
            for b in mascot.banners
        ]
        for node in state["content"]["nodes"]:
            node["image"] = f"/media/content/{quote(node['id'], safe='')}" if node["image"] else ""
        self._web_bridge.publish(state, active)

    def _web_asset(self, route: str) -> Path | None:
        target = None
        root = None
        if route.startswith("/media/banner/") and self._banners is not None:
            banner = next((b for b in self.modes[ModeName.MASCOT].banners
                           if str(b.id) == route.removeprefix("/media/banner/")), None)
            if banner is not None and banner.image:
                root, target = self._banners.dir, self._banners.image_path(banner)
        elif route.startswith("/media/content/") and self.content and self._content_assets:
            node = self.content.nodes.get(route.removeprefix("/media/content/"))
            if node and node.image:
                root = self._content_assets
                target = root / node.image
        if target is None or root is None:
            return None
        target = target.resolve()
        return target if target.is_relative_to(root.resolve()) and target.is_file() else None

    def _web_action(self, payload: dict) -> dict:
        action = payload.get("action")
        active = self.coordinator.active
        token = self._web_snapshot().get("display", {}).get("token")
        if action in ("close", "activity"):
            if payload.get("token") != token or active is not self._web_bridge.activation:
                return {"ok": False, "reason": "stale"}
            if active.priority > Priority.USER or active.expired(self.clock_fn()):
                return {"ok": False, "reason": "preempted"}
            if action == "close":
                self.coordinator.release()
            elif active.priority <= Priority.USER:
                # Touch renews the visitor's menu, never a payment QR.
                if active.mode is ModeName.QR:
                    return {"ok": False, "reason": "fixed_expiry"}
                active.priority = Priority.USER
                active.expires_at = self.clock_fn() + self.config.content.timeout_s
        elif action == "menu":
            node = str(payload.get("node", ""))
            if not self.content or (node and node not in self.content.nodes):
                return {"ok": False, "reason": "unknown_node"}
            ok = self.coordinator.request(
                ModeName.INFO,
                Priority.USER, self.config.content.timeout_s,
                payload={"node": node, "web_menu": True},
            )
            if not ok:
                return {"ok": False, "reason": "preempted"}
        else:
            return {"ok": False, "reason": "unknown_action"}
        self._publish_web()
        return {"ok": True, "snapshot": self._web_snapshot()}

    def shutdown(self) -> None:
        self._banner_stop.set()
        self._content_stop.set()
        if self._web is not None:
            self._web.stop()
            self._web = None
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

        events: list[Event] = []
        events.extend(self._pump_window())
        events.extend(self.tof.poll(sim_dt))
        events.extend(self.nfc.poll(sim_dt))
        if self.vision.capturing:
            events.extend(self.vision.poll(sim_dt))

        events = self._route_touches(events)

        self._apply_pending_content()
        self._web_bridge.drain(self._web_action)
        self._pump_crm()
        changed = self.coordinator.tick()
        active = self.coordinator.active
        reenter = active is not self._entered_activation and (
            active.command_id is not None or active.payload.get("web_menu")
        )
        if changed or self.coordinator.mode is not self._current or reenter:
            self._switch_to(self.coordinator.mode)
        self._entered_activation = active

        mode = self.modes[self._current]
        for event in events:
            mode.handle(event)

        # Камера узгоджується щокадру, після подій. Раніше тут стояла
        # перевірка раз на секунду заради економії, але вона коштувала
        # чутливості: людина тягне ROBI вниз, а погляд оживає із затримкою.
        # Ціна щокадрової перевірки — кілька порівнянь при бюджеті 16.7 мс,
        # з яких рендер займає 2.4.
        self._sync_camera()

        # Кнопка вітрини просить відкрити гілку меню. Як і в `_route_touches`,
        # пріоритет захоплює той режим, який дію справді відкриває.
        pending = getattr(mode, "take_pending_node", None)
        node = pending() if pending is not None else None
        if node and ModeName.INFO in self.modes:
            self.coordinator.request(
                ModeName.INFO,
                Priority.USER,
                self.config.content.timeout_s,
                payload={"node": node},
            )

        intent = mode.update(sim_dt)
        if mode.wants_release():
            # Режим лише повідомляє, що закінчив; звільняє екран координатор.
            self.coordinator.release()
        self._apply_intent(intent, sim_dt)
        self._sync_state()

        self._publish_web()
        if not (self.headless and self.config.web.enabled):
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
                self._press = (event.pos[0] / w, event.pos[1] / h)
            elif event.type == pygame.MOUSEBUTTONUP and self._press is not None:
                w, h = self.screen.get_size()
                start, self._press = self._press, None
                end = (event.pos[0] / w, event.pos[1] / h)
                dx, dy = end[0] - start[0], end[1] - start[1]

                # Намір визначається при відпусканні, а не при натисканні.
                # Інакше протягування пальцем спершу відкривало б меню, а
                # вже потім виявлялося свайпом — людина бачила б спалах
                # чужого екрана посеред власного жесту.
                if abs(dy) >= SWIPE_MIN and abs(dy) > abs(dx):
                    out.append(Swipe(
                        Source.TOUCH,
                        direction="down" if dy > 0 else "up",
                        x=start[0], y=start[1], distance=abs(dy),
                    ))
                elif abs(dx) < TAP_SLOP and abs(dy) < TAP_SLOP:
                    # Пріоритет захоплює не сам дотик, а режим, який він
                    # відкриває — див. `_route_touches`. Якби кожен доторк
                    # claim'ив USER, випадкове торкання екрана на рецепції
                    # глушило б CRM на десятки секунд, і зовні це виглядало б
                    # як «ROBI перестав показувати QR» без видимої причини.
                    out.append(Touch(Source.TOUCH, x=end[0], y=end[1]))
                # Проміжне — не дотик і не свайп: змазаний рух, і вгадувати
                # намір за нього не варто.
        return out

    def accept_command(self, cmd: Command) -> CommandResult:
        """Єдина брама для команд CRM.

        Allowlist перевіряється тут, до координатора й до рендеру: посилання
        з недозволеного домену не має жодного шляху опинитися на екрані
        (D-038). Метод названий і публічний саме тому, що це місце треба
        тестувати прямо, а не через побічні ефекти.
        """
        if cmd.kind is CommandKind.SHOW_QR or (
            cmd.kind is CommandKind.SET_MODE and cmd.payload.get("mode") == "qr"
        ):
            verdict = self.policy.check(str(cmd.payload.get("value", "")))
            if not verdict.ok:
                return CommandResult(cmd.command_id, CommandStatus.REJECTED, verdict.reason)
        if cmd.kind is CommandKind.SET_MODE and cmd.payload.get("mode") == "info":
            node = str(cmd.payload.get("node", "")).strip()
            if node and (not self.content or node not in self.content.nodes):
                return CommandResult(cmd.command_id, CommandStatus.REJECTED, "unknown_node")
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
        if target is ModeName.MASCOT:
            self.modes[target].set_state_from(str(self.coordinator.active.payload.get("state", "idle")))
        self._entered_activation = self.coordinator.active
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
