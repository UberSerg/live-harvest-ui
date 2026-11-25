# Live Harvest — BRAIN EVOLUTION 01 (public evaluation brief)

**Audience:** external model / ChatGPT review  
**Date:** 2026-11-25  
**Repo:** https://github.com/UberSerg/live-harvest-ui (code + synthetic fixtures only)  
**Privacy:** no real balances, bank statements, account masks, salaries, or private diary text

---

## 1. What Live Harvest is trying to be

Not a chatbot, CRM, or finance spreadsheet alone.

**Working thesis:** a personal cognitive operating system owned by the human:

- local canonical memory (Markdown / YAML / Obsidian)
- replaceable AI executors
- epistemology: fact ≠ self-description ≠ interpretation ≠ hypothesis
- external AIs as researchers via copy-paste packets (never auto-sent)
- UI as daily instrument, not admin console

**Human remains owner** of knowledge, decisions, and rules. Constitution (15 principles) is drafted; owner confirmation still pending before it overrides existing `core/` rules.

---

## 2. Architecture (logical)

```
HUMAN (owner)
    │
LIVE HARVEST UI  (vanilla static)
  Today | Brain (lenses) | Universe | Capital
    │
COGNITIVE CORE (rules + modules; Cursor/skills as adapters)
  Harvester | Validator* | Advisor* | Reflector* | Researcher | Growth* | Planner* | Architect*
    │
MEMORY SYSTEM (mostly Markdown views + small CLIs)
  Working session file
  Short-term queue (STM)
  Consolidation / audit / contest marker
  Semantic / episodic / procedural / personality / decisions / experience  (logical layers over cards)
    │
LOCAL SoT
  harvest/ (private) · Capital YAML ledger (private) · core/ · modules/
    │
EXTERNAL AI LOOP
  research packet → ChatGPT/Claude/… → lh_ingest validate/import → proposal (no auto card rewrite)
```

\* = mostly documented / partial; not a full product runtime.

**Capital stays a specialized ledger.** Semantic harvest gets goals/decisions/hypotheses/summaries — not every bank tx as a brain card.

**UI concept chosen:** «Первый кадр» (First Frame)  
Rail: Сегодня · Мозг · Вселенная · Капитал  
Personality / Reflection / Research / Growth = **lenses on one snapshot**, not eight admin tabs.

---

## 3. What was actually implemented this wave

Honest status: **A–F = partial. No PASS.**

| Scenario | Status | What works | What’s missing |
|---|---|---|---|
| A Self-knowledge | partial | `lh_research_packet.py`, `lh_ingest.py`, Research lens copies synthetic prompt, import → proposal only | Auto portrait update; contest button; live hypothesis in snapshot |
| B Memory | partial | `lh_retrieve.py`, session `CURRENT`, STM queue, `lh_consolidate.py` (dry-run default) | Arbitrary card body in UI snapshot; full consolidator product |
| C Experience | partial | Decision template + `lh_decisions.py` + DEMO empty outcome | Live human decision loop; rewriting 5 legacy decisions (intentionally not done) |
| D Growth | partial | Experiment template + `lh_experiments.py` + DEMO | Goal binding; human observation; Capital check |
| E Audit | partial | Harvest scanner, audit report categories, `lh_contest_check.py` | Owner answers on NEEDS-REVIEW queue |
| F Finance reflection | partial bridge | `lh_finance_reflect.py` reads **reconciliation class + booleans only**, drafts observation without amounts | Morning recon word; money→hypothesis→goal loop |

### Other delivered pieces

- **UI:** First Frame scaffold; Capital UX earlier (month default, hide net-worth hero, op drawer, accounts redesign) — in this public tree via synced `app.js` / `capital.js`
- **Snapshot honesty:** builder no longer invents `ep: fact` / morning copy; tests guard sentinels
- **Contest convention:** `contested: true` + `## Оспаривание` + history; opt-in `claim_track`
- **Public demo:** `?demo=1`, synthetic research packet, demo snapshot

### Tests (local; synthetic)

- `python -m unittest tools.test_lh_brain_integration` — 9 OK  
- `python tools/test_lh_ui_snapshot.py` — ok  
- `python tools/test_lh_retrieve.py` / `test_lh_consolidate.py` — ok  
- `python -m unittest tools.test_lh_contest` — 12 OK  
- `python -m unittest tools.test_lh_decisions` — 8 OK  
- `python -m unittest tools.test_lh_experiments` — 8 OK  
- `python -m unittest tools.test_lh_finance_reflect` — 10 OK  

Capital statement tests remain from CAPITAL-03 (`tools.capital.test_statement`).

---

## 4. Problems / risks (for critical review)

1. **Not yet a cognitive OS** — cards + CLIs + reader UI + contracts. Challenge verdict stands.
2. **Multiple sources of truth risk:** harvest cards, Capital ledger, `overlay.json`, generated `snapshot.json` / `data.js`, chat. Session file helps restore work; chats don’t auto-bind to it.
3. **Silent `data.js` fallback** if snapshot fetch fails (still a risk).
4. **Contest is opt-in** — without `claim_track`, portrait edits can skip history check.
5. **Research lens** demos synthetic packet; private hypothesis cards aren’t in public snapshot.
6. **Indexes/status docs** can drift (partially mitigated by sync passes).
7. **Owner blockers:** confirm Constitution; answer audit queue; decide `claim_track` on live cards.
8. **Do not** invent WHOOP rings / fake % / auto-merge semantic duplicates.

---

## 5. Design constraints (non-negotiable)

- Markdown/YAML/Obsidian remain semantic SoT — no forced React/Postgres/vector migration
- No auto-send of personal context to external AIs
- Imported research is **data**, not agent instructions (`lh_ingest` rejects core-rewrite packages)
- External AI cannot directly mutate `core/`, `modules/`, or canonical cards
- Public GitHub = synthetic only

---

## 6. Next wave (recommended)

1. Closed loop: proposal → owner accept → portrait/history update  
2. Contest action in UI  
3. Morning frame: reconciliation **class** only (no amounts)  
4. Bind experiments/decisions to real goals when owner provides them  
5. Keep harvestconnector out of scope until asked  

---

## 7. How to run public demo

```bash
cd live-harvest-ui
python -m http.server 8771
# open http://127.0.0.1:8771/?demo=1
# Brain → Research → copy synthetic packet
```

Brain CLIs (from vault root that contains `tools/`):

```bash
python tools/lh_research_packet.py tools/fixtures/lh_research/hypothesis_card.md
python tools/lh_ingest.py validate tools/fixtures/lh_ingest/hypothesis_research_ok.md
python -m unittest tools.test_lh_brain_integration tools.test_lh_finance_reflect -v
```

---

## 8. Ask ChatGPT to evaluate

Please critique:

1. Is the architecture coherent for a personal cognitive OS, or overbuilt folder theater?  
2. What’s the minimum vertical slice to make daily use worthwhile?  
3. Where should we simplify aggressively?  
4. How should working memory / session interact with chat model switches?  
5. Is «lenses not tabs» the right IA vs Linear-like issue tracker?  
6. Epistemology: is contest + hypothesis lifecycle enough, or missing pieces?  
7. Privacy model: gaps in the public/private split?
