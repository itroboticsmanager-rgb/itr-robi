"""Журнал служби завжди в UTF-8.

Наглядач кіоску перенаправляє stdout/stderr служби у файли. Перенаправлений
потік Python на Windows кодує системною кодовою сторінкою (cp1252 на
планшеті), і перший же `print` українською кидав `UnicodeEncodeError` —
так 19.11.2026 тихо помер потік налаштувань стійки (D-068) і нові версії
з CRM більше не застосовувались. Тому точки входу перемикають обидва
потоки на UTF-8, а символ, який усе ж не закодувався, замінюється, а не
валить код, що просто хотів записати рядок у журнал.
"""

from __future__ import annotations

import sys


def use_utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass
