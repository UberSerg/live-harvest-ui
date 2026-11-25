# Privacy — модуль Капитал / публичный UI-репо

## Правила

- Реальные остатки, доходы, долги живут только в `harvest/Финансы/Капитал/` (локально, `privacy: sensitive`).
- Публичный `live-harvest-ui` содержит **код** + **синтетический demo snapshot** без персональных сумм.
- `snapshot.json` / `data.js` / `overlay.json` для GitHub — demo-профиль или обезличенные формулировки.
- Скриншоты ревью с реальными цифрами не коммитить.
- Capital API только `127.0.0.1`.

## Уже в истории GitHub

Ранее в `live-harvest-ui` публиковались портретные факты (имя, роль, цели, challenge).  
**Банковских остатков / зарплаты в копейках в UI-снэпшоте не было**, но личные формулировки — да.

Если нужна зачистка истории — отдельный план (filter-repo / новый репо), не делать force-push без явной просьбы.

## Генератор

`tools/lh_ui_snapshot.py` пишет только локальные `harvest-ui/snapshot.json` и `data.js`.  
Флаг `--also-demo` **запрещён** для реальных данных: demo-фикстуры не перезаписываются harvest SoT.  
Публичный репозиторий синхронизируется с `demo/snapshot.demo.json`, не с личным snapshot.

## Импорт выписки

- Обработка только через localhost Capital API.
- Не передавать текст выписки в чат Cursor / GitHub / agent logs.
- Не сохранять raw statement в localStorage и YAML.
- Тесты — только synthetic (`tools/capital/fixtures/`, `gen_synthetic_statement.py`).
