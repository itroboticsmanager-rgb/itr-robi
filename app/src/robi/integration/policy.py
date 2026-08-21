"""Перевірка контенту, що приходить від CRM.

Це найважливіші сорок рядків у застосунку. Вимога D-038: allowlist
доменів перевіряється **на пристрої**, а не лише в CRM. Причина
конкретна — скомпрометована CRM інакше перетворює ROBI на довірений
фішинговий пристрій на рецепції школи, якому люди вірять за замовчуванням.

Тому перевірка живе тут, окремо від рендеру, і не має жодного способу
бути пропущеною «на секунду».
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

#: Довші за це посилання не влізуть у QR розумної щільності й майже
#: напевно означають помилку або спробу щось протягнути.
MAX_URL_LENGTH = 512


@dataclass(frozen=True, slots=True)
class Verdict:
    ok: bool
    reason: str = ""


class UrlPolicy:
    """Allowlist схем і доменів.

    Порожній `domains` означає «дозволено будь-який домен із дозволеною
    схемою» і придатний лише для розробки. У production порожній
    allowlist — це помилка конфігурації, а не зручність.
    """

    def __init__(self, schemes: tuple[str, ...] = ("https",), domains: tuple[str, ...] = ()) -> None:
        self._schemes = tuple(s.lower() for s in schemes)
        self._domains = tuple(d.lower().lstrip(".") for d in domains)

    @property
    def permissive(self) -> bool:
        return not self._domains

    def check(self, url: str) -> Verdict:
        if not url:
            return Verdict(False, "empty")
        if len(url) > MAX_URL_LENGTH:
            return Verdict(False, "too_long")

        try:
            parts = urlsplit(url)
        except ValueError:
            return Verdict(False, "malformed")

        if parts.scheme.lower() not in self._schemes:
            return Verdict(False, "scheme_not_allowed")

        host = (parts.hostname or "").lower()
        if not host:
            return Verdict(False, "no_host")

        # Облікові дані в URL — ознака або помилки, або спроби ввести в оману.
        if parts.username or parts.password:
            return Verdict(False, "credentials_in_url")

        if self.permissive:
            return Verdict(True, "permissive")

        for allowed in self._domains:
            # Точний збіг або справжній піддомен: "evil-bank.com" не має
            # проходити перевірку на "bank.com".
            if host == allowed or host.endswith("." + allowed):
                return Verdict(True)

        return Verdict(False, "domain_not_allowed")
