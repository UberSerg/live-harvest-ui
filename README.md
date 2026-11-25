# Live Harvest UI

Personal Command Center (static, read-only). Version **0.4**.

## Quick start

```bash
cd harvest-ui
python -m http.server 8765
```

http://localhost:8765/

## v0.4.1

- Editorial layout + live snapshot из `harvest/`
- Literal (скрипт) + interpreted (`overlay.json`) — см. `PRESENTATION.md`
- После харвеста: `python tools/lh_ui_snapshot.py` → UI poll / «Обновить снимок»
- Три экрана: Обзор · Личность · Моя вселенная

## Layout

- `index.html` / `styles.css` / `app.js` / `data.js`
- `design/HARNESS.md` — канон v0.4
- `archive/v0.1` … `v0.3` — предыдущие версии
- `review/` — скриншоты и review notes

## Boundaries

Read-only. SoT = `harvest/`. Демо маркируется. Персональные KPI не выдумываются.
