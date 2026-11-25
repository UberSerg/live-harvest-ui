"""One-shot harvest markdown audit scanner (stdout JSON). Not for numbered vault."""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

try:
    from lh_contest_check import contest_findings
except ImportError:
    from tools.lh_contest_check import contest_findings

HARVEST = Path(__file__).resolve().parents[1] / "harvest"
REQUIRED = {"id", "type", "created", "updated", "status", "source", "confidence", "privacy"}
VALID_TYPES = {
    "person_profile",
    "idea",
    "project",
    "finance",
    "goal",
    "decision",
    "event",
    "relation",
    "note",
}
VALID_STATUS = {"draft", "active", "paused", "done", "cancelled", "superseded"}
VALID_CONF = {"high", "medium", "low", "unknown"}
VALID_PRIV = {"public", "personal", "sensitive", "secret"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^lh-\d{8}-[a-z0-9]{4}$")
WLINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]]+)?(?:\|[^\]]+)?\]\]")


def parse_fm(text: str):
    if not text.startswith("---"):
        return None, text
    end = text.find("---", 3)
    if end == -1:
        return None, text
    try:
        fm = yaml.safe_load(text[3:end]) or {}
    except Exception as e:
        return {"_parse_error": str(e)}, text[end + 3 :]
    return fm, text[end + 3 :]


def extract_wlinks(s: str) -> list[str]:
    return WLINK_RE.findall(s)


def main() -> int:
    md_files = [p for p in HARVEST.rglob("*.md") if ".obsidian" not in str(p)]
    name_to_path: dict[str, list[str]] = {}
    alias_to_path: dict[str, list[str]] = {}
    for p in md_files:
        stem = p.stem
        rel = str(p.relative_to(HARVEST)).replace("\\", "/")
        name_to_path.setdefault(stem, []).append(rel)
        text = p.read_text(encoding="utf-8-sig")
        fm, _ = parse_fm(text)
        if isinstance(fm, dict):
            for a in fm.get("aliases") or []:
                if a:
                    alias_to_path.setdefault(str(a), []).append(rel)

    names = set(name_to_path.keys()) | set(alias_to_path.keys())
    findings: list[dict] = []

    def add(cat: str, fid: str, path: str, title: str, detail: str = "") -> None:
        findings.append(
            {"id": fid, "category": cat, "path": path, "title": title, "detail": detail}
        )

    for stem, paths in name_to_path.items():
        if len(paths) > 1:
            add("NEEDS-REVIEW", f"dup-stem-{stem}", paths[0], stem, f"multiple paths: {paths}")

    ids_seen: dict[str, str] = {}
    for p in sorted(md_files):
        rel = str(p.relative_to(HARVEST)).replace("\\", "/")
        text = p.read_text(encoding="utf-8-sig")
        fm, body = parse_fm(text)
        if fm is None:
            add("AUTO-FIX", f"no-fm-{rel}", rel, p.stem, "missing frontmatter delimiter")
            continue
        if "_parse_error" in fm:
            add("NEEDS-REVIEW", f"yaml-{rel}", rel, p.stem, fm["_parse_error"])
            continue
        for k in REQUIRED:
            if k not in fm or fm[k] is None:
                add("AUTO-FIX", f"missing-{k}-{rel}", rel, p.stem, f"missing field {k}")
            elif k in ("created", "updated") and not DATE_RE.match(str(fm[k])):
                add("AUTO-FIX", f"bad-date-{k}-{rel}", rel, p.stem, f"bad {k}: {fm[k]}")
            elif k == "source" and fm[k] == "":
                add("KNOWLEDGE-GAP", f"empty-source-{rel}", rel, p.stem, "empty source string")
        if fm.get("id"):
            iid = str(fm["id"])
            if not ID_RE.match(iid):
                add("AUTO-FIX", f"bad-id-{rel}", rel, p.stem, f"id format: {iid}")
            if iid in ids_seen:
                add(
                    "NEEDS-REVIEW",
                    f"dup-id-{iid}",
                    rel,
                    p.stem,
                    f"duplicate of {ids_seen[iid]}",
                )
            else:
                ids_seen[iid] = rel
        if fm.get("type") not in VALID_TYPES:
            add("NEEDS-REVIEW", f"bad-type-{rel}", rel, p.stem, str(fm.get("type")))
        if fm.get("status") not in VALID_STATUS:
            add("AUTO-FIX", f"bad-status-{rel}", rel, p.stem, str(fm.get("status")))
        if fm.get("confidence") not in VALID_CONF:
            add("AUTO-FIX", f"bad-conf-{rel}", rel, p.stem, str(fm.get("confidence")))
        if fm.get("privacy") not in VALID_PRIV:
            add("AUTO-FIX", f"bad-priv-{rel}", rel, p.stem, str(fm.get("privacy")))

        for target in set(extract_wlinks(text)):
            t = target.strip()
            if t == "INDEX":
                continue
            if t not in names:
                add("AUTO-FIX", f"broken-link-{rel}-{t}", rel, p.stem, f"broken [[{t}]]")

    pairs = [
        ("Финансы/Ипотека и жильё.md", "Финансы/Ипотека — квартира.md"),
        ("Личность/Ценности и опоры.md", "Личность/Ценности и понимание свободы.md"),
        ("Связи/Семья.md", "Личность/Семья и отцовство.md"),
        ("Цели/Жизнь через 2–3 года.md", "Цели/Образ желаемой жизни.md"),
        ("Цели/Заработать много денег.md", "Цели/Финансовая независимость и капитал.md"),
    ]
    for a, b in pairs:
        pa, pb = HARVEST / a, HARVEST / b
        if pa.exists() and pb.exists():
            add(
                "SAFE-CONSOLIDATION",
                f"pair-{pa.stem}",
                a,
                f"{pa.stem} ↔ {pb.stem}",
                "intentional split; verify cross-links and single SoT per fact",
            )

    incoming: dict[str, set[str]] = defaultdict(set)
    for p in md_files:
        text = p.read_text(encoding="utf-8-sig")
        src = p.stem
        for t in extract_wlinks(text):
            incoming[t.strip()].add(src)

    skip_orphan_names = {
        "INDEX",
        "README",
        "AUDIT",
        "SCHEMA",
        "MIGRATION-SQLITE",
    }
    for p in md_files:
        rel = str(p.relative_to(HARVEST)).replace("\\", "/")
        stem = p.stem
        if stem in skip_orphan_names or "_overview" in p.name or "_ingest" in rel:
            continue
        if p.name in ("README.md", "AUDIT.md", "SCHEMA.md", "MIGRATION-SQLITE.md"):
            continue
        if len(incoming.get(stem, set())) == 0:
            add("KNOWLEDGE-GAP", f"orphan-{stem}", rel, stem, "no incoming wikilinks from other cards")

    for p in HARVEST.glob("Решения/*.md"):
        if "_overview" in p.name:
            continue
        text = p.read_text(encoding="utf-8-sig")
        fm, _ = parse_fm(text)
        if fm and fm.get("status") == "active":
            low = text.lower()
            if "принято" not in low and "## итог" not in low and "## результат" not in low:
                rel = str(p.relative_to(HARVEST)).replace("\\", "/")
                add(
                    "KNOWLEDGE-GAP",
                    f"dec-outcome-{p.stem}",
                    rel,
                    p.stem,
                    "active decision without explicit outcome/принято marker",
                )

    # Stale updated vs created only on finance snapshots
    for p in md_files:
        rel = str(p.relative_to(HARVEST)).replace("\\", "/")
        if not rel.startswith("Финансы/") or "Капитал" in rel:
            continue
        fm, _ = parse_fm(p.read_text(encoding="utf-8"))
        if not fm or "_parse_error" in fm:
            continue
        if "срез" in p.read_text(encoding="utf-8").lower() and fm.get("updated") == "2026-11-24":
            if "2026-10" in p.read_text(encoding="utf-8"):
                add(
                    "NEEDS-REVIEW",
                    f"stale-{p.stem}",
                    rel,
                    p.stem,
                    "dated snapshot body; verify updated field",
                )

    for p in sorted(md_files):
        rel = str(p.relative_to(HARVEST)).replace("\\", "/")
        for item in contest_findings(p.read_text(encoding="utf-8-sig"), rel):
            add("CONTEST", item["id"], rel, item["title"], item["detail"])

    counts = defaultdict(int)
    for f in findings:
        counts[f["category"]] += 1

    out = {"counts": dict(counts), "total": len(findings), "findings": findings}
    json.dump(out, sys.stdout, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())