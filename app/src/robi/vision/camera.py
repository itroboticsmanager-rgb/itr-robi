"""Реальний vision через камеру пристрою (D-053).

Межа D-027 тут не декларація, а конструкція: кадр живе лише всередині
робочого потоку й гине разом з ітерацією циклу. Назовні клас віддає
`FaceSeen` — кількість, позиція, розмір. Поля під кадр немає, тож решта
системи не може його отримати, залогувати чи відправити в CRM навіть
помилково.

Детектор — YuNet (`cv2.FaceDetectorYN`). Каскади Хаара, на які спиралася
перша редакція D-053, з OpenCV 5 прибрані: `CascadeClassifier` більше
немає в біндингах, а тека `cv2.data.haarcascades` порожня. Модель YuNet
лежить поруч у `models/` і входить у пакет — пристрій не має ходити по
неї в мережу, бо offline-стійкість є вимогою, а не зручністю.

OpenCV містить і `FaceRecognizerSF`, тобто розпізнавання конкретних
людей. Тут він не використовується й використаний бути не може: D-027
забороняє ідентифікацію, а `FaceSeen` не має поля, куди такий результат
можна було б покласти.

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
from pathlib import Path

from ..events import FaceSeen, Source
from ..hardware.base import Health
from .base import VisionStats

MODEL = Path(__file__).with_name("models") / "face_detection_yunet_2023mar.onnx"


class CameraVision:
    name = "vision"

    def __init__(
        self,
        device_index: int = 0,
        fps: float = 4.0,
        detect_width: int = 224,
        min_face_frac: float = 0.08,
        score_threshold: float = 0.6,
        mirror: bool = True,
        idle_fps: float = 1.0,
        idle_after_s: float = 3.0,
    ) -> None:
        # D-033: достатньо низької роздільності й кількох кадрів за секунду.
        self._device_index = device_index
        self._interval = 1.0 / max(fps, 0.1)
        # Стійка порожня більшу частину доби, тож повна частота в спокої —
        # це детекція порожнього коридору цілодобово. У спокої адаптер
        # переходить на idle_fps і повертається до повної, щойно когось
        # побачив. Людина цього не помічає: вона підходить, і ROBI реагує
        # протягом секунди.
        self._idle_interval = 1.0 / max(idle_fps, 0.05)
        self._idle_after_s = idle_after_s
        self._last_seen = 0.0
        self._detect_width = detect_width
        self._min_face_frac = min_face_frac
        self._score_threshold = score_threshold
        self._mirror = mirror

        self._cv2 = None
        self._detector = None
        self._capture = None
        self._input_size: tuple[int, int] | None = None

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

        if not hasattr(cv2, "FaceDetectorYN"):
            self._ok = False
            self._detail = f"opencv {cv2.__version__} без FaceDetectorYN"
            return self.health()

        if not MODEL.exists():
            self._ok = False
            self._detail = f"модель не знайдено: {MODEL.name}"
            return self.health()

        self._cv2 = cv2
        try:
            self._detector = cv2.FaceDetectorYN.create(
                str(MODEL),
                "",
                (self._detect_width, self._detect_width),
                self._score_threshold,
                0.3,
                5000,
            )
        except Exception as exc:  # noqa: BLE001 — причина йде в health, а не в падіння
            self._ok = False
            self._detail = f"детектор не створився: {exc}"
            return self.health()

        self._ok = True
        self._detail = f"opencv {cv2.__version__}, yunet"
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
        # Стартуємо в активному режимі: перед пристроєм цілком може вже
        # хтось стояти, і зустрічати його сповільненою детекцією не варто.
        self._last_seen = time.monotonic()
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
        self._input_size = None
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
            small_h = max(int(height * scale), 1)
            small = cv2.resize(frame, (self._detect_width, small_h))

            # setInputSize недешевий, тож викликається лише коли розмір змінився.
            size = (self._detect_width, small_h)
            if size != self._input_size:
                self._detector.setInputSize(size)
                self._input_size = size

            _, faces = self._detector.detect(small)
            result = self._largest(self._filter(faces), size[0], size[1], self._mirror)
            with self._lock:
                self._latest = result
            # `frame` і `small` виходять зі скоупу тут: далі межі цього
            # циклу зображення не існує ніде.

            if result[0] > 0:
                self._last_seen = time.monotonic()

            elapsed = time.perf_counter() - started
            self._stop.wait(max(self._next_interval() - elapsed, 0.0))

    def _next_interval(self) -> float:
        """Повна частота, поки когось видно; далі — сповільнення.

        Повернення до повної частоти миттєве: щойно обличчя знайдено,
        наступний кадр іде вже без затримки. Дорого тільки чекати, а не
        реагувати.
        """
        if time.monotonic() - self._last_seen <= self._idle_after_s:
            return self._interval
        return self._idle_interval

    def _filter(self, faces) -> list:
        """Відкидає надто дрібні знахідки: людина в глибині холу нам не адресат.

        Поріг навмисно невисокий: обличчя в профіль **вужче** за анфас,
        тож надто суворий фільтр губить людину саме тоді, коли вона
        повертається вбік — а це найчастіший рух біля стійки.
        """
        if faces is None:
            return []
        min_w = self._detect_width * self._min_face_frac
        return [f[:4] for f in faces if float(f[2]) >= min_w]

    @staticmethod
    def _largest(
        faces, frame_w: int, frame_h: int, mirror: bool = True
    ) -> tuple[int, float, float, float]:
        """Найбільше обличчя — це найближча людина; на неї й дивимось.

        `mirror` віддзеркалює горизонталь, і це не косметика. Екран —
        картинка, а не співрозмовник: додатний `x` зсуває зіницю вправо
        з погляду того, хто дивиться. Сира камера дає протилежне — коли
        людина йде праворуч, у кадрі вона зміщується ліворуч. Без
        віддзеркалення погляд відводиться від людини замість стежити за
        нею. Те саме роблять відеодзвінки для власного зображення.
        """
        count = len(faces)
        if count == 0:
            return (0, 0.0, 0.0, 0.0)
        x, y, w, h = max(faces, key=lambda f: float(f[2]) * float(f[3]))
        cx = (float(x) + float(w) / 2.0) / float(frame_w)
        cy = (float(y) + float(h) / 2.0) / float(frame_h)
        # -1..1 відносно центра кадру, як вимагає FaceSeen.
        nx = cx * 2.0 - 1.0
        return (count, -nx if mirror else nx, cy * 2.0 - 1.0, float(w) / float(frame_w))

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
