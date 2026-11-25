"""Очередь STM: сухой прогон ничего не пишет, NEEDS-REVIEW не сливается."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "lh_consolidate.py"


def load_consolidate():
    spec = importlib.util.spec_from_file_location("lh_consolidate", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def card(title: str, aliases: list[str] | None = None) -> str:
    alias_lines = "\n".join(f'  - "{alias}"' for alias in aliases or [])
    alias_block = f"aliases:\n{alias_lines}\n" if aliases else "aliases: []\n"
    return (
        "---\n"
        "id: lh-20261125-test\n"
        "type: note\n"
        "created: 2026-11-25\n"
        "updated: 2026-11-25\n"
        "status: draft\n"
        'source: "тест"\n'
        "confidence: low\n"
        "privacy: personal\n"
        "tags: []\n"
        f"{alias_block}"
        "---\n"
        f"# {title}\n\nТело карточки не должно попасть в план.\n"
    )


def queue_item(
    queue_id: str,
    queue_status: str,
    proposed: str,
    category: str = "",
    link_only: bool = False,
) -> str:
    link = "true" if link_only else "false"
    category_line = f'audit_category: "{category}"\n' if category else "audit_category: \"\"\n"
    return (
        "---\n"
        "id: lh-20261125-qitm\n"
        "type: note\n"
        "created: 2026-11-25\n"
        "updated: 2026-11-25\n"
        "status: draft\n"
        'source: "тест очереди"\n'
        "confidence: low\n"
        "privacy: personal\n"
        f"queue_id: {queue_id}\n"
        f"queue_status: {queue_status}\n"
        f"proposed_name: \"{proposed}\"\n"
        "target_card: \"\"\n"
        f"{category_line}"
        f"allow_link_only: {link}\n"
        "synthetic: true\n"
        "tags: []\n"
        "aliases: []\n"
        "---\n"
        f"# {queue_id}\n\nСинтетическая запись очереди.\n"
    )


def build_fixture(tmp: Path, pair_stem: str) -> dict[str, Path]:
    harvest = tmp / "harvest"
    living = harvest / "Заметки" / "Живая карточка.md"
    write(living, card("Живая карточка", ["Живой alias"]))
    write(
        harvest / "INDEX.md",
        "# Индекс\n\n- SEED-LINE-SECRET [[Живая карточка]]\n- [[Только в индексе]]\n",
    )
    write(
        harvest / "Мозг" / "_system" / "journals" / "Журнал консолидации.md",
        "---\n"
        "id: lh-20261125-jidx\n"
        "type: note\n"
        "created: 2026-11-25\n"
        "updated: 2026-11-25\n"
        "status: active\n"
        'source: "тест"\n'
        "confidence: high\n"
        "privacy: personal\n"
        "tags: []\n"
        "aliases: []\n"
        "---\n"
        "# Журнал консолидации\n\n## Записи\n\n"
        "<!-- lh-journal-entries -->\n"
        "<!-- /lh-journal-entries -->\n",
    )
    items = harvest / "Мозг" / "_system" / "stm" / "items"
    write(items / "a-hold.md", queue_item("a", "new", "Синтетическое имя без карточки"))
    write(
        items / "b-review.md",
        queue_item("b", "new", "Живая карточка", "NEEDS-REVIEW", link_only=True),
    )
    write(items / "c-collision.md", queue_item("c", "new", "Живая карточка"))
    write(
        items / "d-pair.md",
        queue_item("d", "new", pair_stem, "SAFE-CONSOLIDATION", link_only=True),
    )
    write(items / "e-link.md", queue_item("e", "pending_review", "Живой alias", link_only=True))
    write(items / "f-bad.md", queue_item("f", "banana", "Другое синтетическое имя"))
    write(
        harvest / "Мозг" / "_system" / "session" / "CURRENT.md",
        "---\n"
        "active_task: тестовая задача\n"
        "active_goal: тестовая цель\n"
        "open_questions:\n"
        "  - вопрос без факта\n"
        "relevant_cards:\n"
        "  - \"[[Живая карточка]]\"\n"
        "research_session:\n"
        "  state: idle\n"
        "---\n"
        "СЕКРЕТ-ТЕЛА-НЕ-ПЕЧАТАТЬ\n",
    )
    return {"harvest": harvest, "living": living, "items": items}


def run_cli(args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    module = load_consolidate()
    scan = (ROOT / "tools" / "lh_harvest_audit_scan.py").read_text(encoding="utf-8")
    for left, right in module.SAFE_PAIRS:
        assert left in scan and right in scan, (left, right)
    assert module.transition_allowed("discovered", "proposed")
    assert not module.transition_allowed("discovered", "supported")
    assert not module.transition_allowed("refuted", "supported")
    assert module.transition_allowed("refuted", "archived")
    assert "refuted" in module.HYPOTHESIS_STATUSES
    assert "archived" in module.HYPOTHESIS_STATUSES

    import tempfile

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        fixture = build_fixture(tmp, Path(module.SAFE_PAIRS[0][0]).stem)
        harvest = fixture["harvest"]
        living_hash = digest(fixture["living"])
        before = {
            path: path.read_bytes()
            for path in (harvest / "Мозг" / "_system" / "stm" / "items").glob("*.md")
        }
        code, out, err = run_cli(["--harvest", str(harvest), "--dry-run"])
        assert code == 0, err
        dry = json.loads(out)
        assert dry["dry_run"] is True
        assert dry["merge"] is False
        assert "SEED-LINE-SECRET" not in out
        assert "Тело карточки" not in out
        by_id = {plan["queue_id"]: plan for plan in dry["plans"]}
        assert by_id["b"]["decision"] == "block-review"
        assert by_id["b"]["next_status"] != "consolidated"
        assert by_id["b"]["merge"] is False
        assert "needs-review" in by_id["b"]["blockers"]
        assert by_id["d"]["next_status"] != "consolidated"
        assert "safe-pair-member" in by_id["d"]["blockers"] or "safe-consolidation" in by_id["d"]["blockers"]
        assert by_id["c"]["decision"] == "block-collision"
        assert any(hit["reason"] == "exact-stem" for hit in by_id["c"]["collisions"])
        assert any(hit["reason"] == "index-wikilink" for hit in by_id["c"]["collisions"])
        assert by_id["e"]["decision"] == "link-only"
        assert by_id["e"]["merge"] is False
        assert by_id["a"]["decision"] == "hold"
        assert by_id["f"]["decision"] == "repair-status"
        after_dry = {
            path: path.read_bytes()
            for path in (harvest / "Мозг" / "_system" / "stm" / "items").glob("*.md")
        }
        assert before == after_dry
        assert digest(fixture["living"]) == living_hash
        journals = list((harvest / "Мозг" / "_system" / "journals").glob("Журнал консолидации — *.md"))
        assert journals == []

        code, out, err = run_cli(["--harvest", str(harvest), "--apply"])
        assert code == 0, err
        applied = json.loads(out)
        assert applied["dry_run"] is False
        assert applied["merge"] is False
        assert "SEED-LINE-SECRET" not in out
        assert digest(fixture["living"]) == living_hash
        fresh = {
            path.name: path.read_text(encoding="utf-8")
            for path in (harvest / "Мозг" / "_system" / "stm" / "items").glob("*.md")
        }
        assert "queue_status: pending_review" in fresh["b-review.md"]
        assert "queue_status: consolidated" not in fresh["b-review.md"]
        assert "queue_status: pending_review" in fresh["c-collision.md"]
        assert "queue_status: consolidated" in fresh["e-link.md"]
        assert "слияние не делалось" in fresh["e-link.md"]
        assert "Тело карточки" not in fresh["e-link.md"]
        journal = Path(harvest / applied["journal"])
        assert journal.exists()
        journal_text = journal.read_text(encoding="utf-8")
        assert "SEED-LINE-SECRET" not in journal_text
        assert "Тело карточки" not in journal_text
        index_text = (harvest / "Мозг" / "_system" / "journals" / "Журнал консолидации.md").read_text(
            encoding="utf-8"
        )
        assert f"[[{journal.stem}]]" in index_text

        code, out, err = run_cli(
            [
                "--session",
                "--session-file",
                str(harvest / "Мозг" / "_system" / "session" / "CURRENT.md"),
            ]
        )
        assert code == 0, err
        view = json.loads(out)
        assert view["active_task"] == "тестовая задача"
        assert "СЕКРЕТ-ТЕЛА-НЕ-ПЕЧАТАТЬ" not in out

        code, out, err = run_cli(["--hypothesis-from", "discovered", "--hypothesis-to", "supported"])
        assert code == 0, err
        hypo = json.loads(out)
        assert hypo["allowed"] is False
        assert hypo["applied"] is False

        code, out, err = run_cli(["--mode", "weekly", "--harvest", str(harvest)])
        assert code == 1, out

        try:
            module.assert_writable(
                fixture["living"],
                harvest / "Мозг" / "_system" / "stm" / "items",
                harvest / "Мозг" / "_system" / "journals",
            )
        except RuntimeError:
            pass
        else:
            raise AssertionError("запись в предметную карточку не была отвергнута")

    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
