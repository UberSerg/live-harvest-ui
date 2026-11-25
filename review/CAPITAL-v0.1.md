# Capital module v0.1 — delivery notes

## Запуск

```powershell
# UI
cd harvest-ui
python -m http.server 8765

# API (отдельный терминал)
cd <vault root>
$env:PYTHONPATH=(Get-Location)
python tools/capital_api.py
```

UI: http://127.0.0.1:8765/#capital  
API: http://127.0.0.1:8777/ (только localhost)

## Выбор графиков

**Chart.js 4** (локально `vendor/chart.umd.min.js`): без сборщика, лёгкий UMD, достаточно bar/doughnut для MVP. ECharts мощнее для больших дашбордов — подключать точечно позже.

## Тесты

```powershell
$env:PYTHONPATH=<root>
python -m tools.capital.tests
```

8/8 OK: money, transfer≠income/expense, void, correction, net worth.

Smoke API: transfer 1000→250 между счетами; income/expense 0; balances 750/250; void.

## Privacy

- Ledger в `harvest/Финансы/Капитал/` — не для GitHub.
- Публичный репо: demo snapshot (`demo/snapshot.demo.json`).
- AUDIT: старые суммы Harvest не импортированы в actual.
- История публичного UI могла содержать портретные факты (не банковские остатки) — см. `PRIVACY-CAPITAL.md`.

## Не сделано в v0.1 (долг)

- Полный UI сценариев прогноза (есть YAML-заготовка baseline).
- Отдельные графики долга/накоплений.
- CSRF token сильнее заголовка `X-LH-Capital: local`.
- Авто-бэкап перед первым запуском всего vault.
