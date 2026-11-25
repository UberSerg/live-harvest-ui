# Live Harvest UI

Personal cognitive interface (static). Public tree = **synthetic demo only**.

## Quick start

```bash
python -m http.server 8771
```

- App: http://127.0.0.1:8771/
- Demo snapshot: http://127.0.0.1:8771/?demo=1

## BRAIN EVOLUTION 01 (public)

IA: **Первый кадр** — Сегодня · Мозг (линзы) · Вселенная · Капитал.

Evaluation brief for external review: [`docs/BRAIN-EVO-01-FOR-CHATGPT.md`](docs/BRAIN-EVO-01-FOR-CHATGPT.md)  
Constitution draft: [`docs/BRAIN_CONSTITUTION.md`](docs/BRAIN_CONSTITUTION.md)  
UI design decision: [`design/BRAIN-UI-EVOLUTION-01.md`](design/BRAIN-UI-EVOLUTION-01.md)  
Harness: [`design/HARNESS.md`](design/HARNESS.md)

Brain CLIs (synthetic fixtures under `tools/fixtures/`): retrieve, consolidate, ingest, research packet, contest, decisions, experiments, finance_reflect (status class only — no amounts).

## Layout

- `index.html` / `styles.css` / `app.js` / `capital.js` / `data.js`
- `demo/` — synthetic snapshot + research packet
- `tools/` — Capital + brain helpers (no private ledger)
- `archive/` — older UI versions
- `review/` — reviews (no real statements)

## Boundaries

Private `harvest/` and Capital ledger stay local. This repo must not contain real balances, statements, or diary text.
