# Live Harvest Capital — CAPITAL-03 brief

Public repo: code + synthetic fixtures only.

## New in CAPITAL-03

Bank statement import (paste / TXT / PDF text layer) → local parser → YAML ledger → doughnut expense analytics.

- No LLM, no external APIs
- Page-break noise stripped; ops stitched across pages
- Fingerprint dedupe; batch void; needs_review excluded from consumer flows
- UI: Капитал → «Импорт выписки»

## Tests

`python -m tools.capital.test_statement` (synthetic 30-page generator included)

## Privacy

Raw statements never stored in ledger / GitHub / agent logs. Demo account + synthetic text only in public tests.
