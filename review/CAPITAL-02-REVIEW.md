# CAPITAL-02 — Review

Дата: 2026-11-25  
Репозиторий кода (public): https://github.com/UberSerg/live-harvest-ui  
SoT ledger: приватный `harvest/Финансы/Капитал/` (не в public GitHub)

## Что исправлено (аудит MVP)

| Дефект | Исправление |
|---|---|
| Суммирование разных валют без курса | База RUB; `fx_rates/`; без курса валюта не входит в NW |
| Погашение тела не уменьшало долг | `liability_id` + `liability_principals()`; банк-остаток через `/api/liabilities/principal` |
| Correction из нескольких записей без единой атомарности | void + replacement + journal под одним lock |
| Будущие операции в текущем балансе | `as_of` + фильтр дат; opening_date учитывается |
| Неизвестный остаток = 0 | `balance_known: false` / `null` opening → не в liquid |
| Двойной учёт recurring + planned | `planned_without_double_count` + materialize |
| «Профицит» как полный free cashflow | бюджет помечает незаполненные статьи |
| Snapshot мог затереть demo | `lh_ui_snapshot.py` отказывается писать в `demo/` |

## Что реализовано

- Вкладки UI: Обзор, Операции, Счета и активы, Бюджет, Обязательства, Прогноз, Цели/FI
- Операции: add / correct / void / duplicate / confirm planned; фильтры; toast + dialog (без alert)
- Сверка остатков с банком; ручной FX; активы + valuations
- Сценарии (forecast only); FI-параметры без авто-включения жилья
- API v0.2: fx, statements, materialize, confirm, duplicate, fi, scenarios/project
- Тесты: 23 green (валюты, долг, план/факт, unknown balance, scenarios, store)

## Результаты тестов

```
python -m tools.capital.tests
Ran 23 tests … OK
```

## Скриншоты

Локальный UI после CAPITAL-02: см. `review/lh-capital-02-*.png` (если сняты в прогоне) и предыдущий `lh-capital-desktop.png`.

## Ограничения

- Нет учёта отдельных бумаг на брокере (только оценка портфеля)
- Нет автозагрузки курсов ЦБ
- Edit суммы через dialog; полный inline-edit всех полей — позже
- CSRF/Origin — localhost-only; без JWT (осознанно)
- Историческая динамика NW/долга рисуется только при наличии точек
- Кеш-остатки в ledger всё ещё **не подтверждены** → Financial Harvester

## Готовность к ежедневному использованию

**Да, для учёта плана/факта и обязательств** при запущенном `capital_api.py`.  
Полноценная модель капитала — после подтверждения остатков счетов и заполнения переменных статей бюджета.
