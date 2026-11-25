#!/usr/bin/env python3
"""Эксперимент: списки хода и запись результата.

Бланк harvest/Мозг/_system/templates/Шаблон эксперимента.md команда не меняет
и в списки не включает. Текст результата берётся только из аргументов.
record-result дописывает секции и историю и не стирает уже написанные абзацы.
Наблюдения и связь с целью команда не заполняет.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
HARVEST = ROOT / "harvest"

TEMPLATE_RELS = frozenset({"Мозг/_system/templates/Шаблон эксперимента.md"})
ACTIVE = {"planned", "running"}
PENDING = {"pending_review"}
CONTINUE_STATUS = {"yes": "running", "no": "stopped"}
CONTINUE_WORD = {"yes": "continue", "no": "stop"}

HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
SCALAR_LINE = re.compile(r"^([A-Za-z0-9_]+):[ \t]*(.*)$")
BLOCK_TOKENS = {"|", ">", "|-", ">-", "|+", ">+"}
BARE_KEYS = {"experiment_status", "continue_choice"}


class ExperimentWriteError(ValueError):
    """Отказ записи: файл не тот или правка сломала бы уже записанный YAML."""


def read_markdown(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_document(text: str) -> tuple[dict, str, str]:
    if not text.startswith("---"):
        raise ExperimentWriteError("нет frontmatter")
    end = text.find("\n---", 3)
    if end == -1:
        raise ExperimentWriteError("нет закрывающего frontmatter")
    inner = text[4:end]
    loaded = yaml.safe_load(inner) or {}
    if not isinstance(loaded, dict):
        raise ExperimentWriteError("frontmatter не словарь")
    body = text[end + 4 :]
    return loaded, body, inner


def join_document(inner: str, body: str) -> str:
    if not inner.endswith("\n"):
        inner += "\n"
    if not body.startswith("\n"):
        body = "\n" + body
    if not body.endswith("\n"):
        body += "\n"
    return f"---\n{inner}---{body}"


def harvest_rel(path: Path, harvest: Path) -> str | None:
    try:
        return path.resolve().relative_to(harvest.resolve()).as_posix()
    except ValueError:
        return None


def section_span(body: str, title: str) -> tuple[int, int, int] | None:
    matches = list(HEADING_RE.finditer(body))
    for index, match in enumerate(matches):
        if match.group(1).strip() != title:
            continue
        content_start = match.end()
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        return match.start(), content_start, content_end
    return None


def section_text(body: str, title: str) -> str | None:
    span = section_span(body, title)
    if span is None:
        return None
    return body[span[1] : span[2]]


def section_has_substance(text: str | None) -> bool:
    if text is None:
        return False
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.casefold().startswith("пусто"):
            continue
        return True
    return False


def field_empty(fm_value: object, section: str | None) -> bool:
    if isinstance(fm_value, str) and fm_value.strip():
        return False
    if fm_value not in (None, "") and not isinstance(fm_value, str):
        return False
    return not section_has_substance(section)


def parse_day(value: object) -> date | None:
    if value is None or value is False:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip().strip("\"'")
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def format_pair(key: str, value: str) -> str:
    if value == "":
        return f'{key}: ""'
    if key in BARE_KEYS and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        return f"{key}: {value}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return f"{key}: {value}"
    return f"{key}: {json.dumps(value, ensure_ascii=False)}"


def parse_scalar_token(key: str, token: str) -> str:
    if token.strip() in BLOCK_TOKENS:
        raise ExperimentWriteError(f"{key}: блочный YAML, команда его не переписывает")
    if token.strip() == "":
        return ""
    loaded = yaml.safe_load(token)
    if loaded is None:
        return ""
    if isinstance(loaded, date) and not isinstance(loaded, datetime):
        return loaded.isoformat()
    if isinstance(loaded, datetime):
        return loaded.date().isoformat()
    if isinstance(loaded, bool):
        return "yes" if loaded else "no"
    if not isinstance(loaded, str):
        return str(loaded)
    return loaded


def set_scalar(inner: str, key: str, value: str) -> str:
    formatted = format_pair(key, value)
    lines = inner.split("\n")
    for index, line in enumerate(lines):
        match = SCALAR_LINE.match(line)
        if not match or match.group(1) != key:
            continue
        lines[index] = formatted
        return "\n".join(lines)
    if lines and lines[-1] == "":
        lines.insert(len(lines) - 1, formatted)
    else:
        lines.append(formatted)
    return "\n".join(lines)


def read_scalar(inner: str, key: str) -> str | None:
    for line in inner.split("\n"):
        match = SCALAR_LINE.match(line)
        if match and match.group(1) == key:
            return parse_scalar_token(key, match.group(2))
    return None


def append_paragraph(body: str, title: str, text: str) -> str:
    addition = text.strip()
    if not addition:
        raise ExperimentWriteError(f"пустой текст секции «{title}»")
    span = section_span(body, title)
    block = f"## {title}\n\n{addition}\n"
    if span is None:
        history = section_span(body, "История")
        piece = block + "\n"
        if history is None:
            return body.rstrip() + "\n\n" + piece
        return body[: history[0]] + piece + body[history[0] :]
    _heading, content_start, content_end = span
    content = body[content_start:content_end]
    if content.strip():
        new_content = content.rstrip() + "\n\n" + addition + "\n\n"
    else:
        new_content = f"\n\n{addition}\n\n"
    return body[:content_start] + new_content + body[content_end:]


def append_history(body: str, line: str) -> str:
    bullet = f"- {one_line(line)}"
    span = section_span(body, "История")
    if span is None:
        return body.rstrip() + f"\n\n## История\n\n{bullet}\n"
    _heading, content_start, content_end = span
    content = body[content_start:content_end]
    new_content = content.rstrip() + "\n" + bullet + "\n\n"
    return body[:content_start] + new_content + body[content_end:]


def looks_like_experiment(text: str, rel: str | None) -> bool:
    if rel in TEMPLATE_RELS:
        return True
    if not text.startswith("---"):
        return False
    end = text.find("\n---", 3)
    head = text if end < 0 else text[:end]
    return "experiment_status:" in head


def classify(path: Path, harvest: Path, today: date) -> dict | None:
    rel = harvest_rel(path, harvest)
    if rel is None:
        return None
    text = read_markdown(path)
    if not looks_like_experiment(text, rel):
        return None
    try:
        fm, body, _inner = split_document(text)
    except ExperimentWriteError as exc:
        return {"kind": "error", "path": rel, "detail": str(exc)}
    except yaml.YAMLError as exc:
        return {"kind": "error", "path": rel, "detail": str(exc).splitlines()[0]}
    if rel in TEMPLATE_RELS:
        return {"kind": "template", "path": rel, "reason": "template-blank"}
    if "experiment_status" not in fm:
        return None
    status = fm.get("experiment_status")
    status_text = status.strip() if isinstance(status, str) else "" if status is None else str(status).strip()
    status_key = status_text.casefold()
    observations_empty = field_empty(fm.get("observations"), section_text(body, "Наблюдения"))
    result_empty = field_empty(fm.get("actual_result"), section_text(body, "Фактический результат"))
    review = parse_day(fm.get("review_date"))
    if status_key in ACTIVE:
        kind = "active"
    elif status_key in PENDING:
        kind = "pending"
    else:
        return None
    return {
        "kind": kind,
        "path": rel,
        "experiment_status": status_text,
        "review_date": review.isoformat() if review else "",
        "due": bool(review and review <= today),
        "observations_empty": observations_empty,
        "result_empty": result_empty,
        "synthetic": fm.get("synthetic") is True,
        "reason": f"experiment_status {status_text}",
    }


def _scan(root: Path | None, today: date) -> tuple[list[dict], list[dict], int, list[dict]]:
    harvest = (root or HARVEST).resolve()
    if not harvest.is_dir():
        raise ExperimentWriteError(f"нет каталога: {harvest}")
    active: list[dict] = []
    pending: list[dict] = []
    template_skipped = 0
    errors: list[dict] = []
    for path in sorted(harvest.rglob("*.md")):
        row = classify(path, harvest, today)
        if row is None:
            continue
        kind = row.get("kind")
        if kind == "error":
            errors.append({"path": row["path"], "detail": row.get("detail", "")})
        elif kind == "template":
            template_skipped += 1
        elif kind == "active":
            active.append(row)
        elif kind == "pending":
            pending.append(row)
    active.sort(key=lambda item: item["path"])
    pending.sort(key=lambda item: item["path"])
    return active, pending, template_skipped, errors


def _public_row(row: dict) -> dict:
    return {
        "path": row["path"],
        "experiment_status": row["experiment_status"],
        "review_date": row["review_date"],
        "due": row["due"],
        "observations_empty": row["observations_empty"],
        "result_empty": row["result_empty"],
        "synthetic": row["synthetic"],
        "reason": row["reason"],
    }


def list_active(
    root: Path | None = None,
    *,
    today: date | None = None,
    due_only: bool = False,
) -> dict:
    current = today or date.today()
    active, _pending, template_skipped, errors = _scan(root, current)
    rows = [_public_row(item) for item in active if not due_only or item["due"]]
    return {
        "ok": not errors,
        "today": current.isoformat(),
        "due_only": due_only,
        "active": rows,
        "template_skipped": template_skipped,
        "errors": errors,
    }


def list_pending(
    root: Path | None = None,
    *,
    today: date | None = None,
    due_only: bool = False,
) -> dict:
    current = today or date.today()
    _active, pending, template_skipped, errors = _scan(root, current)
    rows = [_public_row(item) for item in pending if not due_only or item["due"]]
    return {
        "ok": not errors,
        "today": current.isoformat(),
        "due_only": due_only,
        "pending": rows,
        "template_skipped": template_skipped,
        "errors": errors,
    }


def record_result(
    path: Path,
    result: str,
    continue_choice: str,
    *,
    when: date | None = None,
    source: str = "CLI lh_experiments.py record-result",
    harvest: Path | None = None,
) -> dict:
    result_text = result.strip()
    choice = continue_choice.strip().casefold()
    if not result_text:
        raise ExperimentWriteError("нужен непустой result")
    if choice not in CONTINUE_STATUS:
        raise ExperimentWriteError("continue: yes или no")
    target = path.resolve()
    if not target.is_file():
        raise ExperimentWriteError(f"нет файла: {target}")
    root = (harvest or HARVEST).resolve()
    rel = harvest_rel(target, root)
    if rel in TEMPLATE_RELS:
        raise ExperimentWriteError("бланк эксперимента эта команда не меняет")
    original = read_markdown(target)
    fm, body, inner = split_document(original)
    if "experiment_status" not in fm:
        raise ExperimentWriteError("файл без experiment_status")
    current = when or date.today()
    iso = current.isoformat()
    previous = read_scalar(inner, "experiment_status") or ""
    previous_result = read_scalar(inner, "actual_result") or ""
    next_status = CONTINUE_STATUS[choice]
    next_result = result_text if not previous_result.strip() else previous_result.rstrip() + "\n" + result_text
    word = CONTINUE_WORD[choice]
    inner = set_scalar(inner, "actual_result", next_result)
    inner = set_scalar(inner, "continue_choice", word)
    inner = set_scalar(inner, "experiment_status", next_status)
    inner = set_scalar(inner, "updated", iso)
    body = append_paragraph(body, "Фактический результат", result_text)
    body = append_paragraph(body, "Продолжать / остановить", word)
    history = (
        f"{iso} — experiment_status {previous or 'пусто'} → {next_status} — "
        f"результат: {one_line(result_text)} — {one_line(source)}"
    )
    body = append_history(body, history)
    target.write_text(join_document(inner, body), encoding="utf-8", newline="\n")
    return {
        "ok": True,
        "path": rel or target.as_posix(),
        "experiment_status": next_status,
        "continue": choice,
        "updated": iso,
    }


def _parse_day_arg(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ExperimentWriteError("дата нужна в виде YYYY-MM-DD") from exc


def _continue_arg(value: str) -> str:
    text = value.strip().casefold()
    if text not in CONTINUE_STATUS:
        raise argparse.ArgumentTypeError("continue: yes или no")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Списки экспериментов и запись результата. Бланк шаблона не меняет."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    active = sub.add_parser("list-active", help="experiment_status planned или running")
    pending = sub.add_parser("list-pending", help="experiment_status pending_review")
    for listing in (active, pending):
        listing.add_argument("--root", type=Path, default=HARVEST, help="Корень markdown. По умолчанию harvest/")
        listing.add_argument("--due", action="store_true", help="Только review_date сегодня или раньше")
        listing.add_argument("--today", default=None, help="YYYY-MM-DD вместо сегодняшней даты")

    record = sub.add_parser("record-result", help="Дописать результат и выбор продолжать или остановить")
    record.add_argument("--file", type=Path, required=True)
    record.add_argument("--result", required=True)
    record.add_argument("--continue", dest="continue_choice", type=_continue_arg, required=True)
    record.add_argument("--date", default=None, help="YYYY-MM-DD для истории и updated")
    record.add_argument("--source", default="CLI lh_experiments.py record-result")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "list-active":
            payload = list_active(args.root, today=_parse_day_arg(args.today), due_only=args.due)
            code = 0 if payload["ok"] else 1
        elif args.cmd == "list-pending":
            payload = list_pending(args.root, today=_parse_day_arg(args.today), due_only=args.due)
            code = 0 if payload["ok"] else 1
        else:
            payload = record_result(
                args.file,
                args.result,
                args.continue_choice,
                when=_parse_day_arg(args.date),
                source=args.source,
            )
            code = 0
    except ExperimentWriteError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
