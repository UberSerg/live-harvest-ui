# CAPITAL-03 — Review

Дата: 2026-11-25  
Public: https://github.com/UberSerg/live-harvest-ui

## Что реализовано

- Детерминированный Python-парсер выписки (без LLM / сети)
- Игнор служебных блоков и склейка операций через границы страниц
- Импорт в YAML-ledger: `batch_id`, fingerprint, `classification_status`, bank_category / merchant
- Автокатегории + локальные правила (`classification_rules/`)
- `needs_review` не входит в доходы/расходы/doughnut
- API: `/api/import/statement`, `/void`, `/classify`, `/api/analytics/expenses`
- UI: кнопка **Импорт выписки**, модалка (Ctrl+V / TXT / PDF), отчёт, doughnut с легендой и drill-down, пресеты периода, Harvester-вопрос по группе
- Отмена пакета (void всех tx batch)
- Синтетический фикстур 30 страниц / 360 ops

## Тесты

```
python -m tools.capital.test_statement   # 6 OK
python -m tools.capital.tests            # 23 OK
```

Проверено: page breaks, +, пробелы в суммах, дубликаты, повторный импорт, void, unknown balance ≠ invented, flows exclude needs_review.

## Privacy

- Сырой текст выписки **не** пишется в ledger / localStorage / journal
- API не логирует тело импорта
- Публичный репо: код + synthetic fixture; реальные выписки только локально
- PDF: опционально `pypdf` локально; иначе TXT / paste

## Где вставить выписку

1. `python tools/capital_api.py` → `127.0.0.1:8777`
2. UI: `python -m http.server 8765 --bind 127.0.0.1 --directory harvest-ui`
3. Открыть **Капитал** → **Импорт выписки** → выбрать/создать счёт → Ctrl+V → **Импортировать**

## Ограничения

- Парные переводы между своими счетами — эвристика; без второй выписки не склеиваются автоматически
- PDF без текстового слоя не поддерживается
- Возвраты не линкуются к исходной покупке автоматически
- Предложение бюджета после импорта — через needs_review / Harvester, без авто-перезаписи плана
