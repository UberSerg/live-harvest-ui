#!/usr/bin/env python3
"""Build harvest-ui snapshot from harvest/ cards + explicit overlay.json.

Literal strings are copied from card sections (Факты, Гипотезы, Открытые вопросы,
Намерения) or from an overlay field the user/agent wrote. Missing morning fields
stay null. The script does not fill focus, checkpoint, steps, questions, or
epistemic labels with its own copy.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
HARVEST = ROOT / "harvest"
UI = ROOT / "harvest-ui"
OVERLAY = UI / "overlay.json"
OUT_JSON = UI / "snapshot.json"
OUT_JS = UI / "data.js"
DEMO_JSON = UI / "demo" / "snapshot.demo.json"
DEMO_JS = UI / "demo" / "data.demo.js"
DEMO_FIXTURE = UI / "demo" / "fixture"
DEMO_OVERLAY = UI / "demo" / "overlay.demo.json"
DEFAULT_MANIFEST_PATH = HARVEST / "Мозг" / "_system" / "snapshot-sources.yaml"

# Files build_literal() reads. A missing file leaves null / []. This is not fallback copy.
DEFAULT_RENDERED_SOURCES = [
    "Личность/Сергей.md",
    "Личность/Ценности и понимание свободы.md",
    "Личность/Работа — тимлид 1С УХ.md",
    "Личность/Профессиональный профиль и карьерная мотивация.md",
    "Цели/Финансовая независимость и капитал.md",
    "Личность/Интересы и отдых.md",
    "Личность/Принятие решений и отношение к ошибкам.md",
    "Связи/Семья.md",
    "Личность/Здоровье привычки и эмоциональное состояние.md",
    "Личность/Созидание деньги и управление.md",
    "Проекты/Live Harvest.md",
    "Заметки/Гипотезы для проверки при самопознании.md",
    "Цели/Образ желаемой жизни.md",
]

# Removed compiler defaults. A snapshot fails the honesty check when any of
# these strings appear. Overlay may still supply different morning copy.
DISHONEST_SENTINELS = (
    "Тимлид 1С · основатель Live Harvest",
    "Тимлид 1С УХ · основатель Live Harvest",
    "Собрать Life OS, которым хочется пользоваться каждый день",
    "Ближайший шаг — аренда в Москве",
    "Одна цель: капитал, дом и опциональность найма — грани одного намерения.",
    "Анализ → внутренний отклик → эксперты → риски → решение",
    "Ошибки сначала болезненны, затем выводы",
    "ИИ / вайбкодинг",
    "Dota 2 / WoW",
    "Семья — опора; переезд связан с работой жены.",
    "Свободных денег мало для покупки/дома.",
    "Live Harvest — приоритетный проект для заработка (монетизация открыта).",
    "Удалёнка, тимлид 1С УХ; найм как база.",
    "ИИ, продукты, вайбкодинг — намерения развития.",
    "Что на этой неделе запускает и гасит твою волну вдохновения?",
    "UI default until overlay",
    "Аренда МСК — ближайший шаг",
    "Единое намерение (не конфликт)",
    "Отец, тимлид, строитель персональных систем. Ищет свободу без потери опоры.",
    "Систематизировать себя через Live Harvest",
    "Продуктовый буст при сохранении найма",
    "Возможно, различает карьерный риск и риск капитала",
    "1С, аналитика, управление командой (самоописание)",
    "ИИ, робототехника, создание продуктов",
    "Волейбол, велосипед, RPG/Dota/WoW, природа, стихи раньше",
    "Прикладной результат, системная память контекста",
    "Дисциплина, здоровье, отказ от курения; алкоголь — редкий или отказ",
    "Что помогало удерживать отказ раньше?",
    "Гипотезы ИИ по самопознанию — только к проверке",
    "Волны вдохновения vs завершение важного",
    "Делегирование vs контроль концепции / общая волна — риск, не CONTR",
    "Спокойный спортивный человек; семья; тёплое место; вайбкодинг по кайфу",
    "Концепция Live Harvest",
    "Первый крупный импорт знаний",
    "Интервью → поглощение",
    "Challenge созидание/управление",
    "Challenge: созидание / деньги / управление",
    "Интервью → портрет",
    "Аренда = ближайший жилищный шаг",
    "Старт Live Harvest",
    "Challenge-интервью поглощено в harvest/",
    "CONTR-015: приоритет аренды",
    "UI snapshot из harvest/",
)

# Injected only when overlay had no sideQuests. Not sentinels of a merged
# snapshot: the same titles may be written explicitly in overlay.json.
DEFAULT_SIDE_QUESTS_REMOVED = (
    "Аренда в Москве + переезд с дочерью",
    "Live Harvest как ежедневный Life OS",
    "Первый измеримый этап монетизации",
)

_EP_BY_PREFIX = (
    ("Факты", "fact"),
    ("Гипотезы", "hypo"),
    ("Открытые вопросы", "open"),
    ("Намерения", "intent"),
)

UNIVERSE_BASE = [
    {"id": "family", "label": "Семья", "angle": -90, "status": "empty", "blurb": None},
    {"id": "finance", "label": "Финансы", "angle": -30, "status": "empty", "blurb": None},
    {"id": "health", "label": "Здоровье", "angle": 20, "status": "empty", "blurb": None},
    {"id": "projects", "label": "Проекты", "angle": 70, "status": "empty", "blurb": None},
    {"id": "work", "label": "Работа", "angle": 125, "status": "empty", "blurb": None},
    {"id": "learn", "label": "Обучение", "angle": 175, "status": "empty", "blurb": None},
    {"id": "rest", "label": "Отдых", "angle": 220, "status": "empty", "blurb": None},
]


def _stdout_utf8() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")


def _as_path_items(value) -> list[dict]:
    items: list[dict] = []
    for raw in value or []:
        if isinstance(raw, str):
            items.append({"path": raw.replace("\\", "/"), "slot": "", "reason": ""})
        elif isinstance(raw, dict) and raw.get("path"):
            items.append(
                {
                    "path": str(raw["path"]).replace("\\", "/"),
                    "slot": str(raw.get("slot") or ""),
                    "reason": str(raw.get("reason") or ""),
                }
            )
    return items


def builtin_manifest() -> dict:
    return {
        "version": 1,
        "contract": "snapshot-sources/1",
        "mode": "builtin",
        "path": None,
        "rendered": [{"path": rel, "slot": "", "reason": ""} for rel in DEFAULT_RENDERED_SOURCES],
        "extra_unrendered": [],
        "excluded": [],
    }


def load_source_manifest(path: Path | None = None) -> dict:
    """Optional manifest. A missing default file keeps the built-in read list."""
    explicit = path is not None
    target = path if path is not None else DEFAULT_MANIFEST_PATH
    if not target.exists():
        if explicit:
            raise FileNotFoundError(target)
        return builtin_manifest()
    loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    if not isinstance(loaded, dict):
        raise ValueError("snapshot manifest must be a mapping")
    return {
        "version": loaded.get("version") or 1,
        "contract": loaded.get("contract") or "snapshot-sources/1",
        "mode": "file",
        "path": str(target),
        "rendered": _as_path_items(loaded.get("rendered")),
        "extra_unrendered": _as_path_items(loaded.get("extra_unrendered")),
        "excluded": _as_path_items(loaded.get("excluded")),
    }


def coverage_report(manifest: dict, harvest_root: Path) -> dict:
    """Which declared paths the builder reads. Does not read card bodies."""
    builder = set(DEFAULT_RENDERED_SOURCES)
    rendered_present: list[str] = []
    rendered_missing: list[str] = []
    for item in manifest.get("rendered") or []:
        rel = item["path"]
        if (harvest_root / rel).is_file():
            rendered_present.append(rel)
        else:
            rendered_missing.append(rel)
    not_in_snapshot: list[dict] = []
    for item in manifest.get("rendered") or []:
        if item["path"] not in builder:
            not_in_snapshot.append(
                {
                    "path": item["path"],
                    "reason": item["reason"] or "в манифесте как rendered, сборщик этот файл не читает",
                    "exists": (harvest_root / item["path"]).is_file(),
                }
            )
    for item in manifest.get("extra_unrendered") or []:
        not_in_snapshot.append(
            {
                "path": item["path"],
                "reason": item["reason"] or "объявлен вне портретного сборщика",
                "exists": (harvest_root / item["path"]).is_file(),
            }
        )
    for item in manifest.get("excluded") or []:
        not_in_snapshot.append(
            {
                "path": item["path"],
                "reason": item["reason"] or "исключён из снимка",
                "exists": (harvest_root / item["path"]).exists(),
            }
        )
    return {
        "contract": "snapshot-sources/1",
        "mode": manifest.get("mode") or "builtin",
        "manifest_path": manifest.get("path"),
        "builder_paths": list(DEFAULT_RENDERED_SOURCES),
        "rendered_present": rendered_present,
        "rendered_missing": rendered_missing,
        "not_in_snapshot": not_in_snapshot,
    }


def attach_source_meta(
    data: dict,
    manifest_path: Path | None = None,
    harvest_root: Path | None = None,
) -> dict:
    """Additive meta. Does not fill portrait, morning, or fact fields."""
    root = harvest_root or HARVEST
    try:
        manifest = load_source_manifest(manifest_path)
        report = coverage_report(manifest, root)
        data.setdefault("meta", {})["sources"] = {
            "contract": report["contract"],
            "mode": report["mode"],
            "rendered_missing": report["rendered_missing"],
            "not_in_snapshot": report["not_in_snapshot"],
        }
    except Exception as exc:
        data.setdefault("meta", {})["sources"] = {
            "contract": "snapshot-sources/1",
            "mode": "builtin",
            "error": exc.__class__.__name__,
            "rendered_missing": [],
            "not_in_snapshot": [],
        }
    return data


def read_md(root: Path, rel: str) -> str:
    path = root / rel
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def iter_sections(text: str):
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", text, flags=re.M))
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        yield match.group(1).strip(), text[start:end]


def heading_ep(heading: str) -> str | None:
    for prefix, ep in _EP_BY_PREFIX:
        if heading == prefix or heading.startswith(prefix + " ") or heading.startswith(prefix + "("):
            return ep
    return None


def bullets(body: str) -> list[str]:
    items = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("- "):
            items.append(line[2:].strip())
    return items


def strip_wiki(s: str) -> str:
    return re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", s)


def h1(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r"^#\s+(.+?)\s*$", text, flags=re.M)
    if not match:
        return None
    title = strip_wiki(match.group(1).strip())
    return title or None


def section_prose(text: str, heading: str) -> str | None:
    for name, body in iter_sections(text):
        if name != heading:
            continue
        lines: list[str] = []
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                if lines:
                    break
                continue
            if stripped.startswith(("- ", "#")):
                break
            lines.append(stripped)
        if not lines:
            return None
        prose = strip_wiki(" ".join(lines)).strip()
        return prose or None
    return None


def ep_items(text: str, kinds: set[str] | None = None, limit: int = 24) -> list[dict]:
    if not text:
        return []
    out: list[dict] = []
    for heading, body in iter_sections(text):
        ep = heading_ep(heading)
        if ep is None:
            continue
        if kinds is not None and ep not in kinds:
            continue
        for bullet in bullets(body):
            cleaned = strip_wiki(bullet).strip()
            if not cleaned:
                continue
            out.append({"ep": ep, "text": cleaned})
            if len(out) >= limit:
                return out
    return out


def lit(value, source: str):
    return {"value": value, "mode": "literal", "source": source}


def unwrap(field, default=None):
    if field is None:
        return default
    if isinstance(field, dict) and "value" in field:
        return field["value"]
    return field


def clip_prefix(text: str, limit: int = 160) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > 40:
        cut = cut[:space]
    return cut


def value_tokens(facts: list[dict]) -> list[str]:
    for item in facts:
        text = item["text"]
        if text.lower().startswith("ключевые ценности"):
            part = text.split(":", 1)[-1]
            return [piece.strip().rstrip(".") for piece in part.split(",") if piece.strip()]
    return []


def motto_from(facts: list[dict]) -> str | None:
    for item in facts:
        text = item["text"]
        low = text.lower()
        if "не беспокоюсь" not in low and "критерий успеха" not in low:
            continue
        quote = re.search(r"«([^»]+)»", text)
        if quote:
            return quote.group(1)
    return None


def role_from(facts: list[dict]) -> str | None:
    for item in facts:
        text = item["text"]
        if not text.lower().startswith("работа:"):
            continue
        rest = text.split(":", 1)[1].strip()
        rest = re.split(r"\s+[—–-]\s+", rest, maxsplit=1)[0]
        rest = rest.strip().rstrip(".")
        return rest or None
    return None


def bind_fact_blurb(node: dict, text: str, source: str) -> None:
    facts = ep_items(text, kinds={"fact"}, limit=1)
    if not facts:
        return
    node["status"] = "active"
    node["blurb"] = clip_prefix(facts[0]["text"])
    node["mode"] = "literal"
    node["source"] = source


def make_cluster(cid: str, title: str, items: list[dict], source: str) -> dict:
    cluster = {
        "id": cid,
        "title": title,
        "mode": "literal" if items else None,
        "source": source if items and source else None,
        "items": items,
    }
    return cluster


def empty_razvivator() -> dict:
    return {"demo": False, "type": None, "text": None, "mode": None, "source": None}


def build_literal(harvest: Path | None = None, manifest_path: Path | None = None) -> dict:
    root = harvest or HARVEST
    sergey = read_md(root, "Личность/Сергей.md")
    values = read_md(root, "Личность/Ценности и понимание свободы.md")
    work = read_md(root, "Личность/Работа — тимлид 1С УХ.md")
    prof = read_md(root, "Личность/Профессиональный профиль и карьерная мотивация.md")
    fin = read_md(root, "Цели/Финансовая независимость и капитал.md")
    interests = read_md(root, "Личность/Интересы и отдых.md")
    decisions = read_md(root, "Личность/Принятие решений и отношение к ошибкам.md")
    family = read_md(root, "Связи/Семья.md")
    health = read_md(root, "Личность/Здоровье привычки и эмоциональное состояние.md")
    create = read_md(root, "Личность/Созидание деньги и управление.md")
    lh = read_md(root, "Проекты/Live Harvest.md")
    hypos = read_md(root, "Заметки/Гипотезы для проверки при самопознании.md")
    future = read_md(root, "Цели/Образ желаемой жизни.md")

    person_facts = ep_items(sergey, kinds={"fact"})
    value_facts = ep_items(values, kinds={"fact"})
    name = h1(sergey)
    role = role_from(person_facts)
    motto = motto_from(value_facts)
    lead = section_prose(sergey, "Суть")
    title = h1(fin)

    person_source = f"[[{name}]]" if name else None
    fields: dict = {}
    if name and person_source:
        fields["name"] = lit(name, person_source)
    if motto:
        fields["motto"] = lit(motto, "[[Ценности и понимание свободы]]")
    if role and person_source:
        fields["role"] = lit(role, person_source)

    quest_fields: dict = {}
    if title:
        quest_fields["title"] = lit(title, "[[Финансовая независимость и капитал]]")

    universe = [dict(node) for node in UNIVERSE_BASE]
    by_id = {node["id"]: node for node in universe}
    bind_fact_blurb(by_id["family"], family, "[[Семья]]")
    bind_fact_blurb(by_id["finance"], fin, "[[Финансовая независимость и капитал]]")
    bind_fact_blurb(by_id["health"], health, "[[Здоровье привычки и эмоциональное состояние]]")
    bind_fact_blurb(by_id["projects"], lh, "[[Live Harvest]]")
    bind_fact_blurb(by_id["work"], work, "[[Работа — тимлид 1С УХ]]")
    bind_fact_blurb(by_id["learn"], prof, "[[Профессиональный профиль и карьерная мотивация]]")
    bind_fact_blurb(by_id["rest"], interests, "[[Интересы и отдых]]")

    clusters = [
        make_cluster(
            "values",
            "Ценности и принципы",
            ep_items(values),
            "[[Ценности и понимание свободы]]",
        ),
        make_cluster("drive", "Мотивация", ep_items(sergey, kinds={"intent"}), person_source or ""),
        make_cluster(
            "mind",
            "Мышление",
            ep_items(decisions),
            "[[Принятие решений и отношение к ошибкам]]",
        ),
        make_cluster(
            "craft",
            "Компетенции",
            ep_items(prof, kinds={"fact", "intent"}),
            "[[Профессиональный профиль и карьерная мотивация]]",
        ),
        make_cluster("spark", "Интересы", ep_items(interests, kinds={"fact"}), "[[Интересы и отдых]]"),
        make_cluster("edge", "Сильные стороны", [], person_source or ""),
        make_cluster(
            "grow",
            "Зоны развития",
            ep_items(health),
            "[[Здоровье привычки и эмоциональное состояние]]",
        ),
        make_cluster(
            "tension",
            "Внутренние напряжения",
            ep_items(hypos, kinds={"hypo", "open"}),
            "[[Гипотезы для проверки при самопознании]]",
        ),
        make_cluster(
            "future",
            "Желаемый образ",
            ep_items(future, kinds={"intent", "open"}),
            "[[Образ желаемой жизни]]",
        ),
    ]
    create_items = ep_items(create)
    if create_items:
        clusters.insert(
            2,
            make_cluster("create", "Созидание и управление", create_items, "[[Созидание деньги и управление]]"),
        )

    data = {
        "meta": {
            "version": "0.4.2",
            "asOf": str(date.today()),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "product": "Personal Command Center",
            "snapshot": True,
            "ui_version": "0.4",
        },
        "profile": {
            "name": name,
            "role": role,
            "stage": None,
            "focus": None,
            "values": value_tokens(value_facts),
            "motto": motto,
            "_fields": fields,
        },
        "state": {"mood": None, "energy": None, "focus": None, "wave": None, "journal": None},
        "universe": universe,
        "mainQuest": {
            "title": title,
            "detail": None,
            "checkpoint": None,
            "_fields": quest_fields,
        },
        "sideQuests": [],
        "waves": [item["text"] for item in ep_items(interests, kinds={"fact"})],
        "razvivator": empty_razvivator(),
        "progress": {"achievements": [], "measurable": []},
        "recent": [],
        "portrait": {
            "core": {
                "title": "Ядро",
                "lead": lead,
                "mode": "literal" if lead else None,
                "source": person_source if lead else None,
            },
            "clusters": clusters,
            "history": [],
        },
    }
    # Personal manifest paths stay off fixture and demo builds.
    if root.resolve() == HARVEST.resolve():
        return attach_source_meta(data, manifest_path, root)
    return data


def deep_apply_overlay(data: dict, overlay: dict) -> dict:
    if not overlay:
        return data

    meta_o = overlay.get("meta") or {}
    data["meta"]["interpreted_at"] = meta_o.get("interpreted_at")
    data["meta"]["interpreter"] = meta_o.get("interpreter")
    data["meta"]["presentation_note"] = meta_o.get("note")

    prof = overlay.get("profile") or {}
    for key in ("stage", "focus"):
        if key in prof:
            data["profile"][key] = unwrap(prof[key], data["profile"].get(key))
            data["profile"].setdefault("_fields", {})[key] = prof[key]

    mq = overlay.get("mainQuest") or {}
    for key, val in mq.items():
        data["mainQuest"][key] = unwrap(val, data["mainQuest"].get(key))
        data["mainQuest"].setdefault("_fields", {})[key] = val

    uni_o = overlay.get("universe") or {}
    for node in data["universe"]:
        patch = uni_o.get(node["id"])
        if not patch:
            continue
        if "blurb" in patch:
            raw = patch["blurb"]
            node["blurb"] = unwrap(raw, node.get("blurb")) if isinstance(raw, dict) else raw
        if "status" in patch:
            node["status"] = patch["status"]
        node["mode"] = patch.get("mode", node.get("mode", "interpreted"))
        node["source"] = patch.get("source", node.get("source"))

    if "sideQuests" in overlay:
        data["sideQuests"] = [
            {
                "title": quest["title"],
                "meta": quest.get("meta", ""),
                "mode": quest.get("mode", "interpreted"),
                "source": quest.get("source"),
            }
            for quest in overlay["sideQuests"]
        ]

    if overlay.get("razvivator"):
        rz = overlay["razvivator"]
        data["razvivator"] = {
            "demo": rz.get("demo", False),
            "type": rz.get("type", "вопрос"),
            "text": rz.get("text", ""),
            "mode": rz.get("mode", "interpreted"),
            "source": rz.get("source"),
        }

    history = overlay.get("portrait_history")
    if isinstance(history, list):
        data["portrait"]["history"] = [
            {"when": row.get("when", ""), "text": row.get("text", "")}
            for row in history
            if isinstance(row, dict) and (row.get("when") or row.get("text"))
        ]

    extras = overlay.get("portrait_clusters_extra") or []
    if extras:
        existing = {cluster["id"] for cluster in data["portrait"]["clusters"]}
        for extra in extras:
            if extra["id"] in existing:
                data["portrait"]["clusters"] = [
                    extra if cluster["id"] == extra["id"] else cluster
                    for cluster in data["portrait"]["clusters"]
                ]
            else:
                data["portrait"]["clusters"].insert(2, extra)

    prepend = overlay.get("recent_prepend") or []
    if prepend:
        data["recent"] = [
            {"what": row["what"], "kind": row.get("kind", "знание")} for row in prepend
        ] + data["recent"]

    return data


def assemble(
    harvest: Path | None = None,
    overlay: dict | None = None,
    manifest_path: Path | None = None,
) -> dict:
    data = build_literal(harvest, manifest_path)
    if overlay:
        data = deep_apply_overlay(data, overlay)
    return data


def iter_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from iter_strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from iter_strings(value)


def find_sentinels(node, sentinels: tuple[str, ...] = DISHONEST_SENTINELS) -> list[str]:
    found: set[str] = set()
    for text in iter_strings(node):
        for sentinel in sentinels:
            if sentinel in text:
                found.add(sentinel)
    return sorted(found)


def write_js(path: Path, data: dict) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    path.write_text(f"window.LH_DATA = {payload};\n", encoding="utf-8")


def load_overlay(path: Path) -> dict:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise SystemExit(f"{path} must be a JSON object")
    return loaded


def write_private(data: dict) -> None:
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_js(OUT_JS, data)
    print(f"OK → {OUT_JSON.relative_to(ROOT)}")
    print(f"OK → {OUT_JS.relative_to(ROOT)}")
    print(f"clusters: {len(data['portrait']['clusters'])}, universe: {len(data['universe'])}")


def write_demo() -> None:
    if not DEMO_FIXTURE.is_dir():
        raise SystemExit(f"missing synthetic fixture: {DEMO_FIXTURE}")
    data = assemble(DEMO_FIXTURE, load_overlay(DEMO_OVERLAY))
    data["meta"]["demo"] = True
    data["meta"]["version"] = "0.4.2-demo"
    data["meta"]["asOf"] = "2026-11-25"
    data["meta"]["generated_at"] = "2026-11-25T00:00:00Z"
    leaked = find_sentinels(data)
    if leaked:
        raise SystemExit("demo snapshot contains dishonest sentinels: " + "; ".join(leaked))
    for title in DEFAULT_SIDE_QUESTS_REMOVED:
        if any(title in text for text in iter_strings(data)):
            raise SystemExit(f"demo snapshot contains removed default step: {title}")
    DEMO_JSON.parent.mkdir(parents=True, exist_ok=True)
    DEMO_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_js(DEMO_JS, data)
    print(f"OK → {DEMO_JSON.relative_to(ROOT)}")
    print(f"OK → {DEMO_JS.relative_to(ROOT)}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Build Live Harvest UI snapshot from harvest/")
    parser.add_argument(
        "--also-demo",
        action="store_true",
        help="FORBIDDEN for real personal data. Use --write-demo for the synthetic fixture.",
    )
    parser.add_argument(
        "--write-demo",
        action="store_true",
        help="Write harvest-ui/demo from demo/fixture and demo/overlay.demo.json only.",
    )
    parser.add_argument(
        "--manifest",
        default="",
        help="Optional snapshot-sources.yaml. The default file is used when present.",
    )
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Print source coverage JSON and do not write snapshot.json or data.js.",
    )
    args = parser.parse_args()
    manifest_path = Path(args.manifest) if args.manifest else None

    if args.coverage:
        _stdout_utf8()
        manifest = load_source_manifest(manifest_path)
        print(json.dumps(coverage_report(manifest, HARVEST), ensure_ascii=False, indent=2))
        return

    if args.also_demo:
        raise SystemExit(
            "Refusing --also-demo. Real harvest must not overwrite demo/. "
            "Run: python tools/lh_ui_snapshot.py --write-demo"
        )
    if args.write_demo:
        write_demo()
        return

    for path in (DEMO_JSON, DEMO_JS):
        if path.resolve() in {OUT_JSON.resolve(), OUT_JS.resolve()}:
            raise SystemExit("refusing to overwrite demo snapshot path")

    data = assemble(HARVEST, load_overlay(OVERLAY), manifest_path)
    leaked = find_sentinels(data)
    if leaked:
        raise SystemExit("snapshot contains dishonest sentinels: " + "; ".join(leaked))
    write_private(data)


if __name__ == "__main__":
    main()
