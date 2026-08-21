"""Метрики кадру й ресурсів.

Це той інструмент, яким закриваються D-015, D-021 і D-022. Тому мірою є
не середній FPS — він приховує ривки, — а перцентилі часу кадру.
Обличчя, що видає 60 FPS із регулярними провалами до 25 мс, виглядає
гірше за стабільні 40.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field

import psutil


@dataclass(slots=True)
class FrameStats:
    frames: int = 0
    seconds: float = 0.0
    fps_avg: float = 0.0
    ms_median: float = 0.0
    ms_p95: float = 0.0
    ms_worst: float = 0.0
    cpu_percent: float = 0.0
    rss_mb: float = 0.0

    def as_row(self) -> str:
        return (
            f"{self.fps_avg:6.1f} FPS | median {self.ms_median:5.2f} ms | "
            f"p95 {self.ms_p95:5.2f} ms | worst {self.ms_worst:6.2f} ms | "
            f"CPU {self.cpu_percent:5.1f}% | RSS {self.rss_mb:6.1f} MB"
        )


class Metrics:
    """Кільцевий збір часу кадрів без алокацій у гарячому шляху."""

    def __init__(self, window: int = 600) -> None:
        self._window = window
        self._samples: list[float] = []
        self._total_frames = 0
        self._total_time = 0.0
        self._proc = psutil.Process()
        self._proc.cpu_percent(None)  # перший виклик лише задає точку відліку

    def frame(self, dt: float) -> None:
        self._total_frames += 1
        self._total_time += dt
        self._samples.append(dt * 1000.0)
        if len(self._samples) > self._window:
            del self._samples[: len(self._samples) - self._window]

    @property
    def recent_fps(self) -> float:
        if not self._samples:
            return 0.0
        avg_ms = sum(self._samples) / len(self._samples)
        return 1000.0 / avg_ms if avg_ms > 0 else 0.0

    def snapshot(self) -> FrameStats:
        if not self._samples:
            return FrameStats()
        ordered = sorted(self._samples)
        idx95 = min(len(ordered) - 1, int(len(ordered) * 0.95))
        return FrameStats(
            frames=self._total_frames,
            seconds=self._total_time,
            fps_avg=self._total_frames / self._total_time if self._total_time > 0 else 0.0,
            ms_median=statistics.median(ordered),
            ms_p95=ordered[idx95],
            ms_worst=ordered[-1],
            cpu_percent=self._proc.cpu_percent(None),
            rss_mb=self._proc.memory_info().rss / (1024 * 1024),
        )

    def reset(self) -> None:
        self._samples.clear()
        self._total_frames = 0
        self._total_time = 0.0
