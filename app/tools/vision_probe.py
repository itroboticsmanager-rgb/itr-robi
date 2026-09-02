"""Профайлер vision: скільки коштує «дивитися» (D-053).

Бенчмарк обличчя міряє рендер і крутить головний цикл на повній
швидкості, тому vision там конкурує за процесор із тим, чого в реальному
застосунку немає — цикл обмежений 60 FPS. Цей інструмент міряє camera
окремо: скільки кадрів адаптер встигає, скільки з них із обличчям і
скільки процесорного часу це коштує.

    python app/tools/vision_probe.py --seconds 20
    python app/tools/vision_probe.py --seconds 20 --fps 8 --detect-width 320

Головне число — `CPU на vision`: частка одного ядра, яку з'їдає постійна
детекція. `mascot` тримає камеру ввімкненою весь час, тож це фон, а не
епізод.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Консоль Windows у сесії SSH приходить у cp1252 і на кирилиці падає з
# UnicodeEncodeError уже після вимірювання, тобто губить саме результат.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

from robi.vision.camera import CameraVision  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=20.0)
    parser.add_argument("--fps", type=float, default=8.0)
    parser.add_argument("--detect-width", type=int, default=320)
    parser.add_argument("--device", type=int, default=0)
    args = parser.parse_args()

    vision = CameraVision(
        device_index=args.device, fps=args.fps, detect_width=args.detect_width
    )
    health = vision.initialize()
    print(f"vision: ok={health.ok}  {health.detail}")
    if not health.ok:
        return 1

    try:
        import psutil

        proc = psutil.Process()
    except ImportError:
        proc = None

    vision.start_capture()
    if not vision.capturing:
        print(f"камера не відкрилася: {vision.health().detail}")
        return 1

    # Перший кадр приходить із затримкою: камера прокидається й ловить
    # експозицію. Ці секунди не мають потрапити у вимір.
    time.sleep(2.0)

    cpu_before = proc.cpu_times() if proc else None
    started = time.perf_counter()
    seen_with_face = 0
    polls = 0

    while time.perf_counter() - started < args.seconds:
        for event in vision.poll(0.0):
            polls += 1
            if event.count:
                seen_with_face += 1
        time.sleep(0.005)

    wall = time.perf_counter() - started
    cpu_after = proc.cpu_times() if proc else None
    stats = vision.stats()
    vision.stop_capture()
    vision.shutdown()

    print()
    print(f"тривалість         : {wall:.1f} с")
    print(f"кадрів оброблено   : {stats.frames}  ({stats.frames / wall:.1f} к/с при цілі {args.fps:.0f})")
    print(f"кадрів з обличчям  : {stats.detections}")
    if cpu_before and cpu_after:
        cpu = (cpu_after.user - cpu_before.user) + (cpu_after.system - cpu_before.system)
        print(f"CPU на vision      : {cpu:.2f} с за {wall:.1f} с = {100.0 * cpu / wall:.1f} % одного ядра")
    print()
    if stats.detections == 0:
        print("Обличчя не знайдено жодного разу.")
        print("Це або справді порожній кадр, або зламана детекція — перевіряйте,")
        print("сидячи перед камерою, інакше вимір нічого не доводить.")
    else:
        share = 100.0 * stats.detections / max(stats.frames, 1)
        print(f"Обличчя було в кадрі {share:.0f} % часу — детекція працює.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
