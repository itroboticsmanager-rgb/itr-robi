# Інтеграція з CRM

## Мета

CRM має віддалено змінювати сценарій ROBI, а пристрій — підтверджувати виконання, передавати стан і повідомляти про взаємодії. Конкретний backend, URL, схема автентифікації та остаточний контракт ще не відомі.

## Поділ каналів

Поточний архітектурний напрям:

- **WebSocket** — команди з малою затримкою, зміна режиму, cancel, синхронізація статусу й події;
- **HTTP API** — конфігурація, metadata/assets, provisioning-related операції, діагностика або fallback;
- **локальний кеш** — останній дозволений fallback-контент і конфігурація, які не є секретами.

Це не фіксує endpoint paths або конкретний WebSocket-протокол. Якщо CRM уже має інший стандарт, adapter layer має підлаштуватися без зміни mode coordinator.

## Життєвий цикл з'єднання

1. ROBI завантажує локальну identity/config і проходить self-check.
2. Встановлює захищене з'єднання та автентифікує device identity.
3. Надсилає версію app/config, capabilities і health summary.
4. Отримує бажаний CRM-стан або підтвердження локального fallback.
5. Обробляє команди з `command_id`, строком актуальності та idempotency.
6. Повертає `accepted/rejected/completed/failed` відповідно до контракту.
7. Після розриву переходить у offline policy та reconnect із backoff/jitter.
8. Після reconnect виконує state reconciliation; прострочені команди не програються.

## Чернетка типів команд

| Команда | Призначення | Ключові перевірки |
|---|---|---|
| `set_mode` | перейти в mascot/qr/info/nfc/voice | supported mode, priority, expiry |
| `show_qr` | показати дозволений QR payload і CTA | URL/payload policy, duration, QR validity |
| `show_info` | показати шаблонований контент | schema, size, locale, asset availability |
| `play_expression` | коротка анімація обличчя, звук або RGB-акцент | capability, safe limits, cooldown |
| `set_nfc_content` | оновити динамічний phone handoff, якщо підтримується | NFC capability, allowed payload |
| `set_settings` | brightness, volume, quiet hours, feature flags | allowed fields, ranges, persistence policy |
| `cancel` | скасувати активний сценарій | target command, safe unwind |
| `request_status` | повернути health/capabilities | rate limit |
| `restart_app` | контрольований restart app | authorization, active interaction, audit |

Назви вище — **чернетка**, а не сумісний API.

## Чернетка envelope

Приклад лише для обговорення контракту:

```json
{
  "schema_version": "draft-1",
  "type": "command.show_qr",
  "command_id": "example-command-id",
  "device_id": "example-device-id",
  "issued_at": "2026-08-21T12:00:00Z",
  "expires_at": "2026-08-21T12:00:30Z",
  "payload": {
    "content_kind": "url",
    "value": "https://example.invalid/replace-me",
    "title": "Відскануйте QR",
    "duration_ms": 15000
  }
}
```

До затвердження треба вирішити:

- формат і генерацію ID;
- часову синхронізацію та допустимий clock skew;
- чи `duration_ms` рахується від accepted або displayed;
- правила URL allowlist і maximum payload;
- version negotiation;
- error taxonomy і retryability;
- локалізацію тексту.

## Події від ROBI

| Подія | Приклад змісту | Privacy note |
|---|---|---|
| `device.ready` | версія, capabilities, degraded modules | без секретів |
| `device.health` | uptime, температура, storage, network, peripherals | sampling/rate limit TODO |
| `command.status` | accepted/completed/rejected/failed + reason code | не дублювати payload із чутливими даними |
| `interaction.started/ended` | mode, source, duration, outcome | мінімізувати ідентифікацію людини |
| `nfc.detected` | тип сценарію, success/failure | UID картки — лише за окремою потребою й політикою |
| `presence.detected` | є людина / скільки / груба відстань | лише агрегат, без ідентифікації (`D-027`) |
| `touch.action` | semantic action ID | не сирі координати без діагностичної потреби |
| `voice.status` | listening/processing/completed/error | transcript/audio policy TODO |
| `fault.raised/cleared` | стабільний code, severity, component | без токенів і сирих dumps у звичайній телеметрії |

## State reconciliation

CRM і ROBI мають розрізняти:

- **desired state** — чого хоче CRM;
- **reported state** — що реально показує/виконує ROBI;
- **capabilities** — що підтримує ця апаратна ревізія;
- **active command** — тимчасовий сценарій із власним lifecycle.

Після reconnect пристрій не повинен сліпо відтворювати всі накопичені команди. Він повідомляє reported state, отримує актуальний desired state і застосовує лише чинну версію.

## Offline policy

Мінімально без мережі доступні:

- mascot face loop;
- реакція на touch/ToF;
- локальний info fallback;
- чіткий, але ненав'язливий offline/service indicator для персоналу;
- безпечна робота power button.

**TODO:** вирішити, чи можна показувати кешований QR/NFC payload офлайн і який у нього TTL. За замовчуванням динамічні/персоналізовані посилання після expiry не показуються.

## Безпека

- лише шифровані transport-з'єднання в production;
- унікальна identity на пристрій, без спільного hard-coded token у репозиторії;
- можливість відкликання та ротації credentials;
- least-privilege команди для конкретного пристрою/site;
- allowlist дозволених типів контенту, розмірів і URL-схем;
- сувора валідація всіх полів до показу або виконання;
- rate limits і захист від нескінченного audio/RGB сценарію;
- аудит адміністративних команд без секретів;
- фізичний service mode не відкриває CRM credentials у UI.

## Privacy

До пілоту треба письмово визначити:

- підтвердити, що обробка камери й голосу лишається локальною;
- зафіксувати, що камера працює постійно у фоновому режимі `mascot`, і як про це повідомляється відвідувачам;
- зафіксувати межу `D-027` у письмовій політиці, а не лише в коді;
- чи зберігаються кадри, аудіо або transcripts;
- правову підставу й строки зберігання;
- видимий апаратний індикатор активної камери/мікрофона (`D-029`);
- чи NFC-картка ідентифікує учня;
- хто в CRM бачить interaction events;
- як видаляються дані та діагностичні журнали.

Без такого рішення app не повинен зберігати сире аудіо/відео або відкриті card identifiers за замовчуванням.

## Acceptance tests інтеграції

- [ ] правильна команда виконується один раз і має повний status lifecycle;
- [ ] дубль `command_id` не дублює фізичну дію;
- [ ] прострочена, невідома або невалідна команда відхиляється;
- [ ] розрив мережі не заморожує UI та не залишає підсвітку чи звук активними;
- [ ] reconnect відновлює актуальний стан без replay старих команд;
- [ ] device із відсутнім NFC або камерою оголошує capability і відхиляє відповідний сценарій;
- [ ] oversized/unsafe content не доходить до renderer;
- [ ] credential rotation і revocation перевірені;
- [ ] журнали не містять credentials або зайвих персональних даних.

