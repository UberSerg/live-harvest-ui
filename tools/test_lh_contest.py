"""Маркер оспаривания: причина, история, молчание карточки без claim_track."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.lh_contest_check import claim_digest, contest_findings, significant_claim_text

SCRIPT = ROOT / "tools" / "lh_contest_check.py"
AUDIT = ROOT / "tools" / "lh_harvest_audit_scan.py"
DEMO = ROOT / "harvest" / "Мозг" / "_system" / "hypotheses" / "DEMO — синтетическая гипотеза.md"


def run(script: Path, args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def codes(text: str) -> set[str]:
    return {item["code"] for item in contest_findings(text, "card.md")}


def card(body: str, *, updated: str = "2026-11-25", track: bool = True, contested: bool = True, digest: str | None = None) -> str:
    pinned = claim_digest(significant_claim_text(body)) if digest is None else digest
    lines = [
        "---",
        "id: lh-20261125-ct01",
        "type: note",
        "created: 2026-11-25",
        f"updated: {updated}",
        "status: draft",
        'source: "тест"',
        "confidence: low",
        "privacy: personal",
        "tags: []",
        "aliases: []",
        "synthetic: true",
        f"claim_track: {'true' if track else 'false'}",
        f"contested: {'true' if contested else 'false'}",
        f'claim_digest: "{pinned}"',
        "---",
        "",
        body if body.endswith("\n") else body + "\n",
    ]
    return "\n".join(lines)


GOOD = """# Тест

## Формулировка

Служебная фраза синтетики.

## Оспаривание

- 2026-11-25 — оспорено — причина: проверка формы, не человек

## История

- 2026-11-25 — файл создан — тест
- 2026-11-25 — дописано оспаривание (оспорено), прежняя строка на месте — тест
"""


class ContestTests(unittest.TestCase):
    def test_valid_marker_is_silent(self):
        self.assertEqual(codes(card(GOOD)), set())

    def test_same_day_claim_change_without_history_arrow(self):
        changed = GOOD.replace("Служебная фраза синтетики.", "Другая служебная фраза.")
        digest = claim_digest(significant_claim_text(GOOD))
        found = codes(card(changed, digest=digest))
        self.assertIn("claim-digest-without-history", found)
        self.assertNotIn("claim-updated-without-history", found)

    def test_bumped_date_without_history_line(self):
        changed = GOOD.replace("Служебная фраза синтетики.", "Другая служебная фраза.")
        digest = claim_digest(significant_claim_text(GOOD))
        found = codes(card(changed, updated="2026-11-26", digest=digest))
        self.assertIn("claim-updated-without-history", found)
        self.assertIn("claim-digest-without-history", found)

    def test_digest_mismatch_waived_by_change_line(self):
        changed = GOOD.replace("Служебная фраза синтетики.", "Другая служебная фраза.")
        changed = changed.replace(
            "- 2026-11-25 — дописано оспаривание (оспорено), прежняя строка на месте — тест",
            "- 2026-11-25 — дописано оспаривание (оспорено), прежняя строка на месте — тест\n"
            "- 2026-11-26 — было → стало — тест",
        )
        digest = claim_digest(significant_claim_text(GOOD))
        self.assertEqual(codes(card(changed, updated="2026-11-26", digest=digest)), set())

    def test_contested_without_reason(self):
        body = GOOD.replace(
            "- 2026-11-25 — оспорено — причина: проверка формы, не человек",
            "Причины нет.",
        )
        found = codes(card(body, track=False))
        self.assertIn("contested-without-reason", found)
        self.assertNotIn("claim-updated-without-history", found)

    def test_dropped_history(self):
        body = GOOD.replace(
            "## История\n\n- 2026-11-25 — файл создан — тест\n"
            "- 2026-11-25 — дописано оспаривание (оспорено), прежняя строка на месте — тест\n",
            "",
        )
        found = codes(card(body, track=False))
        self.assertIn("contest-dropped-history", found)
        self.assertIn("contest-without-history-line", found)

    def test_legacy_card_without_flag_is_silent(self):
        text = """---
id: lh-20261125-leg1
type: note
created: 2026-11-25
updated: 2026-11-26
status: active
source: "тест"
confidence: low
privacy: personal
tags: []
aliases: []
---

# Личность

## Суть

Текст изменён без строки истории.

## История

- 2026-11-25 — создано — тест
"""
        self.assertEqual(contest_findings(text, "Личность/Пример.md"), [])

    def test_reversible_flag_keeps_record(self):
        self.assertEqual(codes(card(GOOD, track=False, contested=False)), set())

    def test_protocol_heading_without_flag_is_silent(self):
        text = """---
id: lh-20261125-doc1
type: note
created: 2026-11-25
updated: 2026-11-25
status: active
source: "тест"
confidence: high
privacy: personal
tags: []
aliases: []
---

# Правила

## Оспаривание

Так называется секция карточки. Это описание, не спор.
"""
        self.assertEqual(contest_findings(text, "Мозг/_system/Knowledge Audit.md"), [])

    def test_cli_nonzero_on_copy_and_zero_on_harvest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "card.md"
            path.write_text(
                card(GOOD, updated="2026-11-26", digest="0" * 64),
                encoding="utf-8",
            )
            code, out, err = run(SCRIPT, ["--file", str(path)])
            self.assertEqual(code, 1, err)
            payload = json.loads(out)
            self.assertFalse(payload["ok"])
            self.assertIn(
                "claim-updated-without-history",
                {item["code"] for item in payload["findings"]},
            )
            self.assertNotIn("hunter2", out)

        code, out, err = run(SCRIPT, ["--file", str(DEMO)])
        self.assertEqual(code, 0, err)
        self.assertTrue(json.loads(out)["ok"])

        code, out, err = run(SCRIPT, [])
        self.assertEqual(code, 0, err)
        self.assertTrue(json.loads(out)["ok"])

    def test_demo_keeps_original_history_line(self):
        text = DEMO.read_text(encoding="utf-8")
        self.assertIn("contested: true", text)
        self.assertIn("файл создан, чтобы цикл был виден на диске", text)
        self.assertIn("## Оспаривание", text)
        self.assertEqual(contest_findings(text, DEMO.name), [])

    def test_audit_scan_adds_no_contest_and_exits_zero(self):
        code, out, err = run(AUDIT, [])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        contest = [item for item in payload["findings"] if item["category"] == "CONTEST"]
        self.assertEqual(contest, [])
        self.assertNotIn("CONTEST", payload["counts"])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
