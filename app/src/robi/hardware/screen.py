"""Знімок екрана стійки для CRM (обслуговування без поїздки до стійки).

Знімає весь екран сесії `Robi` — тобто те, що бачать батьки: Edge у
kiosk-режимі разом із будь-яким вікном, що вистрибнуло поверх. Тому знімок
робить служба, а не сторінка: сторінка бачила б лише себе.

GDI через `ctypes` (без нових залежностей), JPEG — через pygame-ce, який
уже є в застосунку. Повертає `None`, якщо зняти не вдалося: команда тоді
просто не дасть знімка, а не покладе службу.
"""

from __future__ import annotations

import ctypes
import io
import sys
from dataclasses import dataclass

#: Ширина знімка в CRM: досить, щоб прочитати текст, і легко для мережі.
TARGET_WIDTH = 1280


@dataclass(frozen=True, slots=True)
class Screenshot:
    jpeg: bytes
    width: int
    height: int


def capture_jpeg(target_width: int = TARGET_WIDTH) -> Screenshot | None:
    if sys.platform != "win32":
        return None
    try:
        raw, width, height = _grab_bgra()
    except Exception:  # noqa: BLE001 — OSError, ctypes.ArgumentError тощо
        return None
    try:
        import pygame

        surface = pygame.image.frombuffer(raw, (width, height), "BGRA")
        if width > target_width:
            scaled = (target_width, max(1, round(height * target_width / width)))
            surface = pygame.transform.smoothscale(surface, scaled)
        out = io.BytesIO()
        pygame.image.save(surface, out, "screen.jpg")
        size = surface.get_size()
        return Screenshot(out.getvalue(), size[0], size[1])
    except Exception:  # noqa: BLE001 — будь-який збій кодування = немає знімка
        return None


def _grab_bgra() -> tuple[bytes, int, int]:
    """Пікселі всього віртуального екрана як BGRA, рядки зверху вниз."""
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32
    try:
        # Без цього Windows віддає процесу масштабовані розміри (125 % → менше
        # пікселів), і знімок обрізає праву й нижню частину екрана.
        user32.SetProcessDPIAware()
    except (AttributeError, OSError):
        pass

    x = user32.GetSystemMetrics(76)  # SM_XVIRTUALSCREEN
    y = user32.GetSystemMetrics(77)  # SM_YVIRTUALSCREEN
    width = user32.GetSystemMetrics(78)  # SM_CXVIRTUALSCREEN
    height = user32.GetSystemMetrics(79)  # SM_CYVIRTUALSCREEN
    if width <= 0 or height <= 0:
        raise OSError("no screen")

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
            ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
            ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
        ]

    # 64-бітні дескриптори: без явних типів ctypes обрізає їх до int.
    user32.GetDC.restype = wintypes.HDC
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    gdi32.CreateCompatibleDC.restype = wintypes.HDC
    gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    gdi32.SelectObject.restype = wintypes.HGDIOBJ
    gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    gdi32.BitBlt.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                             wintypes.HDC, ctypes.c_int, ctypes.c_int, wintypes.DWORD]
    gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                                ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteDC.argtypes = [wintypes.HDC]

    screen_dc = user32.GetDC(None)
    if not screen_dc:
        raise OSError("GetDC failed")
    mem_dc = gdi32.CreateCompatibleDC(screen_dc)
    bitmap = gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    try:
        if not mem_dc or not bitmap:
            raise OSError("no bitmap")
        gdi32.SelectObject(mem_dc, bitmap)
        # SRCCOPY | CAPTUREBLT — разом із шарованими вікнами.
        if not gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, x, y, 0x00CC0020 | 0x40000000):
            raise OSError("BitBlt failed")
        header = BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        header.biWidth = width
        header.biHeight = -height  # від'ємна висота = рядки зверху вниз
        header.biPlanes = 1
        header.biBitCount = 32
        header.biCompression = 0  # BI_RGB
        buffer = ctypes.create_string_buffer(width * height * 4)
        lines = gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer, ctypes.byref(header), 0)
        if lines != height:
            raise OSError("GetDIBits failed")
        raw = bytearray(buffer.raw)
        raw[3::4] = b"\xff" * (width * height)  # GDI лишає альфу нулем
        return bytes(raw), width, height
    finally:
        if bitmap:
            gdi32.DeleteObject(bitmap)
        if mem_dc:
            gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, screen_dc)
