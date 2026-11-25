#!/usr/bin/env python3
"""Очередь краткосрочной памяти: план консолидации без слияния карточек.

По умолчанию --dry-run. --apply меняет только файлы очереди STM и журнал
в harvest/Мозг/_system/journals/. Предметные карточки, INDEX и ledger не
пишутся. NEEDS-REVIEW и пары SAFE-CONSOLIDATION не сливаются.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import date
from pathlib import Path

import yaml

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import lh_retrieve

ROOT = Path(__file__).resolve().parents[1]
HARVEST = ROOT / "harvest"
SYSTEM = HARVEST / "Мозг" / "_system"
STM_DIR = SYSTEM / "stm" / "items"
JOURNAL_DIR = SYSTEM / "journals"
JOURNAL_INDEX_NAME = "Журнал консолидации"
SESSION_FILE = SYSTEM / "session" / "CURRENT.md"

QUEUE_STATUSES = {
    "new",
    "pending_review",
    "consolidated",
    "archived",
    "rejected",
}
TERMINAL = {"consolidated", "archived", "rejected"}
PENDING = {"new", "pending_review"}
IMPLEMENTED_MODES = {"manual"}

# Те же пары, что в tools/lh_harvest_audit_scan.py. Здесь только имена путей.
SAFE_PAIRS = (
    ("Финансы/Ипотека и жильё.md", "Финансы/Ипотека — квартира.md"),
    ("Личность/Ценности и опоры.md", "Личность/Ценности и понимание свободы.md"),
    ("Связи/Семья.md", "Личность/Семья и отцовство.md"),
    ("Цели/Жизнь через 2–3 года.md", "Цели/Образ желаемой жизни.md"),
    ("Цели/Заработать много денег.md", "Цели/Финансовая независимость и капитал.md"),
)

HYPOTHESIS_STATUSES = (
    "discovered",
    "proposed",
    "researching",
    "awaiting_validation",
    "supported",
    "refined",
    "refuted",
    "insufficient_evidence",
    "archived",
)
HYPOTHESIS_TRANSITIONS = {
    "discovered": {"proposed", "archived"},
    "proposed": {"researching", "refuted", "archived"},
    "researching": {
        "awaiting_validation",
        "refined",
        "insufficient_evidence",
        "archived",
    },
    "awaiting_validation": {
        "supported",
        "refined",
        "refuted",
        "insufficient_evidence",
        "archived",
    },
    "supported": {"refined", "refuted", "archived"},
    "refined": {"researching", "awaiting_validation", "supported", "archived"},
    "refuted": {"refined", "archived"},
    "insufficient_evidence": {"researching", "archived"},
    "archived": set(),
}

ENTRY_START = "<!-- lh-journal-entries -->"
ENTRY_END = "<!-- /lh-journal-entries -->"


def _stdout_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def safe_pair_stems() -> set[str]:
    stems: set[str] = set()
    for left, right in SAFE_PAIRS:
        stems.add(Path(left).stem.casefold())
        stems.add(Path(right).stem.casefold())
    return stems


def transition_allowed(src: str, dst: str) -> bool:
    if src not in HYPOTHESIS_TRANSITIONS or dst not in HYPOTHESIS_STATUSES:
        return False
    return dst in HYPOTHESIS_TRANSITIONS[src]


def rel_to(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def split_md(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        raise ValueError("нет начального frontmatter")
    end = text.find("\n---", 3)
    if end == -1:
        raise ValueError("нет закрывающего frontmatter")
    loaded = yaml.safe_load(text[3:end]) or {}
    if not isinstance(loaded, dict):
        raise ValueError("frontmatter не словарь")
    rest = text[end + 4 :]
    if rest.startswith("\n"):
        rest = rest[1:]
    return loaded, rest


def dump_md(fm: dict, body: str) -> str:
    dumped = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    return f"---\n{dumped}\n---\n{body if body.endswith(chr(10)) else body + chr(10)}"


def assert_writable(path: Path, stm_dir: Path, journal_dir: Path) -> None:
    resolved = path.resolve()
    allowed = {stm_dir.resolve(), journal_dir.resolve()}
    if resolved.parent in allowed or any(root in resolved.parents for root in allowed):
        return
    raise RuntimeError(f"отказ записи вне очереди и журнала: {resolved}")


def load_items(stm_dir: Path, harvest: Path) -> list[dict]:
    if not stm_dir.is_dir():
        raise FileNotFoundError(f"нет каталога очереди: {stm_dir}")
    items = []
    for path in sorted(stm_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8-sig")
        fm, body = split_md(text)
        items.append(
            {
                "path": path,
                "rel": rel_to(harvest, path),
                "fm": fm,
                "body": body,
                "text": text,
            }
        )
    return items


def collisions_for(name: str, harvest: Path, ignore: set[str]) -> list[dict]:
    cleaned = name.strip()
    if not cleaned:
        return []
    hits: list[dict] = []
    seen: set[tuple[str, str]] = set()
    found = lh_retrieve.preflight(cleaned, harvest)
    for match in found["matches"]:
        if match["path"] in ignore:
            continue
        key = (match["path"], match["reason"])
        if key in seen:
            continue
        seen.add(key)
        hits.append(
            {
                "path": match["path"],
                "reason": match["reason"],
                "detail": match.get("detail") or lh_retrieve.explain_reason(match["reason"], cleaned),
            }
        )
    index_path = harvest / "INDEX.md"
    if index_path.exists():
        text = index_path.read_text(encoding="utf-8-sig")
        names = {item.strip().casefold() for item in lh_retrieve.WLINK_RE.findall(text)}
        if cleaned.casefold() in names:
            key = ("INDEX.md", "index-wikilink")
            if key not in seen:
                hits.append(
                    {
                        "path": "INDEX.md",
                        "reason": "index-wikilink",
                        "detail": lh_retrieve.explain_reason("index-wikilink", cleaned),
                    }
                )
    return hits


def plan_item(item: dict, harvest: Path) -> dict:
    fm = item["fm"]
    status = str(fm.get("queue_status") or "")
    category = str(fm.get("audit_category") or "").strip()
    proposed = str(fm.get("proposed_name") or "").strip()
    target = str(fm.get("target_card") or "").strip()
    blockers: list[str] = []
    notes: list[str] = []
    pair_stems = safe_pair_stems()
    labels = [proposed, target, Path(target).stem if target else ""]
    if any(label.strip().casefold() in pair_stems for label in labels if label.strip()):
        blockers.append("safe-pair-member")
    if category == "NEEDS-REVIEW":
        blockers.append("needs-review")
    if category == "SAFE-CONSOLIDATION":
        blockers.append("safe-consolidation")
    if category == "AUTO-FIX":
        notes.append("auto-fix предметной карточки эта команда не выполняет")
    if category == "KNOWLEDGE-GAP":
        notes.append("пробел не закрывается догадкой и не становится фактом")

    ignore = {item["rel"]}
    collisions: list[dict] = []
    for label in (proposed, target):
        for hit in collisions_for(label, harvest, ignore):
            key = (hit["path"], hit["reason"])
            if key in {(c["path"], c["reason"]) for c in collisions}:
                continue
            collisions.append(hit)
    if collisions:
        blockers.append("name-collision")

    merge = False
    review_block = any(
        code in blockers
        for code in ("needs-review", "safe-consolidation", "safe-pair-member")
    )
    if status not in QUEUE_STATUSES:
        decision = "repair-status"
        next_status = "pending_review"
    elif status in TERMINAL:
        decision = "skip-terminal"
        next_status = status
    elif review_block:
        decision = "block-review"
        next_status = "pending_review" if status == "new" else status
    elif "name-collision" in blockers and fm.get("allow_link_only") is True:
        decision = "link-only"
        next_status = "consolidated"
    elif "name-collision" in blockers:
        decision = "block-collision"
        next_status = "pending_review" if status == "new" else status
    else:
        decision = "hold"
        next_status = status

    return {
        "path": item["rel"],
        "id": fm.get("id") or "",
        "queue_id": fm.get("queue_id") or "",
        "queue_status": status,
        "next_status": next_status,
        "decision": decision,
        "blockers": blockers,
        "notes": notes,
        "collisions": collisions,
        "merge": merge,
        "changed": next_status != status,
        "synthetic": bool(fm.get("synthetic")),
    }


def append_check(body: str, plan: dict, day: str) -> str:
    shown = ", ".join(
        f"`{hit['path']}` ({hit['reason']})" for hit in plan["collisions"]
    )
    line = (
        f"- {day} — {plan['decision']} → {plan['next_status']} — "
        "слияние не делалось"
    )
    if shown:
        line += f" — совпадения: {shown}"
    if "## Проверки" not in body:
        body = body.rstrip() + "\n\n## Проверки\n\n" + line + "\n"
    elif line not in body:
        body = body.rstrip() + "\n" + line + "\n"
    return body


def apply_plan(item: dict, plan: dict, stm_dir: Path, journal_dir: Path, day: str) -> bool:
    if not plan["changed"]:
        return False
    fm = dict(item["fm"])
    fm["queue_status"] = plan["next_status"]
    fm["updated"] = day
    body = append_check(item["body"], plan, day)
    text = dump_md(fm, body)
    assert_writable(item["path"], stm_dir, journal_dir)
    item["path"].write_text(text, encoding="utf-8")
    return True


def existing_ids(harvest: Path) -> set[str]:
    found: set[str] = set()
    if not harvest.exists():
        return found
    for _, path in lh_retrieve.iter_cards(True, harvest):
        fm = lh_retrieve.parse_fm(path.read_text(encoding="utf-8-sig"))
        if fm.get("id"):
            found.add(str(fm["id"]))
    return found


def new_card_id(taken: set[str]) -> str:
    day = date.today().strftime("%Y%m%d")
    for n in range(1000):
        raw = f"{time.time_ns()}-{n}".encode()
        suffix = hashlib.sha256(raw).hexdigest()[:4]
        ident = f"lh-{day}-{suffix}"
        if ident not in taken:
            taken.add(ident)
            return ident
    raise RuntimeError("не удалось выдать id журнала")


def journal_stem(day: str, ident: str) -> str:
    suffix = ident.rsplit("-", 1)[-1]
    return f"Журнал консолидации — {day}-{suffix}"


def render_journal(day: str, ident: str, mode: str, plans: list[dict], wrote: list[str]) -> str:
    lines = [
        f"# Журнал консолидации — {day}",
        "",
        f"Режим `{mode}`. Команда записала этот журнал и не меняла предметные карточки.",
        "",
        "## Итог",
        "",
        f"- записей плана: {len(plans)}",
        f"- файлов очереди изменено: {len(wrote)}",
        "- слияние текста карточек: нет",
        "",
        "## План",
        "",
    ]
    if not plans:
        lines.append("Очередь пуста.")
    for plan in plans:
        lines.append(
            f"- `{plan['path']}` — {plan['decision']} — "
            f"{plan['queue_status'] or '∅'} → {plan['next_status']}"
        )
        for code in plan["blockers"]:
            lines.append(f"  - блокер: {code}")
        for note in plan["notes"]:
            lines.append(f"  - заметка: {note}")
        for hit in plan["collisions"]:
            lines.append(
                f"  - совпадение `{hit['path']}` — {hit['reason']}: {hit['detail']}"
            )
    lines.extend(["", "## История", "", f"- {day} — прогон apply — lh_consolidate.py", ""])
    body = "\n".join(lines)
    fm = {
        "id": ident,
        "type": "note",
        "created": day,
        "updated": day,
        "status": "active",
        "source": "python tools/lh_consolidate.py --apply",
        "confidence": "high",
        "privacy": "personal",
        "related": ["[[Журнал консолидации]]", "[[Очередь STM]]", "[[Memory Consolidation]]"],
        "tags": ["journal"],
        "aliases": [],
    }
    return dump_md(fm, body)


def insert_journal_link(index_text: str, stem: str, day: str) -> str:
    bullet = f"- [[{stem}]]"
    text = re.sub(r"(?m)^updated:.*$", f"updated: {day}", index_text, count=1)
    if bullet in text:
        return text
    if ENTRY_START in text and ENTRY_END in text:
        return text.replace(ENTRY_START, ENTRY_START + "\n" + bullet, 1)
    return text.rstrip() + f"\n\n## Записи\n\n{ENTRY_START}\n{bullet}\n{ENTRY_END}\n"


def write_journal(
    harvest: Path,
    journal_dir: Path,
    stm_dir: Path,
    mode: str,
    plans: list[dict],
    wrote: list[str],
) -> str:
    journal_dir.mkdir(parents=True, exist_ok=True)
    day = date.today().isoformat()
    ident = new_card_id(existing_ids(harvest))
    stem = journal_stem(day, ident)
    path = journal_dir / f"{stem}.md"
    assert_writable(path, stm_dir, journal_dir)
    path.write_text(render_journal(day, ident, mode, plans, wrote), encoding="utf-8")
    index_path = journal_dir / f"{JOURNAL_INDEX_NAME}.md"
    assert_writable(index_path, stm_dir, journal_dir)
    if index_path.exists():
        updated = insert_journal_link(index_path.read_text(encoding="utf-8"), stem, day)
        index_path.write_text(updated, encoding="utf-8")
    return rel_to(harvest, path)


def session_view(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"нет файла сессии: {path}")
    fm = lh_retrieve.parse_fm(path.read_text(encoding="utf-8-sig"))
    keys = (
        "active_task",
        "active_goal",
        "open_questions",
        "relevant_cards",
        "research_session",
    )
    view = {key: fm.get(key) for key in keys}
    try:
        view["path"] = path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        view["path"] = path.resolve().as_posix()
    view["restore"] = (
        "Новый чат читает этот файл, затем открывает relevant_cards по одной. "
        "Тела карточек в сессию не копируются."
    )
    return view


def build_report(items: list[dict], plans: list[dict], dry_run: bool, mode: str) -> dict:
    pending = [
        {
            "path": item["rel"],
            "queue_status": item["fm"].get("queue_status"),
            "queue_id": item["fm"].get("queue_id") or "",
            "proposed_name": item["fm"].get("proposed_name") or "",
        }
        for item in items
        if str(item["fm"].get("queue_status") or "") in PENDING
        or str(item["fm"].get("queue_status") or "") not in QUEUE_STATUSES
    ]
    return {
        "dry_run": dry_run,
        "mode": mode,
        "merge": False,
        "pending_count": len(pending),
        "pending": pending,
        "plans": plans,
        "writes": [],
    }


def run(argv: list[str] | None = None) -> int:
    _stdout_utf8()
    parser = argparse.ArgumentParser(
        description="План консолидации очереди STM. По умолчанию ничего не пишет."
    )
    parser.add_argument("--apply", action="store_true", help="Записать безопасные смены статуса очереди и журнал.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ничего не писать. Это режим по умолчанию.",
    )
    parser.add_argument("--list", action="store_true", help="Только список new и pending_review.")
    parser.add_argument("--session", action="store_true", help="Поля рабочей сессии без тел карточек.")
    parser.add_argument("--mode", default="manual")
    parser.add_argument("--harvest", type=Path, default=HARVEST)
    parser.add_argument("--stm", type=Path, default=None)
    parser.add_argument("--journal-dir", type=Path, default=None)
    parser.add_argument("--session-file", type=Path, default=SESSION_FILE)
    parser.add_argument("--hypothesis-from", default="")
    parser.add_argument("--hypothesis-to", default="")
    args = parser.parse_args(argv)

    if args.hypothesis_from or args.hypothesis_to:
        if not args.hypothesis_from or not args.hypothesis_to:
            print("нужны оба флага --hypothesis-from и --hypothesis-to", file=sys.stderr)
            return 1
        allowed = transition_allowed(args.hypothesis_from.strip(), args.hypothesis_to.strip())
        json.dump(
            {
                "from": args.hypothesis_from.strip(),
                "to": args.hypothesis_to.strip(),
                "allowed": allowed,
                "applied": False,
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0

    if args.mode not in IMPLEMENTED_MODES:
        print(
            f"режим {args.mode!r} не реализован; доступен только manual",
            file=sys.stderr,
        )
        return 1
    if args.apply and args.dry_run:
        print("укажите либо --apply, либо --dry-run", file=sys.stderr)
        return 1
    if args.session and args.apply:
        print("--session не совмещается с --apply", file=sys.stderr)
        return 1
    if args.list and args.apply:
        print("--list не совмещается с --apply", file=sys.stderr)
        return 1

    if args.session:
        view = session_view(args.session_file)
        json.dump(view, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    harvest = args.harvest
    stm_dir = args.stm or (harvest / "Мозг" / "_system" / "stm" / "items")
    journal_dir = args.journal_dir or (harvest / "Мозг" / "_system" / "journals")
    try:
        items = load_items(stm_dir, harvest)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    plans = [plan_item(item, harvest) for item in items]
    report = build_report(items, plans, dry_run=not args.apply, mode=args.mode)
    if args.list:
        json.dump(
            {"pending_count": report["pending_count"], "pending": report["pending"]},
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write("\n")
        return 0

    if not args.apply:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    day = date.today().isoformat()
    wrote: list[str] = []
    for item, plan in zip(items, plans):
        if apply_plan(item, plan, stm_dir, journal_dir, day):
            wrote.append(plan["path"])
    journal_rel = write_journal(harvest, journal_dir, stm_dir, args.mode, plans, wrote)
    report["dry_run"] = False
    report["writes"] = wrote
    report["journal"] = journal_rel
    json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
