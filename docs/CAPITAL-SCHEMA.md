# Капитал — схема хранения v1 (CAPITAL-02)

SoT финансовых **операций и остатков**: эта папка.  
Контекст, цели и решения — в обычных карточках `harvest/` (`type: finance|goal`). Показатели не дублировать вручную.

## Деньги и валюты

- Суммы — **целые минимальные единицы** (`amount_minor`).
- Валюты: `RUB` (база отчётности), `USD`, `EUR`.
- Остатки хранятся в оригинальной валюте.
- Конвертация только по явным курсам в `fx_rates/` (дата + rate). Нет курса → валюта не суммируется в net worth, значение не выдумывается.
- Floating-point в учёте запрещён.

## Статусы записей

| status | Смысл | В факт-отчётности |
|---|---|---|
| `actual` | Подтверждённая операция/остаток | да |
| `planned` | План | нет |
| `estimated` | Оценка | отдельно |
| `forecast` | Расчётный прогноз | нет (сценарии) |
| `void` | Отменена | нет (след в истории) |

## Типы транзакций

| type | Эффект |
|---|---|
| `income` | + на счёт |
| `expense` | − со счёта |
| `transfer` | −/`+` между счетами (не доход/расход) |
| `debt_principal` | − со счёта + уменьшение тела (`liability_id` обязателен) |
| `debt_interest` | − со счёта как расход; тело не трогает |
| `adjustment` | корректировка; `corrects_id` или comment |

Поля долга: `liability_id`, опционально `principal_portion_minor` / `interest_portion_minor`.  
Если разбивка ипотеки неизвестна — обновить `principal_remaining_minor` + `principal_as_of` по банку (`/api/liabilities/principal`).

## Счёт

```yaml
balance_known: false          # неизвестный остаток ≠ 0
opening_balance_minor: null
opening_date: 2026-11-25
linked_asset_id: null         # брокер: не двойной учёт с активом
account_kind: checking|savings|deposit|cash|broker|other
```

Сверка: `balance_statements/` + `/api/accounts/statement`.

## План / факт / прогноз

- **Recurring** — шаблон. Материализация → `planned` tx с `recurring_id`.
- Подтверждение плана → void шаблона-операции + `actual` (`confirm_planned`).
- Сценарии в `scenarios/` — forecast only, ledger не меняют.
- FI-параметры — `fi_params/` (цель, SWR, yield); жильё в FI только при `include_home_in_fi: true`.

## Файлы

```
Капитал/
  accounts/ categories/ transactions/ assets/ liabilities/
  goals/ recurring/ valuations/ scenarios/
  fx_rates/ balance_statements/ fi_params/
  _journal/ _backups/ _meta.yaml
```

## Атомарность

- tempfile → `os.replace`; backup перед мутацией; file lock.
- Correction: void + replacement + journal **под одним lock**.
- Дубликаты: 409 `duplicate_suspect` без `allow_duplicate`.

## Импорт выписки (CAPITAL-03)

- Парсер: `tools/capital/statement_parse.py` (локально, без LLM).
- Пакет: `import_batches/`; правила: `classification_rules/`.
- Поля tx: `batch_id`, `fingerprint`, `direction`, `bank_category`, `merchant`, `authorization_code`, `classification_status`, `include_in_flows`, `economic_kind`, `imported_at`.
- Сырой текст выписки **не** хранится.
- `needs_review` / internal transfers не входят в consumer income-expense и doughnut.
- **Банковский оборот** (все actual in/out) и **экономическая аналитика** — разные срезы; сверка footer `Пополнение`/`Списание` при импорте.

## API

Только `127.0.0.1:8777`, заголовок `X-LH-Capital: local`, Origin localhost.  
Импорт: `POST /api/import/statement` (text | file_base64).
