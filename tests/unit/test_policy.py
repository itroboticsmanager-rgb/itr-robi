"""Перевірка allowlist — найважливіші тести в наборі.

Сценарій, від якого вони захищають: CRM скомпрометовано, і вона просить
ROBI показати QR на чужий домен. Пристрій на рецепції школи має довіру
за замовчуванням, тому відмова мусить статися тут, а не покладатися на
те, що CRM «нормальна».
"""

from robi.integration.policy import MAX_URL_LENGTH, UrlPolicy


def strict() -> UrlPolicy:
    return UrlPolicy(schemes=("https",), domains=("example.org", "pay.example.com"))


def test_allows_exact_domain():
    assert strict().check("https://example.org/robi").ok


def test_allows_real_subdomain():
    assert strict().check("https://qr.example.org/x").ok


def test_rejects_lookalike_suffix():
    # Класична пастка: endswith("example.org") пропустив би цей домен.
    verdict = strict().check("https://evil-example.org/pay")
    assert not verdict.ok
    assert verdict.reason == "domain_not_allowed"


def test_rejects_domain_used_as_prefix():
    # "example.org.attacker.net" не має жодного стосунку до example.org.
    assert not strict().check("https://example.org.attacker.net/pay").ok


def test_rejects_plain_http():
    verdict = strict().check("http://example.org/robi")
    assert not verdict.ok
    assert verdict.reason == "scheme_not_allowed"


def test_rejects_credentials_in_url():
    # Вигляд "https://example.org@evil.net" вводить людину в оману.
    verdict = strict().check("https://user:pass@example.org/x")
    assert not verdict.ok
    assert verdict.reason == "credentials_in_url"


def test_rejects_non_http_schemes():
    for url in ("javascript:alert(1)", "file:///etc/passwd", "data:text/html,x"):
        assert not strict().check(url).ok


def test_rejects_overlong_url():
    verdict = strict().check("https://example.org/" + "a" * MAX_URL_LENGTH)
    assert not verdict.ok
    assert verdict.reason == "too_long"


def test_rejects_empty():
    assert not strict().check("").ok


def test_permissive_mode_is_marked_as_such():
    # Порожній allowlist дозволений для розробки, але має бути видимим:
    # це не «налаштування за замовчуванням», це відсутність захисту.
    policy = UrlPolicy(schemes=("https",), domains=())
    assert policy.permissive
    assert policy.check("https://anything.example/x").reason == "permissive"


def test_permissive_still_enforces_scheme():
    policy = UrlPolicy(schemes=("https",), domains=())
    assert not policy.check("http://anything.example/x").ok
