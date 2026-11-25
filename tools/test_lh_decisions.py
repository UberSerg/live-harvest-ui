"""Исход решения: pending, отказ на пяти старых, допись без стирания."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.lh_decisions import (
    LEGACY_RELS,
    DecisionWriteError,
    list_pending,
    record_outcome,
    split_document,
)

SCRIPT = ROOT / "tools" / "lh_decisions.py"
HARVEST = ROOT / "harvest"
DEMO = HARVEST / "Мозг" / "_system" / "DEMO — синтетическое решение.md"
TEMPLATE = HARVEST / "Мозг" / "_system" / "templates" / "Шаблон решения с исходом.md"
DEMO_BYTES = DEMO.read_bytes()
TEMPLATE_BYTES = TEMPLATE.read_bytes()
LEGACY_BYTES = {HARVEST / rel: (HARVEST / rel).read_bytes() for rel in LEGACY_RELS}

SAMPLE = """---
id: lh-20261125-t001
type: decision
created: 2026-11-25
updated: 2026-11-25
status: draft
source: "тест"
confidence: low
privacy: personal
related:
  - "[[Шаблон решения с исходом]]"
tags: [protocol]
aliases: []
synthetic: true
review_date: "2026-11-20"
expected_outcome: "Ожидание служебной проверки."
actual_outcome: ""
lesson: ""
outcome_status: pending
---

# Тестовое решение

## Проблема

Проблема служебная.

## Ожидаемый результат

Ожидание служебной проверки.

## Фактический результат

Пусто, пока человек не сообщил, что произошло.

## Урок

Пусто, пока нет фактического результата.

## История

- 2026-11-25 — карточка создана с ожиданием — тест
"""


def run(args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def write_card(folder: Path, rel: str, text: str) -> Path:
    path = folder / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class DecisionOutcomeTests(unittest.TestCase):
    def test_live_files_stay_byte_for_byte(self):
        self.assertEqual(DEMO.read_bytes(), DEMO_BYTES)
        self.assertEqual(TEMPLATE.read_bytes(), TEMPLATE_BYTES)
        for path, blob in LEGACY_BYTES.items():
            self.assertEqual(path.read_bytes(), blob)

    def test_live_pending_includes_demo_and_skips_legacy(self):
        report = list_pending(HARVEST, today=date(2026, 11, 25), due_only=False)
        paths = [row["path"] for row in report["pending"]]
        self.assertIn("Мозг/_system/DEMO — синтетическое решение.md", paths)
        for rel in LEGACY_RELS:
            self.assertNotIn(rel, paths)
        demo = next(row for row in report["pending"] if row["path"].endswith("DEMO — синтетическое решение.md"))
        self.assertEqual(demo["outcome_status"], "pending")
        self.assertTrue(demo["actual_empty"])
        self.assertTrue(demo["lesson_empty"])
        self.assertFalse(demo["due"])
        self.assertTrue(demo["synthetic"])
        self.assertEqual(report["legacy_skipped"], 5)
        due = list_pending(HARVEST, today=date(2026, 12, 9), due_only=True)
        due_paths = [row["path"] for row in due["pending"]]
        self.assertIn("Мозг/_system/DEMO — синтетическое решение.md", due_paths)

    def test_record_appends_without_erasing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_card(Path(tmp), "card.md", SAMPLE)
            before = path.read_text(encoding="utf-8")
            record_outcome(
                path,
                "сработало",
                "писать явно",
                when=date(2026, 11, 25),
                source="тест",
            )
            text = path.read_text(encoding="utf-8")
            fm, body, _inner = split_document(text)
            self.assertEqual(fm["actual_outcome"], "сработало")
            self.assertEqual(fm["lesson"], "писать явно")
            self.assertEqual(fm["outcome_status"], "reviewed")
            self.assertEqual(fm["expected_outcome"], "Ожидание служебной проверки.")
            self.assertEqual(str(fm["updated"]), "2026-11-25")
            self.assertIn("Проблема служебная.", body)
            self.assertIn("Ожидание служебной проверки.", body)
            self.assertIn("Пусто, пока человек не сообщил, что произошло.", body)
            self.assertIn("Пусто, пока нет фактического результата.", body)
            self.assertIn("сработало", body)
            self.assertIn("писать явно", body)
            self.assertIn("- 2026-11-25 — карточка создана с ожиданием — тест", body)
            self.assertIn("фактический результат: сработало", body)
            self.assertGreater(text.count("сработало"), before.count("сработало"))

    def test_second_record_keeps_first_outcome(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_card(Path(tmp), "card.md", SAMPLE)
            record_outcome(path, "факт один", "урок один", when=date(2026, 11, 25), source="тест")
            record_outcome(path, "факт два", "урок два", when=date(2026, 11, 26), source="тест")
            text = path.read_text(encoding="utf-8")
            fm, body, _inner = split_document(text)
            self.assertIn("факт один", fm["actual_outcome"])
            self.assertIn("факт два", fm["actual_outcome"])
            self.assertIn("урок один", fm["lesson"])
            self.assertIn("урок два", fm["lesson"])
            self.assertEqual(body.count("- 2026-11-25 — карточка создана с ожиданием — тест"), 1)
            self.assertIn("факт один", body)
            self.assertIn("факт два", body)
            self.assertEqual(fm["outcome_status"], "reviewed")

    def test_legacy_file_is_refused(self):
        path = HARVEST / "Решения" / "Решение — MVP стек Live Harvest.md"
        before = path.read_bytes()
        with self.assertRaises(DecisionWriteError):
            record_outcome(path, "факт", "урок", when=date(2026, 11, 25), source="тест")
        self.assertEqual(path.read_bytes(), before)

    def test_note_is_refused(self):
        before = TEMPLATE.read_bytes()
        with self.assertRaises(DecisionWriteError):
            record_outcome(TEMPLATE, "факт", "урок", when=date(2026, 11, 25), source="тест")
        self.assertEqual(TEMPLATE.read_bytes(), before)

    def test_list_filters_due_closed_and_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_card(root, "Решения/Решение — MVP стек Live Harvest.md", SAMPLE.replace("type: decision", "type: decision"))
            legacy = (root / "Решения" / "Решение — MVP стек Live Harvest.md").read_text(encoding="utf-8")
            legacy = legacy.replace("expected_outcome: \"Ожидание служебной проверки.\"\n", "")
            legacy = legacy.replace("actual_outcome: \"\"\n", "")
            legacy = legacy.replace("lesson: \"\"\n", "")
            legacy = legacy.replace("outcome_status: pending\n", "")
            (root / "Решения" / "Решение — MVP стек Live Harvest.md").write_text(legacy, encoding="utf-8")
            future = SAMPLE.replace('review_date: "2026-11-20"', 'review_date: "2026-12-09"')
            write_card(root, "Решения/Решение — позже.md", future)
            closed = SAMPLE.replace("outcome_status: pending", "outcome_status: reviewed")
            closed = closed.replace('actual_outcome: ""', 'actual_outcome: "уже есть"')
            closed = closed.replace('lesson: ""', 'lesson: "уже урок"')
            write_card(root, "Решения/Решение — закрыто.md", closed)
            bare = """---
id: lh-20261125-t002
type: decision
created: 2026-11-25
updated: 2026-11-25
status: draft
source: "тест"
confidence: low
privacy: personal
tags: []
aliases: []
---

# Без полей

## Суть

Служебная дыра.
"""
            write_card(root, "Решения/Решение — без полей.md", bare)
            write_card(
                root,
                "notes/не-решение.md",
                SAMPLE.replace("type: decision", "type: note").replace("outcome_status: pending", "outcome_status: not_applicable"),
            )
            report = list_pending(root, today=date(2026, 11, 25), due_only=False, include_legacy=True)
            paths = {row["path"] for row in report["pending"]}
            self.assertIn("Решения/Решение — позже.md", paths)
            self.assertIn("Решения/Решение — без полей.md", paths)
            self.assertNotIn("Решения/Решение — закрыто.md", paths)
            self.assertNotIn("Решения/Решение — MVP стек Live Harvest.md", paths)
            self.assertNotIn("notes/не-решение.md", paths)
            reasons = {row["path"]: row["reason"] for row in report["pending"]}
            self.assertEqual(reasons["Решения/Решение — без полей.md"], "missing_outcome_fields")
            legacy_paths = {row["path"] for row in report["legacy"]}
            self.assertIn("Решения/Решение — MVP стек Live Harvest.md", legacy_paths)
            due = list_pending(root, today=date(2026, 11, 25), due_only=True)
            due_paths = {row["path"] for row in due["pending"]}
            self.assertNotIn("Решения/Решение — позже.md", due_paths)
            self.assertNotIn("Решения/Решение — без полей.md", due_paths)
            # SAMPLE itself was overwritten as the legacy file; the due sample is «позже».
            # A past review_date is covered by rewriting a third card.
            past = SAMPLE.replace("id: lh-20261125-t001", "id: lh-20261125-t003")
            write_card(root, "Решения/Решение — срок.md", past)
            due_past = list_pending(root, today=date(2026, 11, 25), due_only=True)
            self.assertIn("Решения/Решение — срок.md", {row["path"] for row in due_past["pending"]})

    def test_cli_list_and_record(self):
        code, out, err = run(["list-pending", "--today", "2026-11-25"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        paths = [row["path"] for row in payload["pending"]]
        self.assertTrue(any(path.endswith("DEMO — синтетическое решение.md") for path in paths))
        for rel in LEGACY_RELS:
            self.assertNotIn(rel, paths)
        with tempfile.TemporaryDirectory() as tmp:
            path = write_card(Path(tmp), "card.md", SAMPLE)
            code, out, err = run(
                [
                    "record-outcome",
                    "--file",
                    str(path),
                    "--actual",
                    "сработало",
                    "--lesson",
                    "писать явно",
                    "--date",
                    "2026-11-25",
                ]
            )
            self.assertEqual(code, 0, err)
            text = path.read_text(encoding="utf-8")
            self.assertIn("outcome_status: reviewed", text)
            self.assertIn("Ожидание служебной проверки.", text)
            self.assertIn("карточка создана с ожиданием", text)
        code, _out, err = run(
            ["record-outcome", "--file", str(DEMO), "--actual", " ", "--lesson", " ", "--date", "2026-11-25"]
        )
        self.assertEqual(code, 1)
        self.assertIn("непустые", err)
        self.assertEqual(DEMO.read_bytes(), DEMO_BYTES)


if __name__ == "__main__":
    unittest.main()
