"""Банери вітрини: модель, завантаження з CRM і локальний кеш (`D-058`).

Кеш тут не оптимізація, а вимога. Мережа на рецепції ненадійна, а
порожня вітрина об 8:30, коли в холі найбільше людей, — це найгірший
момент для «зараз нема зв'язку». Тому останній вдалий набір лягає на
диск і показується, поки не приїде новий.

Що саме кешується. Опис банерів у JSON і самі картинки поруч. Ані те, ні
те не є персональними даними: CRM віддає на пристрій лише заголовок,
підпис і зображення, без полів таргетингу — вони описують глядача, а
ROBI не знає, хто перед ним (`D-027`).

Чому картинки лежать файлами, а не в пам'яті: пристрій перезапускається
(оновлення Windows, зникнення світла), і вітрина має піднятися одразу, а
не чекати на мережу.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

#: Скільки банерів пристрій погоджується тримати. Вітрина — не каталог:
#: людина біля стійки встигає побачити кілька, а решта лише роздуває кеш.
MAX_BANNERS = 12

#: Стеля розміру картинки. Без неї одна недбало завантажена світлина
#: здатна забити диск пристрою, на якому вона нікому не потрібна.
MAX_IMAGE_BYTES = 4 * 1024 * 1024

MAX_TITLE = 80
MAX_DESCRIPTION = 200


@dataclass(frozen=True, slots=True)
class Banner:
    id: int
    title: str
    description: str = ""
    #: Ім'я файлу в кеші, а не адреса. Пристрій показує те, що вже лежить
    #: на диску, і не ходить у мережу під час малювання кадру.
    image: str = ""
    bg_color: str = ""
    text_color: str = ""


def _clean(value: object, limit: int) -> str:
    text = str(value or "").strip()
    return text[:limit]


def parse_banners(payload: object) -> list[Banner]:
    """Розбирає відповідь CRM. Битий запис пропускається, а не валить набір.

    Один зіпсований банер не має гасити вітрину цілком: на стійці краще
    показати три з чотирьох, ніж порожній екран.
    """
    if not isinstance(payload, dict):
        return []
    raw = payload.get("banners")
    if not isinstance(raw, list):
        return []

    out: list[Banner] = []
    for entry in raw[:MAX_BANNERS]:
        if not isinstance(entry, dict):
            continue
        try:
            banner_id = int(entry.get("id"))
        except (TypeError, ValueError):
            continue
        title = _clean(entry.get("title"), MAX_TITLE)
        if banner_id <= 0 or not title:
            continue
        out.append(
            Banner(
                id=banner_id,
                title=title,
                description=_clean(entry.get("description"), MAX_DESCRIPTION),
                image=str(entry.get("image_url") or "").strip(),
                bg_color=_clean(entry.get("bg_color"), 16),
                text_color=_clean(entry.get("text_color"), 16),
            )
        )
    return out


class BannerStore:
    """Локальний кеш вітрини: опис поруч із картинками."""

    def __init__(self, directory: str | Path) -> None:
        self.dir = Path(directory)
        self.index = self.dir / "banners.json"

    # -- читання -----------------------------------------------------------

    def load(self) -> list[Banner]:
        """Останній вдалий набір. Порожній список, якщо кешу ще немає."""
        try:
            payload = json.loads(self.index.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        banners = parse_banners(payload)
        # Банер без картинки на диску показувати нема чим: між записом
        # опису й завантаженням файлу могло обірватися живлення.
        return [b for b in banners if not b.image or self.image_path(b).is_file()]

    def image_path(self, banner: Banner) -> Path:
        return self.dir / f"{banner.id}{_suffix(banner.image)}"

    # -- оновлення ---------------------------------------------------------

    def refresh(self, url: str, secret: str, timeout: float = 10.0) -> tuple[bool, str]:
        """Тягне свіжий набір. `(успіх, причина)`; невдача лишає старий кеш.

        Порядок важливий: спершу завантажуються картинки, і лише потім
        переписується опис. Інакше обрив посеред оновлення лишив би
        вітрину з описом нових банерів і файлами старих.
        """
        if not url or not secret:
            return False, "not_configured"

        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {secret}"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return False, f"http_{exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return False, f"net_{type(exc).__name__}"
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False, "bad_response"
        except UnicodeEncodeError:
            # Заголовки HTTP кодуються в latin-1, тож секрет із кирилицею
            # валить запит ще до мережі. Причину треба назвати, а не впасти:
            # адміністратор має зрозуміти, що виправляти.
            return False, "bad_secret"

        banners = parse_banners(payload)
        self.dir.mkdir(parents=True, exist_ok=True)

        kept: list[Banner] = []
        for banner in banners:
            if not banner.image:
                kept.append(banner)
                continue
            if self._fetch_image(banner, timeout):
                kept.append(banner)

        try:
            self.index.write_text(
                json.dumps({"banners": [_as_dict(b) for b in kept]}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            return False, f"write_{type(exc).__name__}"

        self._sweep({self.image_path(b).name for b in kept})
        return True, ""

    def _fetch_image(self, banner: Banner, timeout: float) -> bool:
        target = self.image_path(banner)
        if target.is_file():
            return True
        try:
            with urllib.request.urlopen(banner.image, timeout=timeout) as response:
                data = response.read(MAX_IMAGE_BYTES + 1)
        except Exception:  # noqa: BLE001 — картинка не варта падіння вітрини
            return False
        if not data or len(data) > MAX_IMAGE_BYTES:
            return False
        try:
            target.write_bytes(data)
        except OSError:
            return False
        return True

    def _sweep(self, keep: set[str]) -> None:
        """Прибирає картинки банерів, яких більше немає.

        Без цього кеш ріс би вічно на пристрої зі 128 ГБ, де місце ще
        знадобиться відео з `D-048`.
        """
        try:
            entries = list(self.dir.iterdir())
        except OSError:
            return
        for path in entries:
            if path.name == self.index.name or path.name in keep:
                continue
            try:
                path.unlink()
            except OSError:
                pass


def _suffix(url: str) -> str:
    tail = url.rsplit("/", 1)[-1].split("?", 1)[0]
    dot = tail.rfind(".")
    if dot == -1:
        return ".img"
    suffix = tail[dot:].lower()
    return suffix if len(suffix) <= 5 and suffix.isprintable() else ".img"


def _as_dict(banner: Banner) -> dict:
    return {
        "id": banner.id,
        "title": banner.title,
        "description": banner.description,
        "image_url": banner.image,
        "bg_color": banner.bg_color,
        "text_color": banner.text_color,
    }
