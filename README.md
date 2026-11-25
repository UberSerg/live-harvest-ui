# Live Harvest UI

Personal Command Center (static, read-only). Version **0.4**.

## Quick start

```bash
cd harvest-ui
python -m http.server 8765
```

http://localhost:8765/

## v0.4

- Editorial layout (не bento-админка)
- Три экрана: Обзор · Личность · Моя вселенная
- Universe: single-render SVG, без пересоздания DOM на клик
- Progressive disclosure

## Layout

- `index.html` / `styles.css` / `app.js` / `data.js`
- `design/HARNESS.md` — канон v0.4
- `archive/v0.1` … `v0.3` — предыдущие версии
- `review/` — скриншоты и review notes

## Boundaries

Read-only. SoT = `harvest/`. Демо маркируется. Персональные KPI не выдумываются.
