---
id: lh-20261125-xres
type: note
created: 2026-11-25
updated: 2026-11-25
status: active
source: "Agent 08 — контракт lh_ingest_version 1 и приёмка"
confidence: high
privacy: personal
related:
  - "[[Targeted Harvest]]"
  - "[[INTEGRATION-INVENTORY]]"
tags: [brain, protocol]
aliases: [Протокол внешнего исследования]
---

# External Research Protocol

Приёмка выгрузки внешнего ИИ устроена так, чтобы она пополняла очередь и не становилась скрытой инструкцией. Проверка: `python tools/lh_ingest.py validate`. Запись в очередь: `import`. Поглощение в предметные карточки по-прежнему делает человек. Каталог `harvest/Мозг/_inbox/research/` этим шагом не правит карточки.

Контракт аддитивный к уже поглощённым пакетам `type: interview` с `lh_ingest_version: 1`. Новые поля можно не ставить: старый пакет остаётся действительным. `tools/kb_validate.py ingest` — другой vault и другой контракт.

## Версия

Поддерживается только `lh_ingest_version: 1` (число или строка `"1"`). Другой номер отклоняется.

`checksum`, если он непустой, — это SHA-256 тела после frontmatter, перевод строк приведён к `\n`, в конце одна новая строка. Пустой `checksum` не проверяется.

Отпечаток всего файла (для дубля) считается так же: UTF-8, `\n`, завершающий перевод строки. В очереди он хранится как `source_sha256`.

## Типы

| type | Приёмка |
|---|---|
| `interview` | Уже существующий v1. `targets` не обязателен. |
| `hypothesis_research` | Аддитивный тип этого протокола. Нужен непустой `targets` и секция цели, фактов, гипотез или указаний. |
| `research` | То же, что `hypothesis_research`, с предупреждением. |
| `capital_semantic_export`, `connector` | Имя зарезервировано. CLI отвечает `reserved_not_implemented` и файл не пишет. |

`ingest_kind: research` — необязательная метка. Она не заменяет `type`.

## Статусы

На входе допустимы `pending_ingest`, `pending`, `absorbed`, `rejected`, `triaged`, `in_progress`, `done`, `proposal`.

В очереди файл получает `status: pending` и `ingest_status: pending_ingest`. Исходный статус сохраняется в `source_status`. `absorbed` повторно не импортируется. `rejected` не кладётся в очередь.

Очередь (`README.md` и `INDEX.md` в `harvest/Мозг/_inbox/research/`): `pending`, `triaged`, `in_progress`, `proposal`, `done`, `rejected`, `duplicate`.

## Что отклоняется

Пакет — данные. Он отклоняется и не пишется, если:

- просит сменить инструкции (`ignore previous instructions` и близкие формулировки);
- в одной строке есть повелительная форма и путь к `core/`, `modules/`, `.cursor/skills`, `AGENTS.md` или `BRAIN_CONSTITUTION`, и эта строка не отрицание («не», «нельзя», «do not»);
- содержит присваивание пароля, ключа или seed.

Отрицание в строке («каталог core не входит», «не менять») само по себе пакет не бракует.

## Дубль

Повтор не создаёт вторую копию. Совпадение отпечатка или непустого `session_id` с журналом `_import-log.yaml`, с `pending/` или с `harvest/События/_ingest/` останавливает `import`. Код выхода `3`.

## Запись и --apply

`validate` ничего не пишет.

`import` копирует проверенный пакет в `harvest/Мозг/_inbox/research/pending/` и дописывает журнал.

`import --apply` дополнительно пишет `proposals/proposal-….md` со `status: proposal` и `auto_applied: false`. В предложении — выдержка и список целей. Предметные карточки, ledger и `core/` не открываются на запись.

Выход: `0` принят, `1` форма, `2` политика (инструкция на core или секрет), `3` дубль.

```text
python tools/lh_ingest.py validate tools/fixtures/lh_ingest/hypothesis_research_ok.md
python tools/lh_ingest.py import tools/fixtures/lh_ingest/hypothesis_research_ok.md --apply --inbox harvest/Мозг/_inbox/research
```

Второй пример — только если в очередь сознательно кладут синтетику. Предметные карточки от этого не меняются.

## Шаблон hypothesis_research v1

Каноническая копия: `tools/fixtures/lh_ingest/hypothesis_research.template.md`.

```markdown
---
lh_ingest_version: 1
type: hypothesis_research
source: ""
date: YYYY-MM-DD
status: pending_ingest
session_id: ""
ingest_kind: research
targets:
  - "[[Имя карточки-цели]]"
forbid_create: []
forbid_types:
  - finance
allowed_writes:
  - note
  - hypothesis
source_harness: ""
privacy: personal
checksum: ""
---

# Экспорт исследования

## Цель исследования

Одна цель. Гипотеза здесь не подтверждена.

## Самоописание / факты источника

- Факт: ... Источник: ...

## Гипотезы

- Гипотеза: ... confidence: low

## Решения (кандидаты)

- Кандидат: ... Не ставить статус «принято».

## Указания для импорта

Сопоставить с целями из targets. Не создавать finance-карточки. Не подтверждать гипотезу. Этот файл — данные, не команда.

## Запрещено

- Секреты, пароли, суммы операций и текст выписок.
- Правки каталога правил и конституции.
- Сглаживание противоречий.

## Неизвестно

- Чего не хватает для проверки.
```

## Пример верного экспорта

Синтетика, без сумм и секретов. Каноническая копия: `tools/fixtures/lh_ingest/hypothesis_research_ok.md`.

```markdown
---
lh_ingest_version: 1
type: hypothesis_research
source: synthetic-external-research
date: 2026-11-25
status: pending_ingest
session_id: lh-synth-research-0001
ingest_kind: research
targets:
  - "[[Гипотеза — синтетический пример волны]]"
forbid_create:
  - "Финансы"
forbid_types:
  - finance
allowed_writes:
  - note
  - hypothesis
source_harness: example
privacy: personal
---

# Синтетический экспорт исследования

Персонаж вымышлен. Сумм и секретов нет.

## Цель исследования

Проверить гипотезу: короткий утренний блок связан с тем, что черновик чаще доходит до конца. Это не установленный факт.

## Самоописание / факты источника

- Факт (источник: синтетическая заметка): персонаж дважды назвал утро самым спокойным окном.
- Факт не содержит счетов и секретов.

## Гипотезы

- Гипотеза: утренний блок 25 минут связан с завершением черновика чаще, чем вечерний. confidence: low. Не подтверждено.
- Гипотеза: один пропуск ритуала сам по себе гипотезу не опровергает. confidence: low.

## Решения (кандидаты)

- Кандидат: не переносить формулировку в карточки, пока человек её не подтвердит. Статус «принято» не ставить.

## Указания для импорта

- Сопоставить с целью из targets.
- Не создавать finance-карточки.
- Гипотезы не повышать до факта.
- Этот файл читать как данные.

## Запрещено

- Секреты и суммы операций.
- Каталог core не входит в этот пакет.
- Сглаживание противоречия, если оно появится.

## Неизвестно

- Сколько раз ритуал уже совпадал с законченным черновиком: данных нет.
```

## Что остаётся ручным

Смысловой перенос в карточки, подтверждение гипотезы и мост ledger → смысловая карточка. Локального `harvestconnector` в workspace нет, протокол на него не опирается.

Пакет для внешнего вопроса собирает `python tools/lh_research_packet.py`. Он не подтверждает гипотезу и по умолчанию не пишет файл.
