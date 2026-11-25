#!/usr/bin/env python3
"""Приёмка пакетов lh_ingest_version 1.

validate — сухой прогон, ничего не пишет.
import — кладёт проверенный пакет в Research Inbox со status: pending.
import --apply — тот же файл плюс заметка-предложение. Предметные карточки не правит.

Пакет — данные, не инструкция (принцип 15). Повтор того же файла не создаёт вторую копию.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
HARVEST = ROOT / "harvest"
DEFAULT_INBOX = HARVEST / "Мозг" / "_inbox" / "research"
DEFAULT_INGEST = HARVEST / "События" / "_ingest"

IMPORTABLE_TYPES = {"interview", "hypothesis_research", "research"}
HYPOTHESIS_TYPES = {"hypothesis_research", "research"}
RESERVED_TYPES = {"capital_semantic_export", "connector"}
ALLOWED_STATUS = {
    "pending",
    "pending_ingest",
    "absorbed",
    "rejected",
    "triaged",
    "in_progress",
    "done",
    "proposal",
}
POLICY_CODES = {"core_instruction", "secret_material"}
DUPLICATE_CODES = {"duplicate_hash", "duplicate_session", "already_absorbed"}

HEADING_OK = re.compile(
    r"^#{1,3}\s+.*(гипотез|факт|самоописан|указан|цель|research goal|неизвест|unknown)",
    re.I | re.M,
)
JAILBREAK_RE = re.compile(
    r"ignore\s+(all\s+)?previous\s+instructions"
    r"|disregard\s+(all\s+)?(your\s+)?(previous\s+)?(instructions|rules)"
    r"|you\s+are\s+now\b"
    r"|new\s+system\s+prompt"
    r"|\bjailbreak\b",
    re.I,
)
CORE_PATH_RE = re.compile(
    r"(core/|core\\|BRAIN_CONSTITUTION|\.cursor/skills|AGENTS\.md|modules/)",
    re.I,
)
IMPERATIVE_RE = re.compile(
    r"(edit|modify|change|rewrite|overwrite|update|patch|delete|"
    r"правь|править|измени|изменить|изменяй|перепиши|обнови|удали|замени|"
    r"исполни|выполни|please\s+update)",
    re.I,
)
DENIAL_RE = re.compile(
    r"(?i)(^|[\s«\"'(\[])(не|нельзя|запрещено|запрещается|do\s+not|don't|never|must\s+not)\b"
)
SECRET_RE = re.compile(
    r"(?i)\b(password|passwd|api[_-]?key|secret_key|access_token|seed\s*phrase)\b\s*[:=]\s*\S{6,}"
)
MAX_CHARS = 200_000


def _stdout_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def normalize_text(text: str) -> str:
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def fingerprint(text: str) -> str:
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def body_checksum(body: str) -> str:
    normalized = body.replace("\r\n", "\n").replace("\r", "\n").strip("\n") + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def split_frontmatter(text: str) -> tuple[dict | None, str, str | None]:
    raw = text.lstrip("\ufeff")
    if not raw.startswith("---"):
        return None, raw, "missing_frontmatter"
    lines = raw.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return None, raw, "missing_frontmatter"
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, raw, "bad_frontmatter"
    block = "".join(lines[1:end])
    body = "".join(lines[end + 1 :])
    try:
        loaded = yaml.safe_load(block)
    except yaml.YAMLError:
        return None, body, "bad_frontmatter"
    if loaded is None:
        loaded = {}
    if not isinstance(loaded, dict):
        return None, body, "bad_frontmatter"
    return loaded, body, None


def _version_ok(value) -> bool:
    return value == 1 or value == "1"


def _targets(fm: dict) -> list:
    value = fm.get("targets")
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return []


def policy_hits(text: str) -> list[dict]:
    hits: list[dict] = []
    if JAILBREAK_RE.search(text):
        hits.append(
            {
                "code": "core_instruction",
                "message": "Пакет содержит смену инструкций. Он не исполняется и не кладётся в очередь.",
            }
        )
    for line in text.splitlines():
        if DENIAL_RE.search(line):
            continue
        if CORE_PATH_RE.search(line) and IMPERATIVE_RE.search(line):
            hits.append(
                {
                    "code": "core_instruction",
                    "message": "Пакет просит изменить core, skills, modules или конституцию.",
                }
            )
            break
    if SECRET_RE.search(text):
        hits.append(
            {
                "code": "secret_material",
                "message": "В пакете похоже на секрет. В очередь он не пишется.",
            }
        )
    return hits


def validate_package(text: str) -> dict:
    errors: list[dict] = []
    warnings: list[dict] = []
    fm, body, fm_error = split_frontmatter(text)
    sha = fingerprint(text)
    result = {
        "ok": False,
        "lh_ingest_version": None,
        "type": None,
        "sha256": sha,
        "session_id": "",
        "status": "",
        "errors": errors,
        "warnings": warnings,
        "frontmatter": fm or {},
        "body": body,
    }
    if len(text) > MAX_CHARS:
        errors.append({"code": "too_large", "message": "Пакет больше допустимого размера."})
        return result
    if fm_error:
        errors.append({"code": fm_error, "message": "Нет корректного YAML frontmatter."})
        return result
    assert fm is not None
    if not _version_ok(fm.get("lh_ingest_version")):
        errors.append(
            {
                "code": "bad_version",
                "message": "Поддерживается только lh_ingest_version: 1.",
            }
        )
    else:
        result["lh_ingest_version"] = 1
    pkg_type = str(fm.get("type") or "")
    result["type"] = pkg_type or None
    if pkg_type in RESERVED_TYPES:
        errors.append(
            {
                "code": "reserved_not_implemented",
                "message": f"Тип {pkg_type} зарезервирован и этим CLI не принимается.",
            }
        )
    elif pkg_type not in IMPORTABLE_TYPES:
        errors.append({"code": "bad_type", "message": "Тип пакета не из контракта v1."})
    if pkg_type == "research":
        warnings.append({"code": "type_alias", "message": "type: research принят как hypothesis_research."})
    status = fm.get("status")
    result["status"] = str(status or "")
    if status is None:
        warnings.append({"code": "status_missing", "message": "Нет status. Для нового пакета ожидается pending_ingest."})
    elif not isinstance(status, str) or status not in ALLOWED_STATUS:
        errors.append({"code": "bad_status", "message": "status вне словаря пакета."})
    elif status == "rejected":
        errors.append({"code": "status_rejected", "message": "Пакет уже помечен rejected."})
    session_id = str(fm.get("session_id") or "").strip()
    result["session_id"] = session_id
    if pkg_type in HYPOTHESIS_TYPES and not _targets(fm):
        errors.append({"code": "missing_targets", "message": "Для hypothesis_research нужен непустой targets."})
    if pkg_type in HYPOTHESIS_TYPES and not HEADING_OK.search(body):
        errors.append(
            {
                "code": "missing_section",
                "message": "Нужна секция цели, фактов, гипотез или указаний для импорта.",
            }
        )
    if not body.strip():
        errors.append({"code": "empty_body", "message": "Пустое тело пакета."})
    checksum = fm.get("checksum")
    if checksum not in (None, ""):
        expected = body_checksum(body)
        if str(checksum).lower() != expected:
            errors.append({"code": "checksum_mismatch", "message": "checksum не совпал с телом пакета."})
    errors.extend(policy_hits(text))
    result["ok"] = not errors
    return result


def _iter_md(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    skip_names = {"README.md", "INDEX.md", "Research Inbox.md", "Research Inbox Queue.md"}
    found: list[Path] = []
    for path in folder.rglob("*.md"):
        if path.name.startswith("_") or path.name in skip_names:
            continue
        if "proposals" in path.parts and path.parent.name == "proposals":
            continue
        found.append(path)
    return found


def load_log(inbox: Path) -> dict:
    path = inbox / "_import-log.yaml"
    if not path.exists():
        return {"version": 1, "entries": []}
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        return {"version": 1, "entries": []}
    entries = loaded.get("entries") or []
    if not isinstance(entries, list):
        entries = []
    return {"version": 1, "entries": entries}


def find_duplicates(text: str, report: dict, inbox: Path, scan_dirs: list[Path]) -> list[dict]:
    hits: list[dict] = []
    sha = report["sha256"]
    session_id = report.get("session_id") or ""
    status = report.get("status") or ""
    if status == "absorbed":
        hits.append({"code": "already_absorbed", "message": "Пакет уже помечен absorbed."})
    log = load_log(inbox)
    for entry in log["entries"]:
        if not isinstance(entry, dict):
            continue
        if entry.get("sha256") == sha:
            hits.append({"code": "duplicate_hash", "message": "Такой пакет уже есть в журнале приёмки."})
        elif session_id and entry.get("session_id") == session_id:
            hits.append({"code": "duplicate_session", "message": "session_id уже принимался."})
    seen_codes = {item["code"] for item in hits}
    folders = [inbox, *scan_dirs]
    checked: set[Path] = set()
    for folder in folders:
        for path in _iter_md(folder):
            resolved = path.resolve()
            if resolved in checked:
                continue
            checked.add(resolved)
            try:
                existing = path.read_text(encoding="utf-8")
            except OSError:
                continue
            existing_fm, _, fm_error = split_frontmatter(existing)
            if fingerprint(existing) == sha and "duplicate_hash" not in seen_codes:
                hits.append({"code": "duplicate_hash", "message": f"Тот же текст уже лежит в {path.name}."})
                seen_codes.add("duplicate_hash")
            if not existing_fm or fm_error:
                continue
            if session_id and str(existing_fm.get("session_id") or "") == session_id and "duplicate_session" not in seen_codes:
                hits.append({"code": "duplicate_session", "message": f"session_id уже есть в {path.name}."})
                seen_codes.add("duplicate_session")
            if str(existing_fm.get("source_sha256") or "") == sha and "duplicate_hash" not in seen_codes:
                hits.append({"code": "duplicate_hash", "message": f"Отпечаток уже есть в {path.name}."})
                seen_codes.add("duplicate_hash")
    return hits


def _safe_stem(name: str) -> str:
    stem = Path(name).stem
    stem = re.sub(r"[^\w.\-]+", "-", stem, flags=re.UNICODE)
    stem = stem.strip(".-") or "package"
    return stem[:80]


def _dump_package(fm: dict, body: str) -> str:
    dumped = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
    payload = body if body.startswith("\n") else "\n" + body
    if not payload.endswith("\n"):
        payload += "\n"
    return f"---\n{dumped}\n---{payload}"


def _quote_excerpt(body: str, limit: int = 4000) -> str:
    text = body.strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "\n…"
    return text


def render_index(inbox: Path) -> str:
    rows: list[str] = []
    pending = inbox / "pending"
    if pending.exists():
        for path in sorted(pending.glob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            fm, _, err = split_frontmatter(path.read_text(encoding="utf-8"))
            if err or not fm:
                continue
            rel = path.relative_to(inbox).as_posix()
            rows.append(
                "| {status} | {path} | {typ} | {session} | {filed} |".format(
                    status=str(fm.get("status") or ""),
                    path=rel,
                    typ=str(fm.get("type") or ""),
                    session=str(fm.get("session_id") or ""),
                    filed=str(fm.get("filed_at") or ""),
                )
            )
    proposal_rows: list[str] = []
    proposals = inbox / "proposals"
    if proposals.exists():
        for path in sorted(proposals.glob("*.md")):
            if path.name.lower() == "readme.md":
                continue
            fm, _, err = split_frontmatter(path.read_text(encoding="utf-8"))
            if err or not fm:
                continue
            rel = path.relative_to(inbox).as_posix()
            proposal_rows.append(
                "| {status} | {path} | {src} | {applied} |".format(
                    status=str(fm.get("status") or "proposal"),
                    path=rel,
                    src=str(fm.get("source_package") or ""),
                    applied=str(fm.get("auto_applied")),
                )
            )
    queue = "\n".join(rows) if rows else "|  |  |  |  | очередь пуста |"
    proposal_table = "\n".join(proposal_rows) if proposal_rows else "|  |  |  | нет предложений |"
    today = date.today().isoformat()
    return (
        "---\n"
        "type: note\n"
        "status: актуально\n"
        f"updated: {today}\n"
        'source: "tools/lh_ingest.py"\n'
        "tags: [integration]\n"
        "aliases: [Очередь Research Inbox]\n"
        "---\n\n"
        "# INDEX — очередь исследований\n\n"
        "Сюда `lh_ingest.py import` пишет только проверенные пакеты. "
        "Предметные карточки из этой очереди сами не меняются.\n\n"
        "## Очередь\n\n"
        "| status | path | type | session_id | filed_at |\n"
        "|---|---|---|---|---|\n"
        f"{queue}\n\n"
        "## Предложения\n\n"
        "`auto_applied: false` значит, что заметка только предлагает правку.\n\n"
        "| status | path | source_package | auto_applied |\n"
        "|---|---|---|---|\n"
        f"{proposal_table}\n"
    )


def write_index(inbox: Path) -> Path:
    inbox.mkdir(parents=True, exist_ok=True)
    path = inbox / "INDEX.md"
    path.write_text(render_index(inbox), encoding="utf-8")
    return path


def _append_log(inbox: Path, entry: dict) -> None:
    log = load_log(inbox)
    log["entries"].append(entry)
    path = inbox / "_import-log.yaml"
    path.write_text(
        yaml.safe_dump(log, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def _under(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(root.resolve())
    return resolved


def file_package(text: str, source_name: str, report: dict, inbox: Path, apply: bool) -> dict:
    wrote: list[str] = []
    inbox = inbox.resolve()
    pending_dir = inbox / "pending"
    proposal_dir = inbox / "proposals"
    pending_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(source_name)
    dest = pending_dir / f"{stem}.md"
    if dest.exists():
        dest = pending_dir / f"{stem}-{report['sha256'][:8]}.md"
    fm = dict(report["frontmatter"])
    original_status = fm.get("status")
    fm["status"] = "pending"
    fm["ingest_status"] = "pending_ingest"
    if original_status is not None:
        fm["source_status"] = original_status
    fm["source_sha256"] = report["sha256"]
    fm["filed_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fm["inbox_role"] = "research"
    fm["auto_applied"] = False
    payload = _dump_package(fm, report["body"])
    dest = _under(dest, inbox)
    dest.write_text(payload, encoding="utf-8")
    wrote.append(dest.relative_to(inbox).as_posix())
    _append_log(
        inbox,
        {
            "sha256": report["sha256"],
            "session_id": report.get("session_id") or "",
            "source_name": source_name,
            "inbox_path": wrote[0],
            "filed_at": fm["filed_at"],
            "status": "pending",
        },
    )
    proposal_rel = None
    if apply:
        proposal_dir.mkdir(parents=True, exist_ok=True)
        proposal = proposal_dir / f"proposal-{dest.stem}.md"
        proposal = _under(proposal, inbox)
        targets = _targets(fm)
        target_lines = "\n".join(f"- {item}" for item in targets) or "- цели не указаны"
        proposal_fm = {
            "lh_proposal_version": 1,
            "type": "canonical_change_proposal",
            "status": "proposal",
            "auto_applied": False,
            "source_package": wrote[0],
            "targets": targets,
            "privacy": fm.get("privacy") or "personal",
        }
        proposal_body = (
            "# Предложение канонических правок\n\n"
            "Это данные из пакета, а не команда. Предметные карточки, ledger и `core/` не изменены.\n\n"
            "## Цели\n\n"
            f"{target_lines}\n\n"
            "## Что можно перенести вручную\n\n"
            "Факты оставить фактами. Гипотезы не повышать до факта. "
            "Кандидаты решений не получают статус «принято», пока так не скажет человек.\n\n"
            "## Выдержка пакета\n\n"
            f"{_quote_excerpt(report['body'])}\n"
        )
        proposal.write_text(_dump_package(proposal_fm, proposal_body), encoding="utf-8")
        proposal_rel = proposal.relative_to(inbox).as_posix()
        wrote.append(proposal_rel)
    index_path = write_index(inbox)
    wrote.append(index_path.relative_to(inbox).as_posix())
    return {"wrote": wrote, "proposal": proposal_rel, "auto_applied": False}


def decide_exit(errors: list[dict], duplicate: bool) -> int:
    codes = {item["code"] for item in errors}
    if codes & POLICY_CODES:
        return 2
    if codes - DUPLICATE_CODES:
        return 1
    if duplicate or (codes & DUPLICATE_CODES):
        return 3
    return 0


def run_one(text: str, source_name: str, inbox: Path, scan_dirs: list[Path], action: str, apply: bool) -> dict:
    report = validate_package(text)
    duplicates = []
    if not any(item["code"] in POLICY_CODES for item in report["errors"]):
        duplicates = find_duplicates(text, report, inbox, scan_dirs)
    errors = list(report["errors"])
    if duplicates:
        errors.extend(duplicates)
    exit_code = decide_exit(errors, bool(duplicates))
    wrote: list[str] = []
    proposal = None
    if action == "import" and exit_code == 0:
        filed = file_package(text, source_name, report, inbox, apply)
        wrote = filed["wrote"]
        proposal = filed["proposal"]
    ok = exit_code == 0
    return {
        "ok": ok,
        "action": action,
        "apply": apply and action == "import",
        "exit_code": exit_code,
        "lh_ingest_version": report["lh_ingest_version"],
        "type": report["type"],
        "sha256": report["sha256"],
        "session_id": report.get("session_id") or "",
        "errors": errors,
        "warnings": report["warnings"],
        "duplicate": bool(duplicates),
        "wrote": wrote,
        "proposal": proposal,
        "auto_applied": False,
    }


def _emit(payload: dict) -> int:
    _stdout_utf8()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    code = int(payload["exit_code"])
    label = "ok" if code == 0 else "reject"
    print(f"lh_ingest: {label} {code}", file=sys.stderr)
    return code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Проверка и приёмка пакетов lh_ingest_version 1")
    sub = parser.add_subparsers(dest="action", required=True)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("package", type=Path, help="Markdown-пакет")
    common.add_argument("--inbox", type=Path, default=DEFAULT_INBOX, help="Каталог Research Inbox")
    common.add_argument("--scan", type=Path, action="append", default=None, help="Дополнительный каталог для поиска дубля")
    common.add_argument(
        "--no-default-scan",
        action="store_true",
        help="Не смотреть harvest/События/_ingest (для изолированного прогона)",
    )
    validate_p = sub.add_parser("validate", parents=[common], help="Сухой прогон, без записи")
    import_p = sub.add_parser("import", parents=[common], help="Положить проверенный пакет в очередь как pending")
    import_p.add_argument(
        "--apply",
        action="store_true",
        help="Кроме очереди записать предложение правок. Карточки не менять.",
    )
    index_p = sub.add_parser("index", help="Пересобрать INDEX.md очереди")
    index_p.add_argument("--inbox", type=Path, default=DEFAULT_INBOX)
    args = parser.parse_args(argv)

    if args.action == "index":
        path = write_index(args.inbox)
        return _emit(
            {
                "ok": True,
                "action": "index",
                "apply": False,
                "exit_code": 0,
                "lh_ingest_version": 1,
                "type": None,
                "sha256": "",
                "session_id": "",
                "errors": [],
                "warnings": [],
                "duplicate": False,
                "wrote": [str(path)],
                "proposal": None,
                "auto_applied": False,
            }
        )

    package = args.package
    if not package.is_file():
        return _emit(
            {
                "ok": False,
                "action": args.action,
                "apply": False,
                "exit_code": 1,
                "lh_ingest_version": None,
                "type": None,
                "sha256": "",
                "session_id": "",
                "errors": [{"code": "missing_file", "message": "Файл пакета не найден."}],
                "warnings": [],
                "duplicate": False,
                "wrote": [],
                "proposal": None,
                "auto_applied": False,
            }
        )
    text = package.read_text(encoding="utf-8")
    scan_dirs: list[Path] = list(args.scan or [])
    if not args.no_default_scan:
        scan_dirs.append(DEFAULT_INGEST)
    apply = bool(getattr(args, "apply", False))
    payload = run_one(text, package.name, args.inbox, scan_dirs, args.action, apply)
    return _emit(payload)


if __name__ == "__main__":
    raise SystemExit(main())
