---
id: lh-20261125-fd01
type: note
created: 2026-11-25
updated: 2026-11-25
status: draft
source: "CLI lh_finance_reflect.py draft-observation — фикстура, не книги владельца"
confidence: low
privacy: personal
related:
  - "[[Шаблон финансового наблюдения]]"
  - "[[Reflection Engine]]"
tags: [protocol]
aliases: []
synthetic: true
finance_observation_status: open
reconciliation_class: matched
goal: ""
hypothesis: ""
---

# DEMO — финансовое наблюдение

**Синтетика.** Класс сверки снят с фикстуры, не с книг владельца. Суммы и маски счетов сюда не копируются. Команда совет не пишет.

## Сверка

сверка: matched

message_class: matched

Доступ к API: fixture.

## Полнота

- accounts_complete: false
- free_cash_complete: false
- fx_complete: false
- has_estimates: false
- liquid_complete: true
- net_worth_complete: false

## Период

2026-01-01 — 2026-11-25

## Гипотеза

Пусто.

## Открытый вопрос

что проверить

## Связанная цель

Не задана.

## История

- 2026-11-25 — finance_observation_status пусто → open — сверка: matched — CLI lh_finance_reflect.py draft-observation
