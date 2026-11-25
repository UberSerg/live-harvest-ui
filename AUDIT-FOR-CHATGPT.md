# Live Harvest — что реализовано (для аудита ChatGPT)

Дата выгрузки: 2026-11-25  
Репозиторий: публичный UI-код. **Приватный ledger и реальные суммы в GitHub не входят.**

## Продукт

Personal Command Center (vanilla HTML/CSS/JS) + модуль **Капитал** с локальным API.

## UI v0.4.1 → Capital UX

- Три основных экрана: Обзор, Личность, Моя вселенная + **Капитал** в навигации.
- Редакционный тёмный UI (не bento-админка); широкая раскладка (`--max` до ~1480–1680px на Капитале).
- Universe: single-render SVG, без пересоздания DOM на клик.
- Live snapshot: `snapshot.json` + poll / «Обновить снимок»; SoT знаний — Markdown `harvest/` (локально).
- Presentation layer: `overlay.json` (interpreted) + `tools/lh_ui_snapshot.py` (literal merge).

## Модуль Капитал (MVP)

### Хранение (локально, не в этом репо)

- YAML ledger: accounts, categories, transactions, recurring, liabilities, assets, valuations, scenarios, `_journal`, `_backups`.
- Деньги: `amount_minor` (целые копейки), без float.
- Статусы: `actual` | `planned` | `estimated` | `forecast` | `void`.
- Переводы ≠ доход/расход; корректировки через void + replacement + journal.
- Схема: см. комментарии в `tools/capital/` и `PRIVACY-CAPITAL.md`.

### API

- `tools/capital_api.py` → **только** `http://127.0.0.1:8777/`
- Заголовок `X-LH-Capital: local` + Origin localhost для мутаций.
- Endpoints: health, summary, accounts, transactions (+void/correct), recurring, categories, liabilities, assets.

### UI Капитал (`capital.js`)

- KPI с акцентом на **плановый профицит** и курс на финансовую независимость.
- Долг / обязательства — в свёрнутом блоке со щитом (не в первом экране).
- Chart.js (локально `vendor/chart.umd.min.js`): доходы/расходы, структура расходов.
- Режим редактирования: счета, операции (факт/план), регулярные шаблоны.
- План и факт в summary разделены (`flows` vs `planned_flows` / `recurring_monthly`).

### Тесты

- `python -m tools.capital.tests` — money, transfer, void, correction, recurring net, net worth.

## Запуск локально

```bash
# UI
cd live-harvest-ui && python -m http.server 8765

# API (нужен приватный harvest/Капитал рядом в полном vault)
PYTHONPATH=<vault-root> python tools/capital_api.py
```

Публичный clone показывает UI + demo snapshot; полный ledger работает только с приватным vault.

## Privacy

- В репо: код + `demo/snapshot.demo.json`.
- Не коммитить: реальные остатки, зарплата, ипотека, YAML ledger.
- Если аудит касается финансовых цифр — запрашивать их у владельца отдельно, не из этого GitHub.

## Известный долг

- Сценарии прогноза в UI — заготовка.
- CSRF пока = shared header, не session token.
- Mobile nav — стек, не drawer.
- Полный wiring всех карточек Harvest → UI без ручного overlay — частичный.

## Просьба к аудитору

Оцени: (1) архитектуру Капитала и разделение actual/planned, (2) UX «сила потока vs долг», (3) безопасность localhost API, (4) риски privacy при публикации UI, (5) что критично допилить до daily-driver.
