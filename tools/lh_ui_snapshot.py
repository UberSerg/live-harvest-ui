#!/usr/bin/env python3
"""Build harvest-ui snapshot from harvest/ (literal) + overlay.json (interpreted)."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARVEST = ROOT / "harvest"
UI = ROOT / "harvest-ui"
OVERLAY = UI / "overlay.json"
OUT_JSON = UI / "snapshot.json"
OUT_JS = UI / "data.js"

UNIVERSE_BASE = [
    {"id": "family", "label": "Семья", "angle": -90, "status": "empty", "blurb": "Нет свежего среза в UI."},
    {"id": "finance", "label": "Финансы", "angle": -30, "status": "empty", "blurb": "Нет свежего среза в UI."},
    {"id": "health", "label": "Здоровье", "angle": 20, "status": "empty", "blurb": "Нет свежего среза в UI."},
    {"id": "projects", "label": "Проекты", "angle": 70, "status": "empty", "blurb": "Нет свежего среза в UI."},
    {"id": "work", "label": "Работа", "angle": 125, "status": "empty", "blurb": "Нет свежего среза в UI."},
    {"id": "learn", "label": "Обучение", "angle": 175, "status": "empty", "blurb": "Нет свежего среза в UI."},
    {"id": "rest", "label": "Отдых", "angle": 220, "status": "empty", "blurb": "Нет свежего среза в UI."},
]


def read_md(rel: str) -> str:
    path = HARVEST / rel
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def section_bullets(text: str, heading: str) -> list[str]:
    """Bullets under ## heading until next ##."""
    pat = rf"^##\s+{re.escape(heading)}\s*\n(.*?)(?=^##\s+|\Z)"
    m = re.search(pat, text, flags=re.M | re.S)
    if not m:
        return []
    body = m.group(1)
    items = []
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("- "):
            items.append(line[2:].strip())
    return items


def first_bullet_match(bullets: list[str], *needles: str) -> str | None:
    for b in bullets:
        low = b.lower()
        if all(n.lower() in low for n in needles):
            return b
    return None


def strip_wiki(s: str) -> str:
    return re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", s)


def lit(value, source: str):
    return {"value": value, "mode": "literal", "source": source}


def unwrap(field, default=None):
    if field is None:
        return default
    if isinstance(field, dict) and "value" in field:
        return field["value"]
    return field


def build_literal() -> dict:
    sergey = read_md("Личность/Сергей.md")
    values = read_md("Личность/Ценности и понимание свободы.md")
    work = read_md("Личность/Работа — тимлид 1С УХ.md")
    prof = read_md("Личность/Профессиональный профиль и карьерная мотивация.md")
    fin = read_md("Цели/Финансовая независимость и капитал.md")
    rent = read_md("Цели/Аренда в Москве — переезд с дочерью.md")
    interests = read_md("Личность/Интересы и отдых.md")
    decisions = read_md("Личность/Принятие решений и отношение к ошибкам.md")
    family = read_md("Связи/Семья.md")
    health = read_md("Личность/Здоровье привычки и эмоциональное состояние.md")
    waves = read_md("Личность/Волны вдохновения и фокус.md")
    create = read_md("Личность/Созидание деньги и управление.md")
    lh = read_md("Проекты/Live Harvest.md")
    cash = read_md("Финансы/Кеш — текущий.md")

    value_facts = section_bullets(values, "Факты")
    motto = "Когда я не беспокоюсь ни о чём"
    for b in value_facts:
        if "не беспокоюсь" in b.lower() or "критерий успеха" in b.lower():
            q = re.search(r"«([^»]+)»", b)
            if q:
                motto = q.group(1)
            break

    value_short = []
    for b in value_facts:
        if b.lower().startswith("ключевые ценности"):
            # "свобода, финансовая независимость, семья..."
            part = b.split(":", 1)[-1]
            value_short = [x.strip().rstrip(".") for x in part.split(",") if x.strip()]
            # keep first evocative words
            mapped = []
            for v in value_short:
                if "свобода" in v.lower():
                    mapped.append("Свобода")
                elif "семья" in v.lower():
                    mapped.append("Семья")
                elif "поко" in v.lower() or "безопас" in v.lower():
                    mapped.append("Спокойствие")
                elif "честн" in v.lower():
                    mapped.append("Честность")
            if "Честность" not in mapped:
                for b2 in value_facts:
                    if "честность" in b2.lower():
                        mapped.append("Честность")
                        break
            value_short = mapped or ["Свобода", "Семья"]
            break

    role = "Тимлид 1С · основатель Live Harvest"
    work_facts = section_bullets(work, "Факты")
    if work_facts:
        role = "Тимлид 1С УХ · основатель Live Harvest"

    checkpoint = "Ближайший шаг — аренда в Москве"
    if rent:
        checkpoint = "Ближайший шаг — аренда в Москве"

    main_title = "Финансовая независимость"
    main_detail = "Одна цель: капитал, дом и опциональность найма — грани одного намерения."
    fin_facts = section_bullets(fin, "Факты")
    if fin_facts:
        main_detail = strip_wiki(fin_facts[0])[:220]

    decision_facts = section_bullets(decisions, "Факты")
    mind_items = []
    for b in decision_facts:
        if "порядок принятия" in b.lower() or "анализ" in b.lower():
            mind_items.append({"ep": "fact", "text": strip_wiki(b).split(":", 1)[-1].strip() or strip_wiki(b)})
        if "ошибки" in b.lower():
            mind_items.append({"ep": "fact", "text": strip_wiki(b)})
    if not mind_items:
        mind_items = [
            {"ep": "fact", "text": "Анализ → внутренний отклик → эксперты → риски → решение"},
            {"ep": "fact", "text": "Ошибки сначала болезненны, затем выводы"},
        ]

    portrait_values = []
    for b in value_facts[:5]:
        portrait_values.append({"ep": "fact", "text": strip_wiki(b)})

    interest_facts = section_bullets(interests, "Факты")
    wave_list = []
    for b in interest_facts[:6]:
        wave_list.append(strip_wiki(b)[:60])
    if not wave_list:
        wave_list = ["Live Harvest", "ИИ / вайбкодинг", "Велосипед", "Dota 2 / WoW"]

    # Universe literals where clear
    universe = [dict(u) for u in UNIVERSE_BASE]
    by_id = {u["id"]: u for u in universe}

    if family:
        by_id["family"].update(
            {
                "status": "active",
                "blurb": "Семья — опора; переезд связан с работой жены.",
                "mode": "literal",
                "source": "[[Семья]]",
            }
        )
    if cash or fin:
        by_id["finance"].update(
            {
                "status": "watch",
                "blurb": "Свободных денег мало для покупки/дома." if cash else by_id["finance"]["blurb"],
                "mode": "literal",
                "source": "[[Кеш — текущий]] · [[Финансовая независимость и капитал]]",
            }
        )
    if health:
        hf = section_bullets(health, "Факты")
        by_id["health"].update(
            {
                "status": "active" if hf else "empty",
                "blurb": strip_wiki(hf[0])[:160] if hf else "Нет свежего среза в UI.",
                "mode": "literal" if hf else "literal",
                "source": "[[Здоровье привычки и эмоциональное состояние]]",
            }
        )
    if lh:
        by_id["projects"].update(
            {
                "status": "active",
                "blurb": "Live Harvest — приоритетный проект для заработка (монетизация открыта).",
                "mode": "literal",
                "source": "[[Live Harvest]]",
            }
        )
    if work or prof:
        by_id["work"].update(
            {
                "status": "active",
                "blurb": "Удалёнка, тимлид 1С УХ; найм как база.",
                "mode": "literal",
                "source": "[[Работа — тимлид 1С УХ]]",
            }
        )
    if prof:
        by_id["learn"].update(
            {
                "status": "active",
                "blurb": "ИИ, продукты, вайбкодинг — намерения развития.",
                "mode": "literal",
                "source": "[[Профессиональный профиль и карьерная мотивация]]",
            }
        )
    if waves or interests:
        by_id["rest"].update(
            {
                "status": "active" if interest_facts else "empty",
                "blurb": strip_wiki(interest_facts[0])[:160] if interest_facts else "Нет свежего среза в UI.",
                "mode": "literal",
                "source": "[[Интересы и отдых]]",
            }
        )

    create_cluster = None
    if create:
        cf = section_bullets(create, "Факты (самоописание в сценариях)") or section_bullets(create, "Факты")
        co = section_bullets(create, "Открытые вопросы")
        items = [{"ep": "fact", "text": strip_wiki(x)} for x in cf[:6]]
        for x in co[:2]:
            items.append({"ep": "open", "text": strip_wiki(x)})
        if items:
            create_cluster = {
                "id": "create",
                "title": "Созидание и управление",
                "mode": "literal",
                "source": "[[Созидание деньги и управление]]",
                "items": items,
            }

    history = [
        {"when": "2026-11-25", "text": "Challenge: созидание / деньги / управление"},
        {"when": "2026-11-25", "text": "Интервью → портрет"},
        {"when": "2026-11-25", "text": "Аренда = ближайший жилищный шаг"},
        {"when": "2026-11-24", "text": "Старт Live Harvest"},
    ]

    recent = [
        {"what": "Challenge-интервью поглощено в harvest/", "kind": "знание"},
        {"what": "CONTR-015: приоритет аренды", "kind": "решение"},
        {"what": "UI snapshot из harvest/", "kind": "продукт"},
    ]

    data = {
        "meta": {
            "version": "0.4.1",
            "asOf": str(date.today()),
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "product": "Personal Command Center",
            "snapshot": True,
            "ui_version": "0.4",
        },
        "profile": {
            "name": "Сергей",
            "role": role,
            "stage": "Переезд в Москву · продуктовый буст параллельно с наймом",
            "focus": "Собрать Life OS, которым хочется пользоваться каждый день",
            "values": value_short or ["Свобода", "Семья", "Спокойствие", "Честность"],
            "motto": motto,
            "_fields": {
                "name": lit("Сергей", "[[Сергей]]"),
                "motto": lit(motto, "[[Ценности и понимание свободы]]"),
                "role": lit(role, "[[Работа — тимлид 1С УХ]]"),
            },
        },
        "state": {"mood": None, "energy": None, "focus": None, "wave": None, "journal": None},
        "universe": universe,
        "mainQuest": {
            "title": main_title,
            "detail": main_detail,
            "checkpoint": checkpoint,
            "_fields": {
                "title": lit(main_title, "[[Финансовая независимость и капитал]]"),
                "checkpoint": lit(checkpoint, "[[Аренда в Москве — переезд с дочерью]]"),
            },
        },
        "sideQuests": [],
        "waves": wave_list,
        "razvivator": {
            "demo": True,
            "type": "вопрос",
            "text": "Что на этой неделе запускает и гасит твою волну вдохновения?",
            "mode": "interpreted",
            "source": "UI default until overlay",
        },
        "progress": {
            "achievements": [
                {"title": "Концепция Live Harvest", "when": "2026-11-24"},
                {"title": "Первый крупный импорт знаний", "when": "2026-11-24"},
                {"title": "Интервью → поглощение", "when": "2026-11-25"},
                {"title": "Challenge созидание/управление", "when": "2026-11-25"},
            ],
            "measurable": [
                {"label": "Жильё", "value": "Аренда МСК — ближайший шаг"},
                {"label": "Финцель", "value": "Единое намерение (не конфликт)"},
            ],
        },
        "recent": recent,
        "portrait": {
            "core": {
                "title": "Ядро",
                "lead": "Отец, тимлид, строитель персональных систем. Ищет свободу без потери опоры.",
                "mode": "interpreted",
                "source": "[[Сергей]] · [[Семья и отцовство]] · [[Ценности и понимание свободы]]",
            },
            "clusters": [
                {
                    "id": "values",
                    "title": "Ценности и принципы",
                    "mode": "literal",
                    "source": "[[Ценности и понимание свободы]]",
                    "items": portrait_values
                    or [
                        {"ep": "fact", "text": "Свобода, финансовая независимость, семья, безопасность и покой"},
                        {"ep": "fact", "text": "Честность и доброта"},
                        {"ep": "fact", "text": "Успех вне денег — отсутствие беспокойства"},
                    ],
                },
                {
                    "id": "drive",
                    "title": "Мотивация",
                    "mode": "literal",
                    "source": "[[Сергей]] · [[Live Harvest]]",
                    "items": [
                        {"ep": "intent", "text": "Систематизировать себя через Live Harvest"},
                        {"ep": "intent", "text": "Продуктовый буст при сохранении найма"},
                    ],
                },
                {
                    "id": "mind",
                    "title": "Мышление",
                    "mode": "literal",
                    "source": "[[Принятие решений и отношение к ошибкам]]",
                    "items": mind_items
                    + [{"ep": "hypo", "text": "Возможно, различает карьерный риск и риск капитала"}],
                },
                {
                    "id": "craft",
                    "title": "Компетенции",
                    "mode": "literal",
                    "source": "[[Профессиональный профиль и карьерная мотивация]]",
                    "items": [
                        {"ep": "fact", "text": "1С, аналитика, управление командой (самоописание)"},
                        {"ep": "intent", "text": "ИИ, робототехника, создание продуктов"},
                    ],
                },
                {
                    "id": "spark",
                    "title": "Интересы",
                    "mode": "literal",
                    "source": "[[Интересы и отдых]]",
                    "items": [
                        {
                            "ep": "fact",
                            "text": strip_wiki(interest_facts[0])
                            if interest_facts
                            else "Волейбол, велосипед, RPG/Dota/WoW, природа, стихи раньше",
                        }
                    ],
                },
                {
                    "id": "edge",
                    "title": "Сильные стороны",
                    "mode": "interpreted",
                    "source": "[[Сергей]] наблюдения",
                    "items": [{"ep": "fact", "text": "Прикладной результат, системная память контекста"}],
                },
                {
                    "id": "grow",
                    "title": "Зоны развития",
                    "mode": "literal",
                    "source": "[[Здоровье привычки и эмоциональное состояние]]",
                    "items": [
                        {
                            "ep": "intent",
                            "text": "Дисциплина, здоровье, отказ от курения; алкоголь — редкий или отказ",
                        },
                        {"ep": "open", "text": "Что помогало удерживать отказ раньше?"},
                    ],
                },
                {
                    "id": "tension",
                    "title": "Внутренние напряжения",
                    "mode": "literal",
                    "source": "[[Гипотезы для проверки при самопознании]] · RISK-001",
                    "items": [
                        {"ep": "hypo", "text": "Гипотезы ИИ по самопознанию — только к проверке"},
                        {"ep": "open", "text": "Волны вдохновения vs завершение важного"},
                        {
                            "ep": "hypo",
                            "text": "Делегирование vs контроль концепции / общая волна — риск, не CONTR",
                        },
                    ],
                },
                {
                    "id": "future",
                    "title": "Желаемый образ",
                    "mode": "literal",
                    "source": "[[Образ желаемой жизни]]",
                    "items": [
                        {
                            "ep": "intent",
                            "text": "Спокойный спортивный человек; семья; тёплое место; вайбкодинг по кайфу",
                        }
                    ],
                },
            ],
            "history": history,
        },
    }

    if create_cluster:
        # insert after drive
        clusters = data["portrait"]["clusters"]
        drive_i = next((i for i, c in enumerate(clusters) if c["id"] == "drive"), 1)
        clusters.insert(drive_i + 1, create_cluster)

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
    for u in data["universe"]:
        patch = uni_o.get(u["id"])
        if not patch:
            continue
        if "blurb" in patch:
            u["blurb"] = unwrap(patch["blurb"], u.get("blurb")) if isinstance(patch["blurb"], dict) else patch["blurb"]
        if "status" in patch:
            u["status"] = patch["status"]
        u["mode"] = patch.get("mode", u.get("mode", "interpreted"))
        u["source"] = patch.get("source", u.get("source"))

    if overlay.get("sideQuests"):
        data["sideQuests"] = [
            {
                "title": q["title"],
                "meta": q.get("meta", ""),
                "mode": q.get("mode", "interpreted"),
                "source": q.get("source"),
            }
            for q in overlay["sideQuests"]
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

    extras = overlay.get("portrait_clusters_extra") or []
    if extras:
        existing = {c["id"] for c in data["portrait"]["clusters"]}
        for extra in extras:
            if extra["id"] in existing:
                # replace
                data["portrait"]["clusters"] = [
                    extra if c["id"] == extra["id"] else c for c in data["portrait"]["clusters"]
                ]
            else:
                data["portrait"]["clusters"].insert(2, extra)

    prepend = overlay.get("recent_prepend") or []
    if prepend:
        data["recent"] = [
            {"what": r["what"], "kind": r.get("kind", "знание")} for r in prepend
        ] + data["recent"]

    return data


def write_js(data: dict) -> None:
    # Strip heavy _fields from runtime if desired — keep for transparency in JSON; JS can ignore
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    OUT_JS.write_text(f"window.LH_DATA = {payload};\n", encoding="utf-8")


def main() -> None:
    data = build_literal()
    overlay = {}
    if OVERLAY.exists():
        overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
    data = deep_apply_overlay(data, overlay)
    # default side quests if overlay empty
    if not data["sideQuests"]:
        data["sideQuests"] = [
            {"title": "Аренда в Москве + переезд с дочерью", "meta": "Ближайший жилищный шаг"},
            {"title": "Live Harvest как ежедневный Life OS", "meta": "Продуктовый клин"},
            {"title": "Первый измеримый этап монетизации", "meta": "Открытый вопрос"},
        ]
    OUT_JSON.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_js(data)
    print(f"OK → {OUT_JSON.relative_to(ROOT)}")
    print(f"OK → {OUT_JS.relative_to(ROOT)}")
    print(f"clusters: {len(data['portrait']['clusters'])}, universe: {len(data['universe'])}")


if __name__ == "__main__":
    main()
