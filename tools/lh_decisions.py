#!/usr/bin/env python3
"""Исход новых решений: список ожидания и запись факта с уроком.

Пять старых карточек в harvest/Решения/ команда не меняет.
Текст урока берётся только из аргументов. Из других карточек он не выводится.
record-outcome дописывает секции и историю и не стирает уже написанные абзацы.
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

LEGACY_RELS = frozenset(
    {
        "Решения/Решение — MVP стек Live Harvest.md",
        "Решения/Решение — границы Kraken vs Snowball.md",
        "Решения/Решение — границы финансовых систем.md",
        "Решения/Решение — место Kraken Vault.md",
        "Решения/Решение — каркас UI профиля Live Harvest.md",
    }
)

CLOSED = {"reviewed", "recorded", "not_applicable"}
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
SCALAR_LINE = re.compile(r"^([A-Za-z0-9_]+):[ \t]*(.*)$")
BLOCK_TOKENS = {"|", ">", "|-", ">-", "|+", ">+"}


class DecisionWriteError(ValueError):
    """Отказ записи: файл не тот или правка сломала бы уже записанный YAML."""


def read_markdown(path: Path) -> str:
    text = path.read_text(encoding="utf-8-sig")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def split_document(text: str) -> tuple[dict, str, str]:
    if not text.startswith("---"):
        raise DecisionWriteError("нет frontmatter")
    end = text.find("\n---", 3)
    if end == -1:
        raise DecisionWriteError("нет закрывающего frontmatter")
    inner = text[4:end]
    loaded = yaml.safe_load(inner) or {}
    if not isinstance(loaded, dict):
        raise DecisionWriteError("frontmatter не словарь")
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


def blank(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    return False


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


def has_outcome_schema(fm: dict, body: str) -> bool:
    if any(key in fm for key in ("expected_outcome", "actual_outcome", "lesson", "outcome_status")):
        return True
    if section_text(body, "Фактический результат") is not None:
        return True
    if section_text(body, "Ожидаемый результат") is not None:
        return True
    return False


def one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def format_pair(key: str, value: str) -> str:
    if value == "":
        return f'{key}: ""'
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value):
        return f"{key}: {value}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return f"{key}: {value}"
    return f"{key}: {json.dumps(value, ensure_ascii=False)}"


def parse_scalar_token(key: str, token: str) -> str:
    if token.strip() in BLOCK_TOKENS:
        raise DecisionWriteError(f"{key}: блочный YAML, команда его не переписывает")
    if token.strip() == "":
        return ""
    loaded = yaml.safe_load(token)
    if loaded is None:
        return ""
    if isinstance(loaded, date) and not isinstance(loaded, datetime):
        return loaded.isoformat()
    if isinstance(loaded, datetime):
        return loaded.date().isoformat()
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
        raise DecisionWriteError(f"пустой текст секции «{title}»")
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


def classify(path: Path, harvest: Path, today: date) -> dict | None:
    rel = harvest_rel(path, harvest)
    if rel is None:
        return None
    text = read_markdown(path)
    if not text.startswith("---"):
        return None
    try:
        fm, body, _inner = split_document(text)
    except DecisionWriteError as exc:
        return {"kind": "error", "path": rel, "detail": str(exc)}
    except yaml.YAMLError as exc:
        return {"kind": "error", "path": rel, "detail": str(exc).splitlines()[0]}
    if fm.get("type") != "decision":
        return None
    status = fm.get("outcome_status")
    status_text = "" if status is None else str(status).strip()
    actual_empty = field_empty(fm.get("actual_outcome"), section_text(body, "Фактический результат"))
    lesson_empty = field_empty(fm.get("lesson"), section_text(body, "Урок"))
    review = parse_day(fm.get("review_date"))
    legacy = rel in LEGACY_RELS
    row = {
        "path": rel,
        "outcome_status": status_text,
        "review_date": review.isoformat() if review else "",
        "due": bool(review and review <= today),
        "actual_empty": actual_empty,
        "lesson_empty": lesson_empty,
        "synthetic": fm.get("synthetic") is True,
        "legacy": legacy,
    }
    if legacy:
        row["kind"] = "legacy"
        row["reason"] = "legacy-exempt"
        return row
    if status_text.casefold() in CLOSED:
        return None
    if not has_outcome_schema(fm, body):
        row["kind"] = "pending"
        row["reason"] = "missing_outcome_fields"
        return row
    if status_text.casefold() == "pending" or status_text == "" or actual_empty:
        row["kind"] = "pending"
        if status_text.casefold() == "pending":
            row["reason"] = "outcome_status pending"
        elif actual_empty:
            row["reason"] = "empty actual"
        else:
            row["reason"] = "outcome open"
        return row
    return None


def list_pending(
    root: Path | None = None,
    *,
    today: date | None = None,
    due_only: bool = False,
    include_legacy: bool = False,
) -> dict:
    harvest = (root or HARVEST).resolve()
    if not harvest.is_dir():
        raise DecisionWriteError(f"нет каталога: {harvest}")
    current = today or date.today()
    pending: list[dict] = []
    legacy: list[dict] = []
    errors: list[dict] = []
    for path in sorted(harvest.rglob("*.md")):
        row = classify(path, harvest, current)
        if row is None:
            continue
        kind = row.get("kind")
        if kind == "error":
            errors.append({"path": row["path"], "detail": row.get("detail", "")})
        elif kind == "legacy":
            legacy.append(row)
        elif kind == "pending" and (not due_only or row["due"]):
            pending.append(row)
    pending.sort(key=lambda item: item["path"])
    legacy.sort(key=lambda item: item["path"])
    payload: dict = {
        "ok": not errors,
        "today": current.isoformat(),
        "due_only": due_only,
        "pending": pending,
        "legacy_skipped": len(legacy),
        "errors": errors,
    }
    if include_legacy:
        payload["legacy"] = [
            {"path": item["path"], "reason": item["reason"]} for item in legacy
        ]
    return payload


def record_outcome(
    path: Path,
    actual: str,
    lesson: str,
    *,
    when: date | None = None,
    source: str = "CLI lh_decisions.py record-outcome",
    harvest: Path | None = None,
) -> dict:
    actual_text = actual.strip()
    lesson_text = lesson.strip()
    if not actual_text or not lesson_text:
        raise DecisionWriteError("нужны непустые actual и lesson")
    target = path.resolve()
    if not target.is_file():
        raise DecisionWriteError(f"нет файла: {target}")
    root = (harvest or HARVEST).resolve()
    rel = harvest_rel(target, root)
    if rel in LEGACY_RELS:
        raise DecisionWriteError("пять старых решений не изменяются этой командой")
    original = read_markdown(target)
    fm, body, inner = split_document(original)
    if fm.get("type") != "decision":
        raise DecisionWriteError("файл не decision")
    current = when or date.today()
    iso = current.isoformat()
    previous_actual = read_scalar(inner, "actual_outcome") or ""
    previous_lesson = read_scalar(inner, "lesson") or ""
    next_actual = actual_text if not previous_actual.strip() else previous_actual.rstrip() + "\n" + actual_text
    next_lesson = lesson_text if not previous_lesson.strip() else previous_lesson.rstrip() + "\n" + lesson_text
    inner = set_scalar(inner, "actual_outcome", next_actual)
    inner = set_scalar(inner, "lesson", next_lesson)
    inner = set_scalar(inner, "outcome_status", "reviewed")
    inner = set_scalar(inner, "updated", iso)
    body = append_paragraph(body, "Фактический результат", actual_text)
    body = append_paragraph(body, "Урок", lesson_text)
    history = (
        f"{iso} — фактический результат: {one_line(actual_text)} — "
        f"урок: {one_line(lesson_text)} — {one_line(source)}"
    )
    body = append_history(body, history)
    target.write_text(join_document(inner, body), encoding="utf-8", newline="\n")
    return {
        "ok": True,
        "path": rel or target.as_posix(),
        "outcome_status": "reviewed",
        "updated": iso,
    }


def _parse_day_arg(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise DecisionWriteError("дата нужна в виде YYYY-MM-DD") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ожидание и запись исхода новых решений. Пять старых карточек не меняет."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    pending = sub.add_parser("list-pending", help="Решения с незакрытым исходом")
    pending.add_argument("--root", type=Path, default=HARVEST, help="Корень markdown. По умолчанию harvest/")
    pending.add_argument("--due", action="store_true", help="Только review_date сегодня или раньше")
    pending.add_argument("--today", default=None, help="YYYY-MM-DD вместо сегодняшней даты")
    pending.add_argument("--include-legacy", action="store_true", help="Добавить пути пяти старых карточек")

    record = sub.add_parser("record-outcome", help="Дописать факт и урок в одну карточку")
    record.add_argument("--file", type=Path, required=True)
    record.add_argument("--actual", required=True)
    record.add_argument("--lesson", required=True)
    record.add_argument("--date", default=None, help="YYYY-MM-DD для истории и updated")
    record.add_argument("--source", default="CLI lh_decisions.py record-outcome")

    args = parser.parse_args(argv)
    try:
        if args.cmd == "list-pending":
            payload = list_pending(
                args.root,
                today=_parse_day_arg(args.today),
                due_only=args.due,
                include_legacy=args.include_legacy,
            )
            code = 0 if payload["ok"] else 1
        else:
            payload = record_outcome(
                args.file,
                args.actual,
                args.lesson,
                when=_parse_day_arg(args.date),
                source=args.source,
            )
            code = 0
    except DecisionWriteError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
