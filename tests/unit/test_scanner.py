import threading
import time

from robi.scanner import BarcodeScanner, MAX_SCAN_CHARS, ScanResult


class QrFound:
    def detectAndDecode(self, _frame):
        return "https://itrobotics.com.ua/check", None, None


class QrEmpty:
    calls = 0

    def detectAndDecode(self, _frame):
        self.calls += 1
        return "", None, None


class ZxingEmpty:
    def read_barcodes(self, _frame):
        return []


class ZxingBroken:
    def read_barcodes(self, _frame):
        raise RuntimeError("битий кадр")


class BarcodeFound:
    def detectAndDecodeWithType(self, _frame):
        return True, ("4820001234567",), ("EAN_13",), object()


class ZxingFound:
    def read_barcodes(self, _frame):
        barcode = type("Barcode", (), {"text": "CODE128-ROBI", "format": type("Format", (), {"name": "Code128"})()})()
        return [barcode]


def test_qr_result_is_read_as_text_without_executing_it():
    scanner = BarcodeScanner()
    scanner._qr = QrFound()
    scanner._barcode = BarcodeFound()
    result = scanner._decode(object())
    assert result.value == "https://itrobotics.com.ua/check"
    assert result.format == "QR_CODE"


def test_barcode_is_used_when_there_is_no_qr():
    scanner = BarcodeScanner()
    scanner._qr = QrEmpty()
    scanner._barcode = BarcodeFound()
    result = scanner._decode(object())
    assert result.value == "4820001234567"
    assert result.format == "EAN_13"


def test_zxing_handles_broad_barcode_formats_before_the_opencv_fallback():
    scanner = BarcodeScanner()
    scanner._zxing = ZxingFound()
    scanner._qr = QrEmpty()
    scanner._barcode = None
    result = scanner._decode(object())
    assert result.value == "CODE128-ROBI"
    assert result.format == "Code128"


def test_opencv_does_not_rescan_empty_frames_when_zxing_is_available():
    scanner = BarcodeScanner()
    scanner._zxing = ZxingEmpty()
    scanner._qr = QrEmpty()
    scanner._barcode = BarcodeFound()
    assert scanner._decode(object()) is None
    assert scanner._qr.calls == 0


def test_opencv_still_decodes_when_zxing_fails_on_a_frame():
    scanner = BarcodeScanner()
    scanner._zxing = ZxingBroken()
    scanner._qr = QrFound()
    scanner._barcode = None
    assert scanner._decode(object()) == ScanResult("https://itrobotics.com.ua/check", "QR_CODE")


def test_every_second_attempt_reads_the_zoomed_centre_for_small_codes():
    scanner = BarcodeScanner()
    seen = []
    scanner._grayscale = lambda frame: frame
    scanner._zoom_center = lambda image: f"zoomed-{image}"
    scanner._decode = lambda image: seen.append(image)
    worker = threading.Thread(target=scanner._run_decoder)
    worker.start()
    try:
        for n in range(3):
            scanner._decode_frame = f"frame{n}"
            scanner._decode_event.set()
            deadline = time.monotonic() + 1.0
            while len(seen) <= n and time.monotonic() < deadline:
                time.sleep(0.005)
    finally:
        scanner._stop.set()
        scanner._decode_event.set()
        worker.join(timeout=1.0)
    assert seen == ["frame0", "zoomed-frame1", "frame2"]


def test_preview_is_the_visible_part_of_the_frame_at_native_resolution():
    box = BarcodeScanner._preview_box
    assert box(1920, 1080, None) == (0, 0, 1920, 1080)
    # Майже квадратне вікно: повна висота, середина по ширині, без масштабу.
    assert box(1920, 1080, 0.95) == (447, 0, 1473, 1080)
    # Вікно ширше за кадр: повна ширина, середня смуга по висоті.
    assert box(1920, 1080, 3.0) == (0, 220, 1920, 860)


def test_preview_aspect_from_the_browser_is_validated():
    scanner = BarcodeScanner()
    scanner.set_preview_aspect(0.95)
    assert scanner._preview_aspect == 0.95
    for bad in ("1", True, 0, -1, 10, float("nan"), None):
        scanner.set_preview_aspect(bad)
        assert scanner._preview_aspect is None


def test_wait_frame_returns_only_a_newer_preview_and_wakes_on_stop():
    scanner = BarcodeScanner()
    scanner._capturing = True
    scanner._preview, scanner._preview_seq = b"jpeg-1", 1
    assert scanner.wait_frame(0, timeout=0.01) == (1, b"jpeg-1")
    assert scanner.wait_frame(1, timeout=0.01) is None

    waited = []
    waiter = threading.Thread(target=lambda: waited.append(scanner.wait_frame(1, timeout=5.0)))
    waiter.start()
    scanner.stop_capture()
    waiter.join(timeout=1.0)
    assert not waiter.is_alive() and waited == [None]
    assert scanner.frame() is None


def test_scan_result_is_bounded_and_control_characters_are_removed():
    result = BarcodeScanner._first(("A\x00" + "x" * (MAX_SCAN_CHARS + 20),), "CODE")
    assert "\x00" not in result.value
    assert len(result.value) == MAX_SCAN_CHARS


def test_empty_decoder_values_are_ignored():
    assert BarcodeScanner._first(("", "  "), "QR_CODE") is None


def test_decoder_worker_consumes_latest_frame_without_blocking_preview_loop():
    scanner = BarcodeScanner()

    def decode(frame):
        assert frame == "latest-frame"
        return ScanResult("ROBI", "QR_CODE")

    scanner._decode = decode
    scanner._decode_frame = "latest-frame"
    scanner._decode_event.set()
    worker = threading.Thread(target=scanner._run_decoder)
    worker.start()
    try:
        deadline = time.monotonic() + 1.0
        while scanner.snapshot()["result"] is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert scanner.snapshot()["result"] == {"value": "ROBI", "format": "QR_CODE"}
    finally:
        scanner._stop.set()
        scanner._decode_event.set()
        worker.join(timeout=1.0)
