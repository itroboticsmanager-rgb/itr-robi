"""Контракт адрес між CRM і allowlist пристрою.

Тест з'явився після реальної поломки: 2026-09-08 CRM почала слати
платіжний QR з домену банку `qr.bank.gov.ua`, а allowlist пристрою знав
лише домен CRM. Тести обох репозиторіїв лишались зеленими, а кнопка
«Показати на ROBI» мовчки нічого не показувала.

Тут зафіксовано, які саме адреси CRM шле на кіоск (`src/lib/device-qr.ts`
у CRM), і перевіряється, що приклад конфігурації їх пропускає. Нова адреса
в CRM без змін тут — сигнал оновити `device.toml` на планшеті.
"""

from pathlib import Path

import pytest

from robi.config import Config
from robi.integration.policy import MAX_URL_LENGTH, UrlPolicy

EXAMPLE = Path(__file__).resolve().parents[2] / "app" / "config" / "device.example.toml"

#: Одна адреса на кожен тип коду, який CRM уміє вивести на кіоск.
CRM_QR_URLS = {
    "payment": (
        "https://qr.bank.gov.ua/QkNECjAwMgoxClVDVAoK0KTQntCfINCi0LXRgdGC0L7QstC40LkK"
        "VUEyMTMyMjMxMzAwMDAwMjYwMDcyMzM1NjYwMDEKVUFIMTUwMC4wMAoxMjM0NTY3ODkwCgoK"
    ),
    "enrollment": "https://crm.itrobotics.com.ua/enroll/0b8f3c1e-6c2a-4f0e-9d59-3f1c2a7b9e10",
    "teacher-invite": "https://crm.itrobotics.com.ua/register-teacher/0b8f3c1e-6c2a-4f0e-9d59-3f1c2a7b9e10",
    "admin-invite": "https://crm.itrobotics.com.ua/register-admin/" + "a1" * 32,
    "pin-card": "https://students.itrobotics.com.ua/card/eyJhbGciOiJIUzI1NiJ9.eyJzdHVkZW50SWQiOjF9.c2ln",
    "guest-room": "https://students.itrobotics.com.ua/g/eyJhbGciOiJIUzI1NiJ9.eyJyb29tSWQiOjF9.c2ln",
    "parent-link": "https://t.me/ITRobotics_School_bot?start=link_1-z-1-k3x-0123456789abcdef",
}


def example_policy() -> UrlPolicy:
    crm = Config.load(EXAMPLE).crm
    return UrlPolicy(crm.allowed_url_schemes, crm.allowed_domains)


@pytest.mark.parametrize("kind", sorted(CRM_QR_URLS))
def test_example_allowlist_accepts_every_crm_qr(kind):
    url = CRM_QR_URLS[kind]
    assert len(url) <= MAX_URL_LENGTH
    verdict = example_policy().check(url)
    assert verdict.ok, f"{kind}: {verdict.reason}"


def test_example_allowlist_stays_strict():
    policy = example_policy()
    assert not policy.permissive
    for url in (
        "https://itrobotics.com.ua.attacker.net/enroll/x",
        "https://evil.example.net/enroll/x",
        "https://t.me.attacker.net/x",
        "https://bank.gov.ua.attacker.net/x",
        "http://crm.itrobotics.com.ua/enroll/x",
    ):
        assert not policy.check(url).ok, url
