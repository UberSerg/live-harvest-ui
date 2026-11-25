"""Эксперимент: active/pending, отказ на бланке, допись результата без стирания."""

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

from tools.lh_experiments import (
    TEMPLATE_RELS,
    ExperimentWriteError,
    list_active,
    list_pending,
    record_result,
    split_document,
)

SCRIPT = ROOT / "tools" / "lh_experiments.py"
HARVEST = ROOT / "harvest"
DEMO = HARVEST / "Мозг" / "_system" / "DEMO — синтетический эксперимент.md"
TEMPLATE = HARVEST / "Мозг" / "_system" / "templates" / "Шаблон эксперимента.md"
GOAL = HARVEST / "Цели" / "Образ желаемой жизни.md"
DEMO_BYTES = DEMO.read_bytes()
TEMPLATE_BYTES = TEMPLATE.read_bytes()
GOAL_BYTES = GOAL.read_bytes()

SAMPLE = """---
id: lh-20261125-x001
type: note
created: 2026-11-25
updated: 2026-11-25
status: draft
source: "тест"
confidence: low
privacy: personal
related:
  - "[[Шаблон эксперимента]]"
tags: [protocol]
aliases: []
synthetic: true
experiment_status: pending_review
review_date: "2026-11-20"
---

# Тестовый эксперимент

## Гипотеза

Служебное ожидание.

## Действие

Шаг служебный.

## Период

2026-11-20.

## Критерии успеха

Сигнал служебный.

## Наблюдения

Пусто, пока человек не сообщил, что происходило.

## Фактический результат

Пусто, пока человек не сообщил, что вышло.

## Продолжать / остановить

Ещё не решено.

## Связанные сущности

Ссылки на цель нет.

## История

- 2026-11-25 — карточка создана — тест
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


class ExperimentResultTests(unittest.TestCase):
    def test_live_files_stay_byte_for_byte(self):
        self.assertEqual(DEMO.read_bytes(), DEMO_BYTES)
        self.assertEqual(TEMPLATE.read_bytes(), TEMPLATE_BYTES)
        self.assertEqual(GOAL.read_bytes(), GOAL_BYTES)

    def test_live_pending_includes_demo_and_skips_template(self):
        pending = list_pending(HARVEST, today=date(2026, 11, 25), due_only=False)
        paths = [row["path"] for row in pending["pending"]]
        self.assertIn("Мозг/_system/DEMO — синтетический эксперимент.md", paths)
        for rel in TEMPLATE_RELS:
            self.assertNotIn(rel, paths)
        demo = next(row for row in pending["pending"] if row["path"].endswith("DEMO — синтетический эксперимент.md"))
        self.assertEqual(demo["experiment_status"], "pending_review")
        self.assertTrue(demo["observations_empty"])
        self.assertTrue(demo["result_empty"])
        self.assertFalse(demo["due"])
        self.assertTrue(demo["synthetic"])
        self.assertEqual(pending["template_skipped"], 1)
        self.assertTrue(pending["ok"])
        active = list_active(HARVEST, today=date(2026, 11, 25), due_only=False)
        active_paths = [row["path"] for row in active["active"]]
        self.assertNotIn("Мозг/_system/DEMO — синтетический эксперимент.md", active_paths)
        for rel in TEMPLATE_RELS:
            self.assertNotIn(rel, active_paths)
        self.assertEqual(active["template_skipped"], 1)
        for row in pending["pending"] + active["active"]:
            self.assertFalse(row["path"].startswith("Цели/"))
            self.assertFalse(row["path"].startswith("Личность/"))
            self.assertFalse(row["path"].startswith("Решения/"))
        due = list_pending(HARVEST, today=date(2026, 11, 25), due_only=True)
        self.assertNotIn(
            "Мозг/_system/DEMO — синтетический эксперимент.md",
            [row["path"] for row in due["pending"]],
        )
        due_later = list_pending(HARVEST, today=date(2026, 12, 9), due_only=True)
        self.assertIn(
            "Мозг/_system/DEMO — синтетический эксперимент.md",
            [row["path"] for row in due_later["pending"]],
        )

    def test_record_appends_without_erasing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_card(Path(tmp), "card.md", SAMPLE)
            before = path.read_text(encoding="utf-8")
            record_result(path, "сработало", "yes", when=date(2026, 11, 25), source="тест")
            text = path.read_text(encoding="utf-8")
            fm, body, _inner = split_document(text)
            self.assertEqual(fm["actual_result"], "сработало")
            self.assertEqual(fm["continue_choice"], "continue")
            self.assertEqual(fm["experiment_status"], "running")
            self.assertEqual(fm["status"], "draft")
            self.assertEqual(str(fm["updated"]), "2026-11-25")
            self.assertEqual(fm["related"], ["[[Шаблон эксперимента]]"])
            self.assertIn("Служебное ожидание.", body)
            self.assertIn("Пусто, пока человек не сообщил, что происходило.", body)
            self.assertIn("Пусто, пока человек не сообщил, что вышло.", body)
            self.assertIn("Ещё не решено.", body)
            self.assertIn("сработало", body)
            self.assertIn("\ncontinue\n", body)
            self.assertIn("- 2026-11-25 — карточка создана — тест", body)
            self.assertIn("experiment_status pending_review → running", body)
            self.assertGreater(text.count("сработало"), before.count("сработало"))
            observations = body.split("## Фактический результат", 1)[0]
            self.assertNotIn("сработало", observations)

    def test_continue_no_sets_stopped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_card(Path(tmp), "card.md", SAMPLE)
            payload = record_result(path, "стоп", "no", when=date(2026, 11, 25), source="тест")
            self.assertEqual(payload["experiment_status"], "stopped")
            self.assertEqual(payload["continue"], "no")
            text = path.read_text(encoding="utf-8")
            self.assertIn("experiment_status: stopped", text)
            self.assertIn("\nstop\n", text)
            self.assertIn("status: draft", text)

    def test_second_record_keeps_first_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = write_card(root, "card.md", SAMPLE)
            record_result(path, "факт один", "yes", when=date(2026, 11, 25), source="тест")
            record_result(path, "факт два", "no", when=date(2026, 11, 26), source="тест")
            text = path.read_text(encoding="utf-8")
            fm, body, _inner = split_document(text)
            self.assertIn("факт один", fm["actual_result"])
            self.assertIn("факт два", fm["actual_result"])
            self.assertEqual(fm["experiment_status"], "stopped")
            self.assertEqual(fm["continue_choice"], "stop")
            self.assertEqual(body.count("- 2026-11-25 — карточка создана — тест"), 1)
            self.assertIn("факт один", body)
            self.assertIn("факт два", body)
            self.assertIn("pending_review → running", body)
            self.assertIn("running → stopped", body)
            active = list_active(root, today=date(2026, 11, 26))
            pending = list_pending(root, today=date(2026, 11, 26))
            self.assertEqual(active["active"], [])
            self.assertEqual(pending["pending"], [])

    def test_template_goal_and_blank_result_are_refused(self):
        self.assertNotIn(b"experiment_status:", GOAL_BYTES)
        with self.assertRaises(ExperimentWriteError):
            record_result(TEMPLATE, "факт", "yes", when=date(2026, 11, 25), source="тест")
        with self.assertRaises(ExperimentWriteError):
            record_result(GOAL, "факт", "yes", when=date(2026, 11, 25), source="тест")
        with tempfile.TemporaryDirectory() as tmp:
            path = write_card(Path(tmp), "card.md", SAMPLE)
            before = path.read_bytes()
            with self.assertRaises(ExperimentWriteError):
                record_result(path, "  ", "yes", when=date(2026, 11, 25), source="тест")
            with self.assertRaises(ExperimentWriteError):
                record_result(path, "факт", "maybe", when=date(2026, 11, 25), source="тест")
            self.assertEqual(path.read_bytes(), before)
        self.assertEqual(TEMPLATE.read_bytes(), TEMPLATE_BYTES)
        self.assertEqual(GOAL.read_bytes(), GOAL_BYTES)

    def test_list_filters_status_and_due(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_card(root, "Мозг/_system/templates/Шаблон эксперимента.md", SAMPLE)
            future = SAMPLE.replace('review_date: "2026-11-20"', 'review_date: "2026-12-09"')
            future = future.replace("experiment_status: pending_review", "experiment_status: planned")
            future = future.replace("id: lh-20261125-x001", "id: lh-20261125-x002")
            write_card(root, "lab/план.md", future)
            running = SAMPLE.replace("experiment_status: pending_review", "experiment_status: running")
            running = running.replace("id: lh-20261125-x001", "id: lh-20261125-x003")
            write_card(root, "lab/ход.md", running)
            later = SAMPLE.replace('review_date: "2026-11-20"', 'review_date: "2026-12-09"')
            later = later.replace("id: lh-20261125-x001", "id: lh-20261125-x004")
            write_card(root, "lab/позже.md", later)
            stopped = SAMPLE.replace("experiment_status: pending_review", "experiment_status: stopped")
            stopped = stopped.replace("id: lh-20261125-x001", "id: lh-20261125-x005")
            write_card(root, "lab/стоп.md", stopped)
            plain = SAMPLE.replace("experiment_status: pending_review\n", "")
            plain = plain.replace("id: lh-20261125-x001", "id: lh-20261125-x006")
            write_card(root, "lab/заметка.md", plain)
            active = list_active(root, today=date(2026, 11, 25), due_only=False)
            pending = list_pending(root, today=date(2026, 11, 25), due_only=False)
            self.assertEqual(
                [row["path"] for row in active["active"]],
                ["lab/план.md", "lab/ход.md"],
            )
            self.assertEqual(
                [row["path"] for row in pending["pending"]],
                ["lab/позже.md"],
            )
            self.assertEqual(active["template_skipped"], 1)
            self.assertNotIn("lab/стоп.md", [row["path"] for row in active["active"] + pending["pending"]])
            self.assertNotIn("lab/заметка.md", [row["path"] for row in active["active"] + pending["pending"]])
            due_active = list_active(root, today=date(2026, 11, 25), due_only=True)
            self.assertEqual([row["path"] for row in due_active["active"]], ["lab/ход.md"])
            due_pending = list_pending(root, today=date(2026, 11, 25), due_only=True)
            self.assertEqual(due_pending["pending"], [])
            due_later = list_pending(root, today=date(2026, 12, 9), due_only=True)
            self.assertIn("lab/позже.md", [row["path"] for row in due_later["pending"]])

    def test_cli_list_and_record(self):
        code, out, err = run(["list-pending", "--today", "2026-11-25"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        paths = [row["path"] for row in payload["pending"]]
        self.assertTrue(any(path.endswith("DEMO — синтетический эксперимент.md") for path in paths))
        for rel in TEMPLATE_RELS:
            self.assertNotIn(rel, paths)
        code, out, err = run(["list-active", "--today", "2026-11-25"])
        self.assertEqual(code, 0, err)
        active = json.loads(out)
        self.assertFalse(
            any(path.endswith("DEMO — синтетический эксперимент.md") for path in (row["path"] for row in active["active"]))
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = write_card(Path(tmp), "card.md", SAMPLE)
            code, out, err = run(
                [
                    "record-result",
                    "--file",
                    str(path),
                    "--result",
                    "сработало",
                    "--continue",
                    "yes",
                    "--date",
                    "2026-11-25",
                ]
            )
            self.assertEqual(code, 0, err)
            text = path.read_text(encoding="utf-8")
            self.assertIn("experiment_status: running", text)
            self.assertIn("Служебное ожидание.", text)
            self.assertIn("карточка создана", text)
            recorded = json.loads(out)
            self.assertEqual(recorded["continue"], "yes")
            self.assertEqual(recorded["experiment_status"], "running")
        code, _out, err = run(
            [
                "record-result",
                "--file",
                str(DEMO),
                "--result",
                " ",
                "--continue",
                "yes",
                "--date",
                "2026-11-25",
            ]
        )
        self.assertEqual(code, 1)
        self.assertIn("непустой", err)
        self.assertEqual(DEMO.read_bytes(), DEMO_BYTES)


if __name__ == "__main__":
    unittest.main()
