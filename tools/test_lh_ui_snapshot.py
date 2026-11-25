"""Честность снимка: пустая секция не получает заготовки, снятые заготовки не возвращаются."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "lh_ui_snapshot.py"


def load_module():
    spec = importlib.util.spec_from_file_location("lh_ui_snapshot", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def items(data: dict):
    for cluster in data["portrait"]["clusters"]:
        for item in cluster.get("items") or []:
            yield cluster["id"], item


def load_data_js(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    prefix = "window.LH_DATA = "
    if not raw.startswith(prefix):
        raise AssertionError(f"missing LH_DATA prefix: {path}")
    body = raw[len(prefix) :].strip()
    if body.endswith(";"):
        body = body[:-1]
    return json.loads(body)


def main() -> int:
    mod = load_module()
    empty_dir = Path(tempfile.mkdtemp(prefix="lh-snap-empty-"))
    empty = mod.assemble(empty_dir, {})
    leaked = mod.find_sentinels(empty)
    assert not leaked, leaked
    assert empty["profile"]["name"] is None
    assert empty["profile"]["role"] is None
    assert empty["profile"]["stage"] is None
    assert empty["profile"]["focus"] is None
    assert empty["profile"]["motto"] is None
    assert empty["profile"]["values"] == []
    assert empty["mainQuest"]["title"] is None
    assert empty["mainQuest"]["detail"] is None
    assert empty["mainQuest"]["checkpoint"] is None
    assert empty["sideQuests"] == []
    assert empty["razvivator"]["text"] is None
    assert empty["razvivator"]["source"] is None
    assert empty["progress"]["achievements"] == []
    assert empty["progress"]["measurable"] == []
    assert empty["portrait"]["history"] == []
    assert empty["recent"] == []
    assert all(not cluster["items"] for cluster in empty["portrait"]["clusters"])
    assert not any(item["ep"] == "fact" for _, item in items(empty))
    blob = json.dumps(empty, ensure_ascii=False)
    for title in mod.DEFAULT_SIDE_QUESTS_REMOVED:
        assert title not in blob

    fixture = Path(tempfile.mkdtemp(prefix="lh-snap-fixture-"))
    write(
        fixture,
        "Личность/Ценности и понимание свободы.md",
        "# Ценности\n\n## Факты\n\n- Ключевые ценности: свобода, семья.\n",
    )
    write(
        fixture,
        "Личность/Принятие решений и отношение к ошибкам.md",
        "# Решения\n\n## Факты\n\n- Строка факта только из фикстуры.\n\n"
        "## Гипотезы\n\n- Гипотеза только из фикстуры.\n",
    )
    write(
        fixture,
        "Цели/Аренда в Москве — переезд с дочерью.md",
        "# Аренда\n\n## Суть\n\nБлижайший шаг — аренда в Москве\n\n"
        "## Факты\n\n- Файл аренды есть, точку из него не назначать.\n",
    )
    write(
        fixture,
        "Финансы/Кеш — текущий.md",
        "# Кеш\n\n## Суть\n\nФайл кеша без пункта фактов.\n",
    )
    built = mod.assemble(fixture, {})
    leaked = mod.find_sentinels(built)
    assert not leaked, leaked
    assert built["mainQuest"]["checkpoint"] is None
    assert built["profile"]["values"] == ["свобода", "семья"]
    assert "Спокойствие" not in built["profile"]["values"]
    assert "Честность" not in built["profile"]["values"]
    mind = next(cluster for cluster in built["portrait"]["clusters"] if cluster["id"] == "mind")
    texts = [item["text"] for item in mind["items"]]
    assert texts == [
        "Строка факта только из фикстуры.",
        "Гипотеза только из фикстуры.",
    ]
    assert [item["ep"] for item in mind["items"]] == ["fact", "hypo"]
    finance = next(node for node in built["universe"] if node["id"] == "finance")
    assert finance["blurb"] is None
    assert finance["status"] == "empty"
    assert "Свободных денег мало для покупки/дома." not in json.dumps(built, ensure_ascii=False)

    focused = mod.assemble(
        fixture,
        {
            "profile": {
                "focus": {
                    "value": "явный фокус из overlay",
                    "mode": "interpreted",
                    "source": "test overlay",
                }
            }
        },
    )
    assert focused["profile"]["focus"] == "явный фокус из overlay"
    assert focused["profile"]["_fields"]["focus"]["mode"] == "interpreted"
    assert "Собрать Life OS, которым хочется пользоваться каждый день" not in json.dumps(
        focused, ensure_ascii=False
    )

    live = mod.build_literal(mod.HARVEST)
    leaked = mod.find_sentinels(live)
    assert not leaked, leaked
    assert live["profile"]["stage"] is None
    assert live["profile"]["focus"] is None
    assert live["mainQuest"]["checkpoint"] is None
    assert live["mainQuest"]["detail"] is None
    assert live["razvivator"]["text"] is None
    assert live["sideQuests"] == []
    assert live["progress"]["achievements"] == []
    assert live["portrait"]["history"] == []
    live_blob = json.dumps(live, ensure_ascii=False)
    for title in mod.DEFAULT_SIDE_QUESTS_REMOVED:
        assert title not in live_blob

    demo_path = mod.DEMO_JSON
    demo = json.loads(demo_path.read_text(encoding="utf-8"))
    leaked = mod.find_sentinels(demo)
    assert not leaked, leaked
    assert demo["meta"]["demo"] is True
    assert demo["mainQuest"]["checkpoint"] is None
    assert "Сергей" not in json.dumps(demo, ensure_ascii=False)
    demo_js = load_data_js(mod.DEMO_JS)
    assert demo_js == demo

    snapshot = json.loads(mod.OUT_JSON.read_text(encoding="utf-8"))
    leaked = mod.find_sentinels(snapshot)
    assert not leaked, leaked
    embedded = load_data_js(mod.OUT_JS)
    assert embedded == snapshot

    print("ok")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as exc:
        print("FAIL", str(exc).encode("unicode_escape").decode())
        sys.exit(1)
