"""Бенчмарк рендеру обличчя.

Це інструмент, яким закриваються D-015, D-021 і D-022. Запускається на
робочому ПК як база й на кандидатах платформи як порівняння — на
будь-якому наявному HDMI-моніторі, цільовий дисплей для цього не потрібен.

    python app/tools/benchmark.py
    python app/tools/benchmark.py --resolutions 800x480 1280x720 --seconds 10

Дивитися треба не на середній FPS, а на p95 і worst: обличчя з
регулярними провалами виглядає гірше за стабільно повільніше.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402

from robi.health.metrics import Metrics  # noqa: E402
from robi.modes.mascot import MascotMode  # noqa: E402
from robi.ui.qr_screen import QrScreen  # noqa: E402


def parse_size(text: str) -> tuple[int, int]:
    w, _, h = text.partition("x")
    return int(w), int(h)


def bench_face(size: tuple[int, int], seconds: float, with_vision: bool) -> Metrics:
    """Міряє повний кадр обличчя так, як він виглядає в застосунку."""
    screen = pygame.display.set_mode(size)
    mode = MascotMode(size)
    metrics = Metrics()

    from robi.vision.fake import FakeVision

    vision = FakeVision()
    if with_vision:
        vision.initialize()
        vision.start_capture()

    started = time.perf_counter()
    last = started
    while time.perf_counter() - started < seconds:
        now = time.perf_counter()
        dt = now - last
        last = now

        if with_vision:
            for event in vision.poll(dt):
                mode.handle(event)

        mode.update(dt)
        mode.draw(screen)
        pygame.display.flip()
        metrics.frame(dt)

    return metrics


def bench_qr(size: tuple[int, int], seconds: float) -> Metrics:
    """QR кешується між кадрами, тож тут міряється саме вартість показу."""
    screen = pygame.display.set_mode(size)
    qr = QrScreen(size)
    metrics = Metrics()

    started = time.perf_counter()
    last = started
    while time.perf_counter() - started < seconds:
        now = time.perf_counter()
        dt = now - last
        last = now
        qr.draw(screen, "https://example.org/robi", "Наведіть камеру телефона")
        pygame.display.flip()
        metrics.frame(dt)

    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolutions", nargs="+", default=["800x480", "1280x720"])
    parser.add_argument("--seconds", type=float, default=6.0)
    args = parser.parse_args()

    pygame.init()
    print(f"pygame-ce {pygame.version.ver}, SDL {'.'.join(map(str, pygame.get_sdl_version()))}")
    print(f"кожен тест — {args.seconds:.0f} с без обмеження кадрів\n")

    header = f"{'сценарій':<28}{'результат'}"
    print(header)
    print("-" * 108)

    for text in args.resolutions:
        size = parse_size(text)
        for label, metrics in (
            (f"{text} обличчя", bench_face(size, args.seconds, with_vision=False)),
            (f"{text} обличчя + vision", bench_face(size, args.seconds, with_vision=True)),
            (f"{text} qr", bench_qr(size, args.seconds)),
        ):
            print(f"{label:<28}{metrics.snapshot().as_row()}")
        print()

    pygame.quit()
    print("Орієнтир для Pi: median нижче 16.7 мс — це стабільні 60 FPS,")
    print("нижче 33.3 мс — стабільні 30. Дивіться на p95, а не на середнє.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
