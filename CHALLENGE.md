# Live Harvest UI — Challenge brief

Static Personal Command Center (v0.3). Open `index.html` via any static server (`python -m http.server 8765`).

## Intent
Linear + WHOOP + Obsidian + light Fallout Pip-Boy. Premium graphite Life OS — not an admin panel, not AI-slop dashboard.

## Known weak spots (be ruthless)
1. **Universe graph lags / feels cheap** — custom SVG orbits; motion may jank; looks decorative.
2. **Still reads as neuroslope** — generic dark UI, purple accent glow, bento cards, same card chrome.
3. Personality is still card-grid character sheet, not a living profile.
4. Mobile nav is a long top strip.
5. Icons via CSS filter invert — hacky.
6. Demo data mixed with real portrait facts — mark clearly when critiquing content vs chrome.

## Constraints for redesign proposals
- Read-only UI; SoT stays in Markdown elsewhere
- No fake XP / personality levels / invented KPIs
- Prefer fewer dependencies (vanilla or minimal)
- Keep epistemic marks: fact / intent / hypothesis / open question

## What to attack
Visual hierarchy, composition, signature “universe”, motion quality, typography, uniqueness vs Linear/WHOOP clones. Propose concrete CSS/JS changes or a redesign direction Cursor can implement.
