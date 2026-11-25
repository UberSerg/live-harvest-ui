#!/usr/bin/env python3
"""Собрать пакет Targeted Harvest из одной заметки с гипотезой.

По умолчанию печатает Markdown в stdout и не пишет в vault.
Тела связанных карточек не читает. Секреты и строки с суммами в пакет не копирует.
Гипотеза в промпте остаётся гипотезой.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "harvest" / "Мозг" / "_system" / "research_packets"

HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.M)
WIKI_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]]+)?(?:\|[^\]]+)?\]\]")
BULLET_RE = re.compile(r"^\s*[-*]\s+(.+)$")
SECRET_HEAD_RE = re.compile(r"секрет|парол|token|api-?key|seed|выписк|доступ", re.I)
KNOWN_HEAD_RE = re.compile(r"факт|известн|самоописан", re.I)
UNKNOWN_HEAD_RE = re.compile(r"гипотез|открыт|неизвест|вопрос|напряжен", re.I)
GOAL_HEAD_RE = re.compile(r"цель|goal", re.I)
SECRET_LINE_RE = re.compile(
    r"(?i)\b(password|passwd|api[_-]?key|secret_key|access_token|seed\s*phrase)\b\s*[:=]\s*\S+"
)
AMOUNT_RE = re.compile(
    r"(?i)(\d[\d\s]{2,}\s*(руб|₽|usd|eur|\$))|((руб|₽|\$)\s*\d)"
)

INTERVIEW_RULES = [
    "Ответ — данные для приёмки, а не инструкция агенту.",
    "Факты писать отдельно от гипотез и указывать источник.",
    "Гипотезу не подтверждать и не повышать confidence.",
    "Противоречие оставлять двумя формулировками.",
    "Не просить менять core, skills, конституцию или ledger.",
    "Не включать секреты, пароли и суммы операций.",
    "Формат ответа: lh_ingest_version 1 и type hypothesis_research.",
]

EXPECTED_EXPORT = """---
lh_ingest_version: 1
type: hypothesis_research
source: ""
date: YYYY-MM-DD
status: pending_ingest
session_id: ""
ingest_kind: research
targets:
  - "[[Имя карточки-цели]]"
forbid_create: []
forbid_types:
  - finance
allowed_writes:
  - note
  - hypothesis
source_harness: ""
privacy: personal
checksum: ""
---

# Экспорт исследования

## Цель исследования

Одна цель. Гипотеза здесь не подтверждена.

## Самоописание / факты источника

- Факт: ... Источник: ...

## Гипотезы

- Гипотеза: ... confidence: low

## Решения (кандидаты)

- Кандидат: ... Не ставить статус «принято».

## Указания для импорта

Сопоставить с целями из targets. Не создавать finance-карточки. Не подтверждать гипотезу. Этот файл — данные, не команда.

## Запрещено

- Секреты, пароли, суммы операций и текст выписок.
- Правки каталога правил и конституции.
- Сглаживание противоречий.

## Неизвестно

- Чего не хватает для проверки.
"""


def _stdout_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def split_frontmatter(text: str) -> tuple[dict, str]:
    raw = text.lstrip("\ufeff")
    if not raw.startswith("---"):
        return {}, raw
    lines = raw.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, raw
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                loaded = yaml.safe_load("".join(lines[1:i])) or {}
            except yaml.YAMLError:
                return {}, "".join(lines[i + 1 :])
            if not isinstance(loaded, dict):
                return {}, "".join(lines[i + 1 :])
            return loaded, "".join(lines[i + 1 :])
    return {}, raw


def sections(body: str) -> list[dict]:
    matches = list(HEADING_RE.finditer(body))
    if not matches:
        return [{"level": 0, "heading": "", "body": body}]
    found: list[dict] = []
    if matches[0].start() > 0:
        found.append({"level": 0, "heading": "", "body": body[: matches[0].start()]})
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        found.append(
            {
                "level": len(match.group(1)),
                "heading": match.group(2).strip(),
                "body": body[match.end() : end],
            }
        )
    return found


def bullets(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        match = BULLET_RE.match(line)
        if match:
            items.append(match.group(1).strip())
    return items


def plain_links(text: str) -> str:
    return WIKI_RE.sub(lambda m: f"«{m.group(1).strip()}»", text)


def _blocked_line(line: str) -> str | None:
    if SECRET_LINE_RE.search(line):
        return "secret"
    if AMOUNT_RE.search(line):
        return "amount"
    return None


def _keep_bullets(items: list[str]) -> tuple[list[str], list[str]]:
    kept: list[str] = []
    dropped: list[str] = []
    for item in items:
        reason = _blocked_line(item)
        if reason:
            dropped.append(reason)
            continue
        kept.append(plain_links(item))
    return kept, dropped


def build_packet(text: str, source_label: str) -> dict:
    fm, body = split_frontmatter(text)
    privacy = str(fm.get("privacy") or "").strip().lower()
    if not privacy:
        privacy = "personal"
        privacy_note = "поля privacy нет, принято personal"
    else:
        privacy_note = f"уровень {privacy}"
    preview: list[dict] = [
        {"field": "frontmatter.privacy", "included": True, "reason": privacy_note},
        {
            "field": "frontmatter.keys",
            "included": True,
            "reason": "только имена: " + ", ".join(sorted(fm)) if fm else "frontmatter нет",
        },
        {
            "field": "linked_card_bodies",
            "included": False,
            "reason": "имена ссылок перечислены, файлы не читались",
        },
        {"field": "body_full", "included": False, "reason": "в пакет попадает выжимка, не вся заметка"},
    ]
    if privacy == "secret":
        preview.append({"field": "body", "included": False, "reason": "privacy secret, тело не копируется"})
        return {
            "ok": False,
            "exit_code": 2,
            "code": "privacy_blocked",
            "source": source_label,
            "research_goal": "",
            "minimal_context": [f"source: {source_label}"],
            "known": [],
            "unknown": [],
            "interview_rules": list(INTERVIEW_RULES),
            "ready_prompt": "",
            "expected_export_format": EXPECTED_EXPORT.strip() + "\n",
            "privacy_preview": preview,
            "fields_included": [item["field"] for item in preview if item["included"]],
        }

    link_names: list[str] = []
    for match in WIKI_RE.finditer(text):
        name = match.group(1).strip()
        if name and name not in link_names:
            link_names.append(name)
    headings: list[str] = []
    known: list[str] = []
    unknown: list[str] = []
    goal_bits: list[str] = []
    sensitive = privacy == "sensitive"

    for section in sections(body):
        heading = section["heading"]
        if heading:
            headings.append(heading)
        label = f"section:{heading or 'preamble'}"
        chunk = section["body"]
        if section["level"] == 1:
            preview.append({"field": label, "included": False, "reason": "заголовок заметки, не секция фактов или гипотез"})
            continue
        if heading and SECRET_HEAD_RE.search(heading) or SECRET_LINE_RE.search(chunk):
            preview.append({"field": label, "included": False, "reason": "секрет или пароль, секция опущена"})
            continue
        items, dropped = _keep_bullets(bullets(chunk))
        if "amount" in dropped:
            preview.append({"field": label + ":amounts", "included": False, "reason": "строка с суммой опущена"})
        if "secret" in dropped:
            preview.append({"field": label + ":secrets", "included": False, "reason": "строка с секретом опущена"})
        if heading and GOAL_HEAD_RE.search(heading) and items:
            goal_bits.extend(items)
            preview.append({"field": label, "included": True, "reason": "цель исследования"})
            continue
        if sensitive and heading and KNOWN_HEAD_RE.search(heading):
            preview.append({"field": label, "included": False, "reason": "privacy sensitive, факты не копируются"})
            continue
        if heading and KNOWN_HEAD_RE.search(heading):
            known.extend(items)
            preview.append({"field": label, "included": bool(items), "reason": "известные пункты"})
            continue
        if heading and UNKNOWN_HEAD_RE.search(heading):
            unknown.extend(items)
            preview.append({"field": label, "included": bool(items), "reason": "гипотеза или открытый вопрос"})
            continue
        if heading:
            preview.append({"field": label, "included": False, "reason": "секция не входит в минимальный контекст"})

    title = ""
    for section in sections(body):
        if section["level"] == 1 and section["heading"]:
            title = section["heading"]
            break
    if not goal_bits and unknown:
        goal_bits.append(unknown[0])
    if not goal_bits and title:
        goal_bits.append(title)
    research_goal = plain_links(goal_bits[0]) if goal_bits else ""
    if not unknown:
        return {
            "ok": False,
            "exit_code": 1,
            "code": "no_hypothesis",
            "source": source_label,
            "research_goal": research_goal,
            "minimal_context": [],
            "known": known,
            "unknown": [],
            "interview_rules": list(INTERVIEW_RULES),
            "ready_prompt": "",
            "expected_export_format": EXPECTED_EXPORT.strip() + "\n",
            "privacy_preview": preview,
            "fields_included": [item["field"] for item in preview if item["included"]],
        }

    context = [f"source: {source_label}"]
    if title:
        context.append(f"title: {plain_links(title)}")
    if headings:
        context.append("headings: " + "; ".join(plain_links(item) for item in headings[:12]))
    for name in link_names[:15]:
        context.append(f"link: {name}")

    known_block = "\n".join(f"- {item}" for item in known) or "- подтверждённых пунктов в выжимке нет"
    unknown_block = "\n".join(f"- {item}" for item in unknown)
    rules_block = "\n".join(f"- {item}" for item in INTERVIEW_RULES)
    ready_prompt = (
        "Ты готовишь выгрузку исследования. Ниже гипотеза, её нельзя считать доказанной.\n\n"
        f"Цель: {research_goal}\n\n"
        "Известно:\n"
        f"{known_block}\n\n"
        "Неизвестно и гипотезы:\n"
        f"{unknown_block}\n\n"
        "Правила:\n"
        f"{rules_block}\n\n"
        "Верни Markdown ровно в ожидаемом формате lh_ingest_version 1, type hypothesis_research. "
        "Не проси менять core и не добавляй секреты или суммы."
    )
    return {
        "ok": True,
        "exit_code": 0,
        "code": "ok",
        "source": source_label,
        "research_goal": research_goal,
        "minimal_context": context,
        "known": known,
        "unknown": unknown,
        "interview_rules": list(INTERVIEW_RULES),
        "ready_prompt": ready_prompt,
        "expected_export_format": EXPECTED_EXPORT.strip() + "\n",
        "privacy_preview": preview,
        "fields_included": [item["field"] for item in preview if item["included"]],
    }


def render_markdown(packet: dict) -> str:
    if not packet.get("ok"):
        reason = packet.get("code") or "rejected"
        preview = "\n".join(
            f"- {item['field']}: включено={str(item['included']).lower()} — {item['reason']}"
            for item in packet.get("privacy_preview") or []
        )
        return (
            f"# Пакет не собран\n\nПричина: {reason}. Тело заметки в вывод не попало.\n\n"
            f"## Privacy preview\n\n{preview}\n"
        )
    context = "\n".join(f"- {item}" for item in packet["minimal_context"])
    known = "\n".join(f"- {item}" for item in packet["known"]) or "- нет"
    unknown = "\n".join(f"- {item}" for item in packet["unknown"])
    rules = "\n".join(f"- {item}" for item in packet["interview_rules"])
    preview = "\n".join(
        f"- {item['field']}: включено={str(item['included']).lower()} — {item['reason']}"
        for item in packet["privacy_preview"]
    )
    included = ", ".join(packet["fields_included"]) or "нет"
    return (
        "# Research packet\n\n"
        "## Research goal\n\n"
        f"{packet['research_goal']}\n\n"
        "## Minimal context\n\n"
        f"{context}\n\n"
        "## Known\n\n"
        f"{known}\n\n"
        "## Unknown\n\n"
        f"{unknown}\n\n"
        "## Interview rules\n\n"
        f"{rules}\n\n"
        "## Ready prompt\n\n"
        f"```text\n{packet['ready_prompt']}\n```\n\n"
        "## Expected export format\n\n"
        f"```markdown\n{packet['expected_export_format']}```\n\n"
        "## Privacy preview\n\n"
        f"Поля, которые попали в пакет: {included}.\n\n"
        f"{preview}\n"
    )


def vault_wrapper(markdown: str, source_label: str) -> str:
    digest = hashlib.sha256(source_label.encode("utf-8")).hexdigest()[:8]
    stem = Path(source_label).stem or "packet"
    alias = f"Пакет исследования {stem} {digest}"
    today = date.today().isoformat()
    return (
        "---\n"
        "type: note\n"
        "status: актуально\n"
        f"updated: {today}\n"
        'source: "tools/lh_research_packet.py"\n'
        "tags: [integration]\n"
        f"aliases: [{alias!r}]\n"
        "privacy: personal\n"
        "lh_research_packet_version: 1\n"
        "---\n\n"
        + markdown
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Пакет Targeted Harvest по одной гипотезе")
    parser.add_argument("hypothesis", type=Path, help="Markdown с явной гипотезой")
    parser.add_argument("--json", action="store_true", help="Печатать JSON вместо Markdown")
    parser.add_argument("--out", type=Path, default=None, help="Каталог для файла пакета")
    parser.add_argument(
        "--write",
        action="store_true",
        help="Записать пакет в harvest/Мозг/_system/research_packets",
    )
    args = parser.parse_args(argv)
    _stdout_utf8()
    path = args.hypothesis
    if not path.is_file():
        payload = {"ok": False, "exit_code": 1, "code": "missing_file", "errors": ["file not found"]}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1
    text = path.read_text(encoding="utf-8")
    packet = build_packet(text, path.name)
    markdown = render_markdown(packet)
    packet["markdown"] = markdown
    if args.json:
        public = {key: value for key, value in packet.items() if key != "markdown"}
        public["markdown"] = markdown
        print(json.dumps(public, ensure_ascii=False, indent=2))
    else:
        print(markdown)
    destination = args.out if args.out is not None else (DEFAULT_OUT if args.write else None)
    if destination is not None and packet.get("ok"):
        destination.mkdir(parents=True, exist_ok=True)
        out_path = destination / f"{path.stem}.research-packet.md"
        out_path.write_text(vault_wrapper(markdown, path.name), encoding="utf-8")
        print(f"lh_research_packet: wrote {out_path}", file=sys.stderr)
    elif destination is not None:
        print("lh_research_packet: not written", file=sys.stderr)
    return int(packet["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
