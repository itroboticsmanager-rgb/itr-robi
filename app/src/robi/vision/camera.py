"""Реальний vision через камеру пристрою (D-053).

Межа D-027 тут не декларація, а конструкція: кадр живе лише всередині
робочого потоку й гине разом з ітерацією циклу. Назовні клас віддає
`FaceSeen` — кількість, позиція, розмір. Поля під кадр немає, тож решта
системи не може його отримати, залогувати чи відправити в CRM навіть
помилково.

Захоплення йде в окремому потоці навмисно. Детекція коштує десятки
мілісекунд, а бюджет кадру анімації — 16.7 мс: якби вони жили в одному
циклі, обличчя смикалося б у такт детекції. Головний потік лише забирає
готовий результат, тому вартість vision не додається до вартості кадру.

OpenCV імпортується всередині `initialize()`, а не на рівні модуля.
Це навмисно: залежність необов'язкова (D-053), і застосунок із
`backend = "fake"` має працювати на машині, де OpenCV не встановлено.
"""

from __future__ import annotations

import threading
import time

from ..events import FaceSeen, Source
from ..hardware.base import Health
from .base import VisionStats


class CameraVision:
    name = "vision"

    def __init__(
        self,
        device_index: int = 0,
        fps: float = 8.0,
        detect_width: int = 320,
        min_face_frac: float = 0.12,
    ) -> None:
        # D-033: достатньо низької роздільності й кількох кадрів за секунду.
        self._device_index = device_index
        self._interval = 1.0 / max(fps, 0.1)
        self._detect_width = detect_width
        self._min_face_frac = min_face_frac

        self._cv2 = None
        self._cascade = None
        self._capture = None

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

        # Єдине, що потік віддає назовні. Кадру тут немає й бути не може.
        self._latest: tuple[int, float, float, float] | None = None

        self._ok = False
        self._capturing = False
        self._frames = 0
        self._detections = 0
        self._detail = "not initialised"

    # -- життєвий цикл -----------------------------------------------------

    def initialize(self) -> Health:
        try:
            import cv2
        except ImportError:
            self._ok = False
            self._detail = "opencv не встановлено (extra 'camera')"
            return self.health()

        self._cv2 = cv2
        path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(path)
        if cascade.empty():
            self._ok = False
            self._detail = "каскад не завантажився"
            return self.health()

        self._cascade = cascade
        self._ok = True
        self._detail = f"opencv {cv2.__version__}, haar"
        return self.health()

    def start_capture(self) -> None:
        if not self._ok or self._capturing:
            return
        cap = self._cv2.VideoCapture(self._device_index, self._cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            self._detail = f"камеру {self._device_index} не вдалося відкрити"
            return
        self._capture = cap
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="robi-vision", daemon=True)
        self._capturing = True
        self._thread.start()

    def stop_capture(self) -> None:
        """Зупинка справжня: камера звільняється, і за цим гасне індикатор (D-029)."""
        if not self._capturing:
            return
        self._capturing = False
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2.0)
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        with self._lock:
            self._latest = None

    @property
    def capturing(self) -> bool:
        return self._capturing

    def shutdown(self) -> None:
        self.stop_capture()
        self._ok = False
        self._detail = "shutdown"

    # -- робочий потік -----------------------------------------------------

    def _run(self) -> None:
        cv2 = self._cv2
        while not self._stop.is_set():
            started = time.perf_counter()
            cap = self._capture
            if cap is None:
                break

            ok, frame = cap.read()
            if not ok:
                # Камеру могли забрати (сон, від'єднання). Не крутимо цикл на повній.
                self._stop.wait(0.5)
                continue

            height, width = frame.shape[:2]
            scale = self._detect_width / float(width) if width else 1.0
            small = cv2.resize(frame, (self._detect_width, max(int(height * scale), 1)))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            gray = cv2.equalizeHist(gray)

            sh, sw = gray.shape[:2]
            min_side = max(int(sw * self._min_face_frac), 20)
            faces = self._cascade.detectMultiScale(
                gray, scaleFactor=1.2, minNeighbors=5, minSize=(min_side, min_side)
            )

            result = self._largest(faces, sw, sh)
            with self._lock:
                self._latest = result
            # `frame`, `small` і `gray` виходять зі скоупу тут: далі межі
            # цього циклу зображення не існує ніде.

            elapsed = time.perf_counter() - started
            self._stop.wait(max(self._interval - elapsed, 0.0))

    @staticmethod
    def _largest(faces, frame_w: int, frame_h: int) -> tuple[int, float, float, float]:
        """Найбільше обличчя — це найближча людина; на неї й дивимось."""
        count = len(faces)
        if count == 0:
            return (0, 0.0, 0.0, 0.0)
        x, y, w, h = max(faces, key=lambda f: int(f[2]) * int(f[3]))
        cx = (float(x) + float(w) / 2.0) / float(frame_w)
        cy = (float(y) + float(h) / 2.0) / float(frame_h)
        # -1..1 відносно центра кадру, як вимагає FaceSeen.
        return (count, cx * 2.0 - 1.0, cy * 2.0 - 1.0, float(w) / float(frame_w))

    # -- те, що бачить застосунок ------------------------------------------

    def poll(self, dt: float) -> list[FaceSeen]:
        if not (self._ok and self._capturing):
            return []
        with self._lock:
            latest, self._latest = self._latest, None
        if latest is None:
            return []

        count, x, y, size = latest
        self._frames += 1
        if count:
            self._detections += 1
        return [FaceSeen(Source.VISION, count=count, x=x, y=y, size=size)]

    def stats(self) -> VisionStats:
        return VisionStats(self._frames, self._detections, self._capturing)

    def health(self) -> Health:
        return Health(self.name, self._ok, self._detail)
