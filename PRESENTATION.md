# UI Presentation Layer

SoT = `harvest/`. UI читает **снимок**, не пишет в базу.

## Два режима полей

| mode | Когда | Кто пишет |
|---|---|---|
| `literal` | В карточке однозначно (имя, девиз, цель, списки фактов) | `tools/lh_ui_snapshot.py` из Markdown |
| `interpreted` | Нужна компоновка, акцент, формулировка для экрана | Harvester правит `overlay.json`, затем снова snapshot |

Запрещено: выдуманные KPI, гипотеза как факт, секреты.

## Пайплайн после харвеста

1. Записать знания в `harvest/`.
2. При необходимости обновить `harvest-ui/overlay.json` (акценты, razvivator, blurbs вселенной, порядок).
3. `python tools/lh_ui_snapshot.py`
4. UI подхватит `snapshot.json` (кнопка «Обновить» или авто-poll ~12 с).

## Файлы

- `overlay.json` — слой интерпретации (не SoT)
- `snapshot.json` — результат merge (генерируется)
- `data.js` — тот же снимок для офлайн/fallback (генерируется)
