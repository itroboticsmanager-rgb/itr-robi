# Програмна частина

## Цілі

Device app має дати ROBI плавне обличчя й передбачувані сценарії, не пов'язуючи бізнес-логіку CRM із конкретними GPIO або моделями периферії.

Мова, фреймворк UI, база/сховище й система пакування **не обрані**. Вибір слід робити після короткого proof of concept на цільовій платформі з цільовою роздільністю дисплея. Розробку можна починати на ПК проти fake hardware — це не блокується вибором заліза (`D-023`).

## Запропонована структура app

```text
app/src/
├── bootstrap/       # запуск, dependency wiring, shutdown
├── config/          # завантаження й валідація конфігурації
├── modes/           # mascot, qr, info, nfc, voice
├── state/           # coordinator, transitions, priority rules
├── ui/              # face, cards, QR, error/offline screens
├── integration/     # CRM WebSocket/API client
├── hardware/        # адаптери touch, ToF, NFC, audio, RGB, camera
├── vision/          # face detect; віддає події, не кадри
├── media/           # відтворення звуку/анімацій, не самі assets
├── health/          # logs, metrics, watchdog-facing health
└── platform/        # Raspberry Pi lifecycle/update helpers
```

Це логічна схема, а не вимога створити всі модулі до вибору стека.

## Машина станів

Мінімальні системні стани:

- `booting` — перевірка конфігурації та модулів;
- `ready` — базовий mascot/info idle;
- `interacting` — активний touch/NFC/voice/QR сценарій;
- `offline` — CRM недоступна, локальна функціональність збережена;
- `degraded` — необов'язкова периферія відмовила;
- `service` — діагностика без звичайного контенту й без активної камери;
- `shutting_down` — завершення дій, зупинка захоплення, sync і shutdown;
- `fault` — небезпечний або невідновлюваний стан.

Окремі `mascot/qr/info/nfc/voice` є режимами контенту, а не заміною системних станів. Наприклад `offline + mascot` є валідною комбінацією.

## Поведінка режимів

### mascot

- loop анімацій обличчя з обмеженим навантаженням;
- реакція на ToF/touch і на детекцію обличчя: погляд у бік людини;
- плавне повернення в нейтральний погляд, коли обличчя зникає з кадру;
- необов'язкові короткі RGB/audio акценти;
- cooldown, щоб акценти не спрацьовували безперервно.

### qr

- QR генерується з валідованого payload;
- достатня quiet zone, контраст і розмір;
- CTA не перекриває QR;
- timeout і повернення до попереднього режиму;
- за можливості локальний scan test для цільового екрана.

### info

- шаблонований контент без довільного виконуваного HTML/коду з CRM;
- обмеження довжини, шрифту та кількості сторінок;
- fallback для відсутніх assets.

### nfc

- підказка, де торкнутися;
- debounce повторних читань;
- зрозумілий success/error стан;
- ідентифікатори карток не логуються відкритим текстом без окремого рішення.

### voice

- явний стан `listening` і можливість скасування;
- timeout, error і offline behavior;
- індикатор активного мікрофона;
- pipeline розпізнавання/відповіді та місце обробки TODO.

## Конфігурація

Очікувані групи параметрів:

- identity: `device_id`, site/installation label;
- CRM endpoints і reconnect policy;
- feature flags для NFC/voice/camera/fan;
- hardware adapter selection і calibrated limits;
- brightness/volume/quiet hours;
- thermal і health thresholds після тестів;
- content fallback та locale;
- logging level без секретів.

Секрети не входять до звичайного config-файлу в Git. Схема, формат і спосіб захищеного provisioning — TODO.

## Vision

Окремий шар, бо він єдиний бачить кадр.

- працює лише в режимі `mascot`; в інших режимах захоплення зупиняється;
- обробляє зменшений кадр і не тримає повнорозмірний довше за один прохід;
- віддає вгору лише події: `face.present`, кількість, груба позиція й відстань;
- ніколи не віддає, не логує і не кешує зображення — заборона `D-027` реалізується межею модуля, а не дисципліною виклику;
- стан захоплення синхронний з апаратним індикатором (`D-029`): індикатор гасне лише коли захоплення реально зупинено;
- має fake-реалізацію, що програє записаний сценарій подій без камери.

## Hardware abstraction

Кожний адаптер має надавати:

- `initialize` із явним результатом;
- операції з timeout/cancellation;
- нормалізовані події;
- `health`/capabilities;
- безпечний `shutdown`;
- fake/mock реалізацію для тестів.

Для RGB/audio потрібен scheduler: одна команда режиму не повинна залишати підсвітку або звук активними після скасування сценарію.

## Надійність

- App стартує автоматично після boot і повідомляє `ready` лише після критичних self-checks.
- Необов'язкові модулі можуть перевести пристрій у `degraded`, а не в crash loop.
- CRM reconnect використовує backoff/jitter і не блокує UI.
- Команди мають idempotency/correlation ID та строк актуальності.
- Локальні черги мають верхню межу; прострочені команди не відтворюються після reconnect.
- Watchdog перезапускає завислий процес, але не маскує повторювану апаратну помилку.

## Оновлення

Потрібний механізм:

1. підписаний/перевірений пакет або image;
2. перевірка сумісності конфігурації;
3. контрольований restart у quiet window;
4. health check після оновлення;
5. rollback або відновлення носія.

Точна технологія TODO. Віддалений shell не слід вважати production update strategy.

## Тестування

- unit: state transitions, priority, timeouts, payload validation, QR content, мапінг подій vision у поведінку погляду;
- integration: fake CRM, reconnect, duplicate/out-of-order commands, offline recovery;
- UI: цільова роздільність, touch targets, читабельність і QR scan test зовнішнім телефоном;
- hardware-in-loop: кожний модуль і комбінації навантаження;
- endurance: тривалий loop UI/network, audio/RGB, temperature soak;
- fault injection: від'єднання периферії, CRM loss, low storage, app restart;
- privacy: перевірка, що жоден кадр не потрапляє в журнали, телеметрію чи файлову систему.

## TODO до першого коду

- [ ] Вибрати платформу і стек через вимірюваний UI/animation proof of concept (`D-022`, `D-015`).
- [ ] Підтвердити роздільність та touch mapping дисплея.
- [ ] Узгодити CRM draft contract і локальну simulator/fake server.
- [ ] Описати config schema та secret provisioning.
- [ ] Визначити support matrix для периферії.
- [ ] Вибрати logging, watchdog, update і rollback підхід.
- [ ] Описати privacy behavior voice/NFC/camera в межах `D-027` і `D-029`.

