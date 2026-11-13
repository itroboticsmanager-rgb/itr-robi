"""Яскравість екрана й системна гучність планшета (D-068).

Гучність — саме системна, а не застосунку: відео в галереї грає браузер
кіоску, а не процес ROBI, тож гучність лише «свого» процесу нічого б не
змінила. Ставиться через Core Audio (`IAudioEndpointVolume`) прямо з
`ctypes`, без сторонніх пакетів: на пристрої зайва залежність — зайва
причина не стартувати.

Яскравість — через WMI (`WmiMonitorBrightnessMethods`), як і в налаштуваннях
Windows. Виклик через PowerShell важить пів секунди, тому робиться лише при
зміні цілі й ніколи в головному циклі.

Будь-яка невдача — `False`, а не виняток: кіоск, що не зміг змінити
яскравість, лишається кіоском. Причину бачить CRM у звіті пристрою.
"""

from __future__ import annotations

import ctypes
import subprocess
import sys
from typing import Protocol


class SystemControls(Protocol):
    name: str

    def set_brightness(self, percent: int) -> bool: ...

    def set_volume(self, percent: int) -> bool: ...


class FakeSystemControls:
    """Пам'ятає, що просили. Для тестів і не-Windows машин."""

    name = "fake"

    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.brightness: list[int] = []
        self.volume: list[int] = []

    def set_brightness(self, percent: int) -> bool:
        self.brightness.append(percent)
        return self.ok

    def set_volume(self, percent: int) -> bool:
        self.volume.append(percent)
        return self.ok


class WindowsSystemControls:
    name = "windows"

    def set_brightness(self, percent: int) -> bool:
        level = max(0, min(100, int(percent)))
        # Метод екземпляра, а не класу: виклик на класі WMI відхиляє як
        # «Invalid method Parameter(s)». Типи аргументів — рівно ті, що в схемі.
        script = (
            "$m = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods -ErrorAction Stop; "
            f"Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness "
            f"-Arguments @{{Timeout=[uint32]0; Brightness=[byte]{level}}} -ErrorAction Stop | Out-Null"
        )
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0

    def set_volume(self, percent: int) -> bool:
        try:
            return _set_master_volume(max(0, min(100, int(percent))) / 100.0)
        except OSError:
            return False


def make_system_controls() -> SystemControls:
    return WindowsSystemControls() if sys.platform == "win32" else FakeSystemControls()


# -- Core Audio через ctypes ------------------------------------------------
#
# Мінімум COM без comtypes: три інтерфейси, по одному-два методи кожного.
# Номери методів — позиції у vtable з mmdeviceapi.h / endpointvolume.h.

class _GUID(ctypes.Structure):
    _fields_ = [("a", ctypes.c_uint32), ("b", ctypes.c_uint16), ("c", ctypes.c_uint16), ("d", ctypes.c_ubyte * 8)]

    @classmethod
    def parse(cls, text: str) -> "_GUID":
        h = text.replace("-", "")
        return cls(int(h[0:8], 16), int(h[8:12], 16), int(h[12:16], 16),
                   (ctypes.c_ubyte * 8)(*bytes.fromhex(h[16:32])))


_CLSID_ENUMERATOR = "BCDE0395-E52F-467C-8E3D-C4579291692E"
_IID_ENUMERATOR = "A95664D2-9614-4F35-A746-DE8DB63617E6"
_IID_ENDPOINT_VOLUME = "5CDF2C82-841E-4546-9722-0CF74078229A"
_CLSCTX_ALL = 0x17
_E_RENDER, _E_MULTIMEDIA = 0, 1


def _method(obj: ctypes.c_void_p, index: int, *argtypes):
    vtable = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    prototype = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, *argtypes)
    return prototype(vtable[index])


def _release(obj: ctypes.c_void_p) -> None:
    if obj:
        _method(obj, 2)(obj)


def _set_master_volume(level: float) -> bool:
    ole32 = ctypes.windll.ole32
    initialized = ole32.CoInitializeEx(None, 0x2) in (0, 1)  # STA; S_FALSE — уже ініціалізовано
    enumerator = ctypes.c_void_p()
    device = ctypes.c_void_p()
    volume = ctypes.c_void_p()
    try:
        clsid, iid = _GUID.parse(_CLSID_ENUMERATOR), _GUID.parse(_IID_ENUMERATOR)
        if ole32.CoCreateInstance(ctypes.byref(clsid), None, _CLSCTX_ALL, ctypes.byref(iid), ctypes.byref(enumerator)):
            return False
        get_default = _method(enumerator, 4, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))
        if get_default(enumerator, _E_RENDER, _E_MULTIMEDIA, ctypes.byref(device)):
            return False
        iid_volume = _GUID.parse(_IID_ENDPOINT_VOLUME)
        activate = _method(device, 3, ctypes.POINTER(_GUID), ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))
        if activate(device, ctypes.byref(iid_volume), _CLSCTX_ALL, None, ctypes.byref(volume)):
            return False
        set_scalar = _method(volume, 7, ctypes.c_float, ctypes.c_void_p)
        set_mute = _method(volume, 14, ctypes.c_int, ctypes.c_void_p)
        ok = set_scalar(volume, ctypes.c_float(level), None) == 0
        # Нуль у CRM означає «тиша»: вимикаємо звук, а не лише крутимо вниз.
        set_mute(volume, 1 if level == 0 else 0, None)
        return ok
    finally:
        _release(volume)
        _release(device)
        _release(enumerator)
        if initialized:
            ole32.CoUninitialize()


def read_master_volume() -> float | None:
    """Поточна гучність 0–1. Для перевірки на пристрої й у тестах на Windows."""
    if sys.platform != "win32":
        return None
    ole32 = ctypes.windll.ole32
    initialized = ole32.CoInitializeEx(None, 0x2) in (0, 1)
    enumerator, device, volume = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_void_p()
    try:
        clsid, iid = _GUID.parse(_CLSID_ENUMERATOR), _GUID.parse(_IID_ENUMERATOR)
        if ole32.CoCreateInstance(ctypes.byref(clsid), None, _CLSCTX_ALL, ctypes.byref(iid), ctypes.byref(enumerator)):
            return None
        if _method(enumerator, 4, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_void_p))(
            enumerator, _E_RENDER, _E_MULTIMEDIA, ctypes.byref(device)
        ):
            return None
        iid_volume = _GUID.parse(_IID_ENDPOINT_VOLUME)
        if _method(device, 3, ctypes.POINTER(_GUID), ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p))(
            device, ctypes.byref(iid_volume), _CLSCTX_ALL, None, ctypes.byref(volume)
        ):
            return None
        level = ctypes.c_float()
        if _method(volume, 9, ctypes.POINTER(ctypes.c_float))(volume, ctypes.byref(level)):
            return None
        return float(level.value)
    finally:
        _release(volume)
        _release(device)
        _release(enumerator)
        if initialized:
            ole32.CoUninitialize()
