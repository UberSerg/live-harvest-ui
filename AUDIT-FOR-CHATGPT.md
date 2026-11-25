# Live Harvest Capital — CAPITAL-02 audit brief

Public repo: code + synthetic demo only. Real ledger stays private.

## Stack (unchanged)

- SoT: YAML ledger (private vault)
- Local Python API `127.0.0.1:8777`
- Vanilla HTML/CSS/JS + Chart.js
- No new frameworks / DB / cloud auth

## CAPITAL-02 fixes

1. **FX** — reporting base RUB; balances in native currency; explicit fx_rates only; missing rate ⇒ omit from net worth (no invented rates)
2. **Liabilities** — debt_principal linked to liability_id reduces principal; interest does not; bank principal statement supported when split unknown
3. **Corrections** — atomic void+replace+journal under one lock; backups; duplicate detect
4. **Balances** — opening_date; as_of; future txs excluded; unknown ≠ 0; broker double-count guard; bank reconciliation endpoint
5. **Plan/fact/forecast** — recurring materializes to planned ops; confirm→actual; no double-count templates; budget marks unfilled lines; scenarios do not mutate ledger
6. **UI tabs** — Overview / Ops / Accounts / Budget / Liabilities / Forecast / Goals+FI; toasts+dialogs instead of alert; edit without global edit mode
7. **FI** — explicit params; home excluded from FI capital by default
8. **Privacy** — snapshot generator refuses to overwrite `demo/`; public repo uses synthetic snapshot

## Tests

`python -m tools.capital.tests` → 23 OK

## Ask the auditor

- Remaining risks in YAML store / localhost API
- UX gaps for daily personal finance use
- Priority of next Financial Harvester data gaps vs more modeling
