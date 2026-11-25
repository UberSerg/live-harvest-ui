#!/usr/bin/env python3
"""Локальное извлечение карточек harvest по имени, alias и строке INDEX.

Без embeddings и без вывода тел карточек. Каталог harvest/Мозг/_system
по умолчанию не входит в выдачу: архитектурные документы не смешиваются
с персональным контекстом.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
HARVEST = ROOT / "harvest"
WLINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]]+)?(?:\|[^\]]+)?\]\]")
SYSTEM_PREFIX = "Мозг/_system/"


def _stdout_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def parse_fm(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        fm = yaml.safe_load(text[3:end]) or {}
    except Exception:
        return {}
    return fm if isinstance(fm, dict) else {}


def explain_reason(reason: str, query: str, alias: str | None = None) -> str:
    """Почему выбрана карточка. Текст строки INDEX и тело не копируются."""
    q = query.strip()
    if reason == "exact-stem":
        return f"имя файла совпало с запросом «{q}» целиком"
    if reason == "exact-alias":
        shown = alias or q
        return f"alias «{shown}» совпал с запросом «{q}» целиком"
    if reason == "stem-contains":
        return f"запрос «{q}» входит в имя файла"
    if reason == "alias-contains":
        shown = alias or q
        return f"запрос «{q}» входит в alias «{shown}»"
    if reason == "index-line":
        return "строка INDEX.md содержит запрос и ссылку на карточку; текст строки не копируется"
    if reason == "index-wikilink":
        return "в INDEX.md есть точная вики-ссылка на это имя; текст строки не копируется"
    return reason


def iter_cards(include_system: bool, harvest: Path | None = None):
    harvest = harvest or HARVEST
    for path in harvest.rglob("*.md"):
        if ".obsidian" in path.parts:
            continue
        rel = path.relative_to(harvest).as_posix()
        if "/_backups/" in f"/{rel}/":
            continue
        if not include_system and rel.startswith(SYSTEM_PREFIX):
            continue
        yield rel, path


def retrieve(
    query: str,
    limit: int,
    include_system: bool,
    harvest: Path | None = None,
) -> dict:
    harvest = harvest or HARVEST
    needle = query.casefold().strip()
    ranked: list[tuple[int, str, str, str]] = []
    seen: set[str] = set()

    def add(rank: int, rel: str, reason: str, detail: str) -> None:
        if rel in seen:
            return
        seen.add(rel)
        ranked.append((rank, rel, reason, detail))

    index_text = ""
    index_path = harvest / "INDEX.md"
    if index_path.exists():
        index_text = index_path.read_text(encoding="utf-8-sig")

    stem_to_rel: dict[str, str] = {}
    for rel, path in iter_cards(include_system, harvest):
        stem = path.stem
        stem_to_rel[stem] = rel
        text = path.read_text(encoding="utf-8-sig")
        fm = parse_fm(text)
        aliases = [str(a) for a in (fm.get("aliases") or []) if a]
        stem_cf = stem.casefold()
        if stem_cf == needle:
            add(0, rel, "exact-stem", explain_reason("exact-stem", query))
        elif needle and needle in stem_cf:
            add(2, rel, "stem-contains", explain_reason("stem-contains", query))
        for alias in aliases:
            alias_cf = alias.casefold()
            if alias_cf == needle:
                add(1, rel, "exact-alias", explain_reason("exact-alias", query, alias))
            elif needle and needle in alias_cf:
                add(3, rel, "alias-contains", explain_reason("alias-contains", query, alias))

    if needle and index_text:
        for line in index_text.splitlines():
            if needle not in line.casefold():
                continue
            for name in WLINK_RE.findall(line):
                rel = stem_to_rel.get(name.strip())
                if rel:
                    add(4, rel, "index-line", explain_reason("index-line", query))

    ranked.sort(key=lambda item: (item[0], item[1]))
    hits = [
        {"path": rel, "reason": reason, "detail": detail}
        for _, rel, reason, detail in ranked[:limit]
    ]
    return {"query": query, "limit": limit, "count": len(hits), "hits": hits}


def preflight(stem: str, harvest: Path | None = None) -> dict:
    harvest = harvest or HARVEST
    target = stem.casefold().strip()
    matches: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for rel, path in iter_cards(True, harvest):
        candidates: list[tuple[str, str, str]] = []
        if path.stem.casefold() == target:
            candidates.append((rel, "exact-stem", explain_reason("exact-stem", stem)))
        text = path.read_text(encoding="utf-8-sig")
        fm = parse_fm(text)
        for alias in fm.get("aliases") or []:
            if str(alias).casefold() == target:
                candidates.append(
                    (rel, "exact-alias", explain_reason("exact-alias", stem, str(alias)))
                )
        for rel_hit, reason, detail in candidates:
            key = (rel_hit, reason)
            if key in seen:
                continue
            seen.add(key)
            matches.append({"path": rel_hit, "reason": reason, "detail": detail})
    return {"stem": stem, "exists": bool(matches), "matches": matches}


def main(argv: list[str] | None = None) -> int:
    _stdout_utf8()
    parser = argparse.ArgumentParser(
        description="Найти карточки Live Harvest, не загружая их тела в ответ."
    )
    parser.add_argument("--query", default="")
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument(
        "--include-system",
        action="store_true",
        help="Включить harvest/Мозг/_system в поиск по имени.",
    )
    parser.add_argument(
        "--preflight",
        default="",
        help="Точное имя или alias. Код 2, если карточка уже есть.",
    )
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit должен быть >= 1")
    if args.preflight.strip():
        result = preflight(args.preflight.strip())
        json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 2 if result["exists"] else 0
    if not args.query.strip():
        parser.error("нужен --query или --preflight")
    result = retrieve(args.query.strip(), args.limit, args.include_system)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
