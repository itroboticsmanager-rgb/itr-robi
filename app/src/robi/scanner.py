"""Локальний сканер QR і штрихкодів для кіоску ROBI.

Камера в режимі сканування належить лише цьому адаптеру. Кадри не
записуються на диск, не логуються й не надсилаються в CRM: у пам'яті
тримається один стиснений JPEG для локального прев'ю та останній текстовий
результат. Після виходу обидва стираються.

Камера запитується в режимі 30 к/с (Surface віддає до 25) не заради плавності, а заради різкості:
автоекспозиція не може тримати затвор довше за тривалість кадру, тож на
15 к/с рух руки з кодом розмивається вдвічі сильніше. Цикл при цьому читає
лише ті кадри, що потрібні прев'ю (до 15 к/с) чи декодеру: DirectShow
тримає найсвіжіший кадр, тож решта через Python не проходить узагалі.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from .hardware.base import Health

MAX_SCAN_CHARS = 2048

#: Кадр, що прийшов трохи раніше розкладу, все одно береться: інакше при
#: 30 к/с камери й 15 к/с прев'ю тремтіння таймінгу з'їдає кожен другий кадр.
_EARLY = 0.01


@dataclass(frozen=True, slots=True)
class ScanResult:
    value: str
    format: str


class BarcodeScanner:
    name = "scanner"

    def __init__(
        self,
        device_index: int = 0,
        *,
        fps: float = 30.0,
        preview_fps: float = 15.0,
        preview_width: int = 1280,
        jpeg_quality: int = 86,
        decode_fps: float = 5.0,
        mirror_preview: bool = True,
    ) -> None:
        self._device_index = device_index
        self._fps = max(fps, 1.0)
        self._preview_interval = 1.0 / max(preview_fps, 1.0)
        self._preview_width = max(320, preview_width)
        self._jpeg_quality = min(95, max(60, jpeg_quality))
        self._decode_interval = 1.0 / max(decode_fps, 1.0)
        self._mirror_preview = mirror_preview
        self._preview_aspect: float | None = None

        self._cv2 = None
        self._zxing = None
        self._qr = None
        self._barcode = None
        self._capture = None
        self._thread: threading.Thread | None = None
        self._decode_thread: threading.Thread | None = None
        self._decode_event = threading.Event()
        self._decode_frame = None
        self._attempts = 0
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._frame_ready = threading.Condition(self._lock)

        self._available = False
        self._capturing = False
        self._open_attempted = False
        self._preview: bytes | None = None
        self._preview_seq = 0
        self._result: ScanResult | None = None
        self._error = ""
        self._capture_width = 0
        self._capture_height = 0
        self._capture_fps = 0.0
        self._preview_fps = 0.0

    def initialize(self) -> Health:
        try:
            import cv2
        except ImportError:
            self._error = "OpenCV не встановлено"
            return self.health()

        if not hasattr(cv2, "QRCodeDetector"):
            self._error = f"OpenCV {cv2.__version__} не має QR-декодера"
            return self.health()
        try:
            import zxingcpp
        except ImportError:
            zxingcpp = None
        if zxingcpp is None and not hasattr(cv2, "barcode_BarcodeDetector"):
            self._error = "Немає декодера штрихкодів"
            return self.health()
        try:
            self._qr = cv2.QRCodeDetector()
            self._barcode = cv2.barcode_BarcodeDetector() if hasattr(cv2, "barcode_BarcodeDetector") else None
        except Exception as exc:  # noqa: BLE001 - причина лишається локальним health
            self._error = f"декодер не створився: {type(exc).__name__}"
            return self.health()

        self._cv2 = cv2
        self._zxing = zxingcpp
        self._available = True
        self._error = ""
        return self.health()

    @property
    def available(self) -> bool:
        return self._available

    @property
    def capturing(self) -> bool:
        return self._capturing

    def start_capture(self) -> None:
        if not self._available or self._capturing or self._open_attempted:
            return
        self._open_attempted = True
        cv2 = self._cv2
        cap = cv2.VideoCapture(self._device_index, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            self._error = "Не вдалося відкрити камеру"
            return
        # MJPG просимо для USB-камер, яким без нього бракує смуги на Full HD.
        # Камера Surface його ігнорує й віддає 1920x1080 незжатим YUY2 на
        # 25 к/с, тож «каша» на ній не від стиснення. Фокусом вона не
        # керується взагалі (AUTOFOCUS/FOCUS = -1, set -> False); запит
        # автофокуса лишається для інших камер. Фактичний режим читається
        # назад для health UI.
        if hasattr(cv2, "VideoWriter_fourcc") and hasattr(cv2, "CAP_PROP_FOURCC"):
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        cap.set(cv2.CAP_PROP_FPS, round(self._fps))
        if hasattr(cv2, "CAP_PROP_AUTOFOCUS"):
            cap.set(cv2.CAP_PROP_AUTOFOCUS, 1)
        if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._capture_width = round(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self._capture_height = round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._capture_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        self._capture = cap
        self._stop.clear()
        self._decode_event.clear()
        self._error = ""
        self._capturing = True
        self._decode_thread = threading.Thread(target=self._run_decoder, name="robi-scanner-decode", daemon=True)
        self._decode_thread.start()
        self._thread = threading.Thread(target=self._run, name="robi-scanner", daemon=True)
        self._thread.start()

    def stop_capture(self) -> None:
        self._capturing = False
        self._stop.set()
        self._decode_event.set()
        with self._frame_ready:
            # Відкритий MJPEG-потік браузера чекає на кадр; будимо його, щоб
            # з'єднання закрилося разом із камерою, а не через таймаут.
            self._frame_ready.notify_all()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=2.0)
        decode_thread, self._decode_thread = self._decode_thread, None
        if decode_thread is not None:
            decode_thread.join(timeout=2.0)
        if self._capture is not None:
            self._capture.release()
            self._capture = None
        self._open_attempted = False
        with self._lock:
            self._preview = None
            self._result = None
            self._decode_frame = None
        self._preview_fps = 0.0

    def shutdown(self) -> None:
        self.stop_capture()
        self._available = False

    def clear_result(self) -> None:
        with self._lock:
            self._result = None

    def set_preview_aspect(self, aspect) -> None:
        """Пропорції вікна прев'ю з браузера; будь-що дивне означає «весь кадр»."""
        valid = isinstance(aspect, (int, float)) and not isinstance(aspect, bool) and 0.3 <= aspect <= 4.0
        self._preview_aspect = float(aspect) if valid else None

    def frame(self) -> bytes | None:
        with self._lock:
            return self._preview if self._capturing else None

    def wait_frame(self, after: int, timeout: float = 1.0) -> tuple[int, bytes] | None:
        """Перший JPEG прев'ю, новіший за `after`, або None після таймауту чи зупинки.

        Живлення MJPEG-потоку: відповідь іде рівно тоді, коли камера дала
        новий кадр, тож браузер не опитує сервер і не отримує той самий
        кадр двічі.
        """
        with self._frame_ready:
            self._frame_ready.wait_for(
                lambda: not self._capturing or (self._preview is not None and self._preview_seq > after),
                timeout,
            )
            if not self._capturing or self._preview is None or self._preview_seq <= after:
                return None
            return self._preview_seq, self._preview

    def snapshot(self) -> dict:
        with self._lock:
            result = self._result
            ready = self._preview is not None
        return {
            "available": self._available,
            "active": self._capturing,
            "ready": ready,
            "error": self._error,
            "capture_width": self._capture_width,
            "capture_height": self._capture_height,
            "capture_fps": round(self._capture_fps, 1),
            "preview_fps": round(self._preview_fps, 1),
            "result": None if result is None else {
                "value": result.value,
                "format": result.format,
            },
        }

    def health(self) -> Health:
        detail = self._error or ("ZXing" if self._zxing is not None else "OpenCV QR + EAN/UPC")
        return Health(self.name, self._available, detail)

    def _run(self) -> None:
        cv2 = self._cv2
        previewed = 0
        sample_started = time.perf_counter()
        next_decode_at = next_preview_at = 0.0
        while not self._stop.is_set():
            cap = self._capture
            if cap is None:
                break
            with self._lock:
                needs_result = self._result is None
            due = min(next_preview_at, next_decode_at) if needs_result else next_preview_at
            now = time.perf_counter()
            if due > now + _EARLY:
                # Спимо до потрібного кадру. grab() тут не підходить: у
                # DirectShow він не чекає нового кадру, і цикл на ньому
                # крутився б тисячі разів на секунду на цілому ядрі.
                self._stop.wait(due - now)
                continue
            # read() чекає наступного кадру камери й віддає найсвіжіший.
            ok, frame = cap.read()
            if not ok:
                self._error = "Камера не повернула кадр"
                self._stop.wait(0.25)
                continue

            now = time.perf_counter()
            if needs_result and now + _EARLY >= next_decode_at:
                with self._lock:
                    # Замінюємо старий кадр новішим: декодер ніколи не
                    # створює черги й завжди бачить найсвіжіше.
                    self._decode_frame = frame
                self._decode_event.set()
                next_decode_at = max(next_decode_at + self._decode_interval, now)
            if now + _EARLY >= next_preview_at:
                self._publish_preview(cv2, frame)
                previewed += 1
                next_preview_at = max(next_preview_at + self._preview_interval, now)

            sample_elapsed = time.perf_counter() - sample_started
            if sample_elapsed >= 1.0:
                self._preview_fps = previewed / sample_elapsed
                previewed = 0
                sample_started = time.perf_counter()

    def _publish_preview(self, cv2, frame) -> None:
        height, width = frame.shape[:2]
        x0, y0, x1, y1 = self._preview_box(width, height, self._preview_aspect)
        preview = frame[y0:y1, x0:x1]
        crop_w, crop_h = x1 - x0, y1 - y0
        if crop_w > self._preview_width:
            target_h = max(1, round(crop_h * self._preview_width / crop_w))
            # INTER_AREA усереднює пікселі; лінійна інтерполяція при
            # зменшенні дає «сходинки» саме на дрібних модулях коду.
            preview = cv2.resize(preview, (self._preview_width, target_h), interpolation=cv2.INTER_AREA)
        if self._mirror_preview:
            # Дзеркалимо вже зменшений кадр: удвічі менше пікселів.
            preview = cv2.flip(preview, 1)
        encoded, buffer = cv2.imencode(".jpg", preview, [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality])
        if encoded:
            with self._frame_ready:
                self._preview = bytes(buffer)
                self._preview_seq += 1
                self._frame_ready.notify_all()

    @staticmethod
    def _preview_box(width: int, height: int, aspect: float | None) -> tuple[int, int, int, int]:
        """Центральна частина кадру, яку реально показує вікно прев'ю.

        Браузер однаково обрізає кадр під пропорції вікна (object-fit: cover).
        Досі він спершу зменшувався до 1280 px, а видима середина потім
        розтягувалась назад — дрібні модулі коду на екрані злипались у кашу.
        Вирізана тут та сама частина йде в повній роздільності.
        """
        if not aspect:
            return 0, 0, width, height
        if width / height > aspect:
            crop_w = max(1, round(height * aspect))
            x0 = (width - crop_w) // 2
            return x0, 0, x0 + crop_w, height
        crop_h = max(1, round(width / aspect))
        y0 = (height - crop_h) // 2
        return 0, y0, width, y0 + crop_h

    def _run_decoder(self) -> None:
        while not self._stop.is_set():
            if not self._decode_event.wait(0.25):
                continue
            self._decode_event.clear()
            if self._stop.is_set():
                return
            with self._lock:
                frame = self._decode_frame
                self._decode_frame = None
                needs_result = self._result is None
            if frame is None or not needs_result:
                continue
            image = self._grayscale(frame)
            self._attempts += 1
            if self._attempts % 2 == 0:
                # Кожна друга спроба — збільшений центр: туди людина тримає
                # код за рамкою, і саме там губляться дрібні модулі.
                image = self._zoom_center(image)
            result = self._decode(image)
            if result is not None:
                with self._lock:
                    if self._result is None:
                        self._result = result

    def _grayscale(self, frame):
        # Обидва декодери працюють з яскравістю. Один cvtColor тут дешевший,
        # ніж неявне перетворення всередині кожного з них.
        if self._cv2 is None or getattr(frame, "ndim", 0) != 3:
            return frame
        return self._cv2.cvtColor(frame, self._cv2.COLOR_BGR2GRAY)

    def _zoom_center(self, gray):
        # Фронтальна камера без автофокуса: код тримають далі, і модулі
        # дрібного QR виходять по 1.5–2.5 px із розфокусом. Центральна
        # половина кадру (це й є рамка наведення), збільшена вдвічі та
        # підгострена, читається там, де повний кадр — ні (D-062), а коштує
        # стільки ж: 960x540 x2 — це ті самі пікселі, що й 1920x1080.
        cv2 = self._cv2
        if cv2 is None or getattr(gray, "ndim", 0) != 2:
            return gray
        height, width = gray.shape
        crop = gray[height // 4: height - height // 4, width // 4: width - width // 4]
        zoomed = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        soft = cv2.GaussianBlur(zoomed, (0, 0), 1.5)
        return cv2.addWeighted(zoomed, 1.8, soft, -0.8, 0)

    def _decode(self, frame) -> ScanResult | None:
        if self._zxing is not None:
            try:
                # Опції ZXing навмисно типові: try_rotate=False дешевший на
                # ~40 %, але не читає вертикально повернутий штрихкод.
                for barcode in self._zxing.read_barcodes(frame):
                    raw_format = getattr(barcode, "format", "CODE")
                    format_name = getattr(raw_format, "name", None) or str(raw_format)
                    result = self._first((getattr(barcode, "text", ""),), format_name)
                    if result is not None:
                        return result
                # ZXing читає QR і штрихкоди краще за OpenCV. Прогнати ще й
                # OpenCV по кожному порожньому кадру означало б утричі більше
                # CPU на пошук, який нічого нового не знаходить.
                return None
            except Exception:  # noqa: BLE001 - OpenCV лишається локальним fallback
                pass

        try:
            value, _points, _straight = self._qr.detectAndDecode(frame)
            result = self._first((value,), "QR_CODE")
            if result is not None:
                return result
        except Exception:  # noqa: BLE001 - один битий кадр не завершує сканер
            pass

        try:
            if self._barcode is None:
                return None
            decoded = self._barcode.detectAndDecodeWithType(frame)
            if len(decoded) == 4:
                found, values, formats, _points = decoded
                if found:
                    for value, format_name in zip(values, formats, strict=False):
                        result = self._first((value,), str(format_name or "BARCODE"))
                        if result is not None:
                            return result
        except Exception:  # noqa: BLE001 - продовжуємо з наступного кадру
            pass
        return None

    @staticmethod
    def _first(values, format_name: str) -> ScanResult | None:
        for raw in values or ():
            value = str(raw or "").strip()
            if value:
                safe = "".join(char for char in value if char.isprintable() or char in "\r\n\t")
                return ScanResult(safe[:MAX_SCAN_CHARS], format_name[:40] or "CODE")
        return None
