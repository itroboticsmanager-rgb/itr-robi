"""Контент-меню з CRM: завантаження, сувора перевірка й локальний кеш.

CRM вирішує, які напрями й рівні показує кіоск (вкладка «Сайт → Кіоск ROBI»),
а пристрій тримає останній вдалий набір на диску поруч із картинками. Мотив
той самий, що в банерів (`D-058`): мережа на рецепції ненадійна, і меню з
курсами має підніматися після перезапуску одразу, а не чекати на зв'язок.

Перевірка та сама, що для локального файлу (`D-048`): набір, який не пройшов
би `Content.from_dict`, відкидається цілком, і на пристрої лишається
попередній. Старий, але цілий каталог біля стійки кращий за новий із глухим
кутом.

Три стани кешу:

- набору з CRM ще не було — діє локальний файл із `content.path`;
- CRM віддала порожній набір — адміністратор нічого не ввімкнув, меню з CRM
  немає, і локальний приклад на його місце не підставляється;
- CRM віддала дерево — показується воно.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

from .content import Content, ContentError

#: Відповідь CRM — кілька десятків вузлів тексту. Стеля не дає випадково
#: великій відповіді з'їсти пам'ять пристрою.
MAX_PAYLOAD_BYTES = 2 * 1024 * 1024

#: Стеля картинки, як у банерів: одна недбало завантажена світлина не має
#: забивати диск пристрою.
MAX_IMAGE_BYTES = 4 * 1024 * 1024

#: Стеля відео галереї (D-063). CRM віддає вже стиснений H.264 до 1280 px,
#: хвилина такого — 15–30 МБ; більше означає, що стиснення не спрацювало.
MAX_VIDEO_BYTES = 80 * 1024 * 1024

#: Відео тягнеться шматками прямо на диск, а не цілим у пам'ять.
CHUNK = 256 * 1024

INDEX = "content.json"
PENDING = "content.pending.json"


class ContentStore:
    """Локальний кеш меню з CRM: опис поруч із картинками."""

    def __init__(self, directory: str | Path) -> None:
        self.dir = Path(directory)
        self.index = self.dir / INDEX

    # -- читання -----------------------------------------------------------

    def load(self) -> tuple[bool, Content | None]:
        """`(набір є, контент)`. `(True, None)` — меню в CRM вимкнено.

        Битий кеш рахується відсутнім: тоді діє локальний файл, а не порожній
        екран.
        """
        try:
            raw = json.loads(self.index.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False, None
        if not isinstance(raw, dict) or not isinstance(raw.get("node"), list):
            return False, None
        if not raw["node"]:
            return True, None
        try:
            return True, Content.from_dict(raw)
        except ContentError:
            return False, None

    def image_name(self, node_id: str, url: str) -> str:
        """Ім'я файлу з id вузла й відбитка адреси, а не з чужої адреси.

        Шлях на нашому диску не має вирішувати сервер картинок. Нова адреса —
        нове ім'я, тож оновлена обкладинка не ховається за старим файлом.
        """
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", node_id)[:60] or "node"
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        return f"{safe}-{digest}{_suffix(url)}"

    # -- оновлення ---------------------------------------------------------

    def refresh(self, url: str, secret: str, timeout: float = 10.0) -> tuple[bool, str]:
        """Тягне свіжий набір. `(успіх, причина)`; невдача лишає старий кеш.

        Порядок як у банерів: спершу перевірка, потім картинки, і лише тоді
        переписується опис. Обрив посередині не лишає опису без файлів.
        """
        if not url or not secret:
            return False, "not_configured"

        request = urllib.request.Request(url, headers={"Authorization": f"Bearer {secret}"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read(MAX_PAYLOAD_BYTES + 1)
        except urllib.error.HTTPError as exc:
            return False, f"http_{exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return False, f"net_{type(exc).__name__}"
        except UnicodeEncodeError:
            # Секрет із кирилицею валить заголовок ще до мережі; причину треба
            # назвати, а не впасти.
            return False, "bad_secret"
        if len(body) > MAX_PAYLOAD_BYTES:
            return False, "too_large"
        try:
            payload = json.loads(body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            return False, "bad_response"
        if not isinstance(payload, dict) or not isinstance(payload.get("node"), list):
            return False, "bad_response"

        root = str(payload.get("root", "root"))
        entries = payload["node"]
        if not entries:
            return self._commit({"root": root, "node": []}, keep=set())

        # Перевірка без картинок: битий набір не має коштувати жодного
        # завантаження, а `image` від CRM не приймається зовсім — це шлях на
        # нашому диску, і його вирішує пристрій. Галерею перевіряє той самий
        # код, що й локальний файл: адреси CRM стоять на місці майбутніх файлів.
        nodes = [_without_image(entry) for entry in entries]
        try:
            Content.from_dict({"root": root, "node": [
                {**node, "media": _remote_media(entry)} for entry, node in zip(entries, nodes)
            ]})
        except ContentError as exc:
            return False, f"invalid: {exc}"

        self.dir.mkdir(parents=True, exist_ok=True)
        keep: set[str] = set()
        for entry, node in zip(entries, nodes):
            node_id = str(entry.get("id", "")).strip()
            name = self._fetch(node_id, entry.get("image_url"), MAX_IMAGE_BYTES, timeout)
            if name:
                node["image"] = name
                keep.add(name)
            media = self._fetch_media(node_id, _remote_media(entry), timeout)
            if media:
                node["media"] = media
                keep.update(m[key] for m in media for key in ("file", "poster") if m.get(key))
        return self._commit({"root": root, "node": nodes}, keep)

    def _commit(self, payload: dict, keep: set[str]) -> tuple[bool, str]:
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
            pending = self.dir / PENDING
            pending.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            pending.replace(self.index)
        except OSError as exc:
            return False, f"write_{type(exc).__name__}"
        self._sweep(keep)
        return True, ""

    def _fetch_media(self, node_id: str, remote: list[dict], timeout: float) -> list[dict]:
        """Галерея вузла у вигляді локальних файлів.

        Пункт, що не завантажився, випадає сам, а не валить набір: без одного
        відео галерея лишається галереєю. Постер — прикраса, його відсутність
        відео не скасовує.
        """
        media: list[dict] = []
        for item in remote:
            kind = item["kind"]
            limit = MAX_VIDEO_BYTES if kind == "video" else MAX_IMAGE_BYTES
            file = self._fetch(node_id, item["file"], limit, timeout)
            if not file:
                continue
            entry = {"kind": kind, "file": file}
            if kind == "video" and item.get("poster"):
                poster = self._fetch(node_id, item["poster"], MAX_IMAGE_BYTES, timeout)
                if poster:
                    entry["poster"] = poster
            media.append(entry)
        return media

    def _fetch(self, node_id: str, url: object, limit: int, timeout: float) -> str:
        """Ім'я файлу в кеші або порожньо. Без картинки картка лишається картою.

        Лише https: адресу дає CRM, і відкритий http біля стійки ні до чого.
        Файл пишеться поруч під тимчасовим ім'ям і стає на місце лише цілим:
        обірване посередині відео не має виглядати завантаженим наступного разу.
        """
        if not isinstance(url, str) or not url.startswith("https://") or len(url) > 1000:
            return ""
        name = self.image_name(node_id, url)
        target = self.dir / name
        if target.is_file():
            return name
        partial = self.dir / f"{name}.part"
        try:
            size = 0
            with urllib.request.urlopen(url, timeout=timeout) as response, partial.open("wb") as out:
                while chunk := response.read(CHUNK):
                    size += len(chunk)
                    if size > limit:
                        raise ValueError("too large")
                    out.write(chunk)
            if not size:
                raise ValueError("empty")
            partial.replace(target)
        except Exception:  # noqa: BLE001 — картинка не варта меню
            try:
                partial.unlink(missing_ok=True)
            except OSError:
                pass
            return ""
        return name

    def _sweep(self, keep: set[str]) -> None:
        """Прибирає картинки вузлів, яких більше немає."""
        try:
            entries = list(self.dir.iterdir())
        except OSError:
            return
        for path in entries:
            if path.name in (INDEX, PENDING) or path.name in keep:
                continue
            try:
                path.unlink()
            except OSError:
                pass


def _without_image(entry: object) -> object:
    if not isinstance(entry, dict):
        return entry
    return {k: v for k, v in entry.items() if k not in ("image", "image_url", "media")}


def _remote_media(entry: object) -> object:
    """Галерея з CRM у формі локальної: адреса стоїть на місці файлу.

    Непридатну форму віддаємо як є — її відкине перевірка контенту, а не
    мовчазне «галереї немає».
    """
    raw = entry.get("media", []) if isinstance(entry, dict) else []
    if not isinstance(raw, list):
        return raw
    items: list[object] = []
    for item in raw:
        if not isinstance(item, dict):
            items.append(item)
            continue
        converted = {"kind": item.get("kind", ""), "file": item.get("url", "")}
        if item.get("poster_url"):
            converted["poster"] = item["poster_url"]
        items.append(converted)
    return items


def _suffix(url: str) -> str:
    tail = url.rsplit("/", 1)[-1].split("?", 1)[0]
    dot = tail.rfind(".")
    if dot == -1:
        return ".img"
    suffix = tail[dot:].lower()
    return suffix if re.fullmatch(r"\.[a-z0-9]{1,4}", suffix) else ".img"
