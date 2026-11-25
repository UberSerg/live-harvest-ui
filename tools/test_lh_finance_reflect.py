"""Мост сверки: класс и флаги, без сумм. Живой API и ledger не вызываются."""

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

from tools.lh_finance_reflect import (
    DEFAULT_BASE,
    FinanceReflectError,
    Offline,
    collect_status,
    draft_observation,
    interpret_summary,
    probe,
    public_status,
    render_observation,
)

SCRIPT = ROOT / "tools" / "lh_finance_reflect.py"
FIXTURE = ROOT / "tools" / "fixtures" / "lh_finance" / "summary_poison.json"
TEMPLATE = ROOT / "harvest" / "Мозг" / "_system" / "templates" / "Шаблон финансового наблюдения.md"
DEMO = ROOT / "harvest" / "Мозг" / "_system" / "DEMO — синтетическое финансовое наблюдение.md"
POISON = (
    "987654321",
    "111111111",
    "250000",
    "9988",
    "SALARY",
    "зарплат",
    "руб",
    "USD",
    "****",
    "amount_minor",
    "balance",
)


def _blob(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _assert_clean(test: unittest.TestCase, text: str) -> None:
    for token in POISON:
        test.assertNotIn(token, text)


class FinanceReflectTests(unittest.TestCase):
    def test_module_does_not_load_capital(self) -> None:
        src = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("import tools.capital", src)
        self.assertNotIn("from tools.capital", src)
        self.assertNotIn("capital_api", src)
        self.assertEqual(DEFAULT_BASE, "http://127.0.0.1:8777")
        self.assertNotIn("tools.capital.store", sys.modules)
        self.assertNotIn("tools.capital_api", sys.modules)

    def test_poison_fixture_status_has_no_money(self) -> None:
        def fail_get(_path: str) -> dict:
            raise AssertionError("live api")

        report = collect_status(fixture=FIXTURE, get_json=fail_get)
        payload = public_status(report)
        text = _blob(payload)
        _assert_clean(self, text)
        self.assertEqual(payload["reachability"], "fixture")
        self.assertEqual(payload["reconciliation_status"], "matched")
        self.assertEqual(payload["message_class"], "matched")
        self.assertTrue(payload["completeness"]["liquid_complete"])
        self.assertFalse(payload["completeness"]["net_worth_complete"])
        self.assertFalse(payload["completeness"]["free_cash_complete"])
        self.assertFalse(payload["completeness"]["fx_complete"])
        self.assertFalse(payload["completeness"]["accounts_complete"])
        self.assertEqual(payload["period"], {"from": "2026-01-01", "to": "2026-11-25"})
        self.assertNotIn("message", payload)
        self.assertNotIn("balances", payload)

    def test_no_totals_and_dirty_token(self) -> None:
        quiet = interpret_summary(
            {"reconciliation": {"status": "no_totals", "message": "долг 42 руб"}}
        )
        self.assertEqual(quiet["reconciliation_status"], "missing")
        self.assertEqual(quiet["message_class"], "no_totals")
        _assert_clean(self, _blob(public_status(quiet)))

        mismatch = interpret_summary({"reconciliation": {"status": "mismatch"}})
        self.assertEqual(mismatch["reconciliation_status"], "mismatch")
        self.assertEqual(mismatch["message_class"], "mismatch")

        dirty = interpret_summary({"reconciliation": {"status": "mismatch 987654321"}})
        self.assertEqual(dirty["reconciliation_status"], "missing")
        self.assertEqual(dirty["message_class"], "missing")
        _assert_clean(self, _blob(public_status(dirty)))

    def test_non_bool_flags_and_dirty_period_dropped(self) -> None:
        report = interpret_summary(
            {
                "reconciliation": {"status": "matched", "message": "****9988"},
                "net_worth": {"liquid_complete": "987654321", "unknown_accounts": "****9988", "missing_fx": "USD"},
                "budget": {"free_cash_complete": False, "income_fact_minor": 25000000},
                "period": {"from": "2026-01-01", "to": "5000 руб"},
            }
        )
        self.assertNotIn("liquid_complete", report["completeness"])
        self.assertNotIn("accounts_complete", report["completeness"])
        self.assertNotIn("fx_complete", report["completeness"])
        self.assertIs(report["completeness"]["free_cash_complete"], False)
        self.assertEqual(report["period"], {"from": "2026-01-01"})
        _assert_clean(self, _blob(public_status(report)))

    def test_offline_and_health_do_not_echo_body(self) -> None:
        def down(_path: str) -> dict:
            raise Offline("connection refused 987654321")

        offline = probe(down)
        self.assertEqual(offline["reachability"], "offline")
        self.assertEqual(offline["detail"], "offline")
        self.assertIsNone(offline["reconciliation_status"])
        self.assertNotIn("987654321", _blob(public_status(offline)))

        def health_only(path: str) -> dict:
            if path == "/api/summary":
                raise Offline("offline")
            return {
                "ok": True,
                "version": "9.9.9",
                "balances": {"hidden": 123456789},
                "message": "зарплата 250000",
            }

        health = probe(health_only)
        self.assertEqual(health["reachability"], "online")
        self.assertEqual(health["source"], "health")
        self.assertEqual(health["detail"], "summary_unavailable")
        self.assertIsNone(health["reconciliation_status"])
        _assert_clean(self, _blob(public_status(health)))
        self.assertNotIn("9.9.9", _blob(public_status(health)))
        self.assertNotIn("123456789", _blob(public_status(health)))

    def test_draft_phrases_goal_and_no_advice(self) -> None:
        report = collect_status(fixture=FIXTURE)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "obs.md"
            payload = draft_observation(
                out,
                report,
                when=date(2026, 11, 25),
                goal="[[Reflection Engine]]",
                ident="ab12",
            )
            text = out.read_text(encoding="utf-8")
        _assert_clean(self, text)
        self.assertIn("сверка: matched", text)
        self.assertIn("что проверить", text)
        self.assertIn("## Гипотеза", text)
        self.assertIn("Пусто.", text)
        self.assertIn('hypothesis: ""', text)
        self.assertIn("[[Reflection Engine]]", text)
        self.assertIn("finance_observation_status: open", text)
        self.assertNotIn("рекоменд", text.casefold())
        self.assertNotIn("следует", text.casefold())
        self.assertEqual(payload["finance_observation_status"], "open")
        self.assertTrue(payload["synthetic"])
        self.assertNotIn("amount", text.casefold())
        self.assertNotIn("balance", text.casefold())

    def test_draft_refuses_ledger_template_and_overwrite(self) -> None:
        report = collect_status(fixture=FIXTURE)
        banned = ROOT / "harvest" / "Финансы" / "Капитал" / "lh-finance-reflect-should-not-exist.md"
        before = TEMPLATE.read_bytes()
        try:
            with self.assertRaises(FinanceReflectError):
                draft_observation(banned, report, when=date(2026, 11, 25), ident="aa01")
            self.assertFalse(banned.exists())
            with self.assertRaises(FinanceReflectError):
                draft_observation(TEMPLATE, report, when=date(2026, 11, 25), ident="aa02")
            self.assertEqual(TEMPLATE.read_bytes(), before)
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) / "obs.md"
                draft_observation(out, report, when=date(2026, 11, 25), ident="aa03")
                with self.assertRaises(FinanceReflectError):
                    draft_observation(out, report, when=date(2026, 11, 25), ident="aa04")
        finally:
            if banned.exists():
                banned.unlink()

    def test_stm_queue_fields_and_cleanup(self) -> None:
        report = interpret_summary({"reconciliation": {"status": "no_totals"}})
        out = ROOT / "harvest" / "Мозг" / "_system" / "stm" / "items" / "STM — lh-finance-reflect unittest.md"
        try:
            payload = draft_observation(out, report, when=date(2026, 11, 25), ident="stm1")
            text = out.read_text(encoding="utf-8")
            self.assertEqual(payload["kind"], "stm")
            self.assertIn("queue_status: new", text)
            self.assertIn("queue_id: stm-20261125-stm1", text)
            self.assertIn("сверка: missing", text)
            self.assertIn("message_class: no_totals", text)
            self.assertIn("что проверить", text)
            _assert_clean(self, text)
        finally:
            if out.exists():
                out.unlink()

    def test_cli_fixture_status_and_draft(self) -> None:
        status = subprocess.run(
            [sys.executable, str(SCRIPT), "status", "--fixture", str(FIXTURE)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(status.returncode, 0, status.stderr)
        _assert_clean(self, status.stdout)
        loaded = json.loads(status.stdout)
        self.assertEqual(loaded["reconciliation_status"], "matched")
        self.assertNotIn("transactions", loaded)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "draft.md"
            draft = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "draft-observation",
                    "--out",
                    str(out),
                    "--fixture",
                    str(FIXTURE),
                    "--date",
                    "2026-11-25",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=False,
            )
            self.assertEqual(draft.returncode, 0, draft.stderr)
            _assert_clean(self, draft.stdout)
            text = out.read_text(encoding="utf-8")
            _assert_clean(self, text)
            self.assertIn("сверка: matched", text)
            self.assertIn("что проверить", text)
            self.assertIn("Не задана.", text)

    def test_template_and_demo_have_no_amount_fields(self) -> None:
        template = TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("finance_observation_status: open", template)
        self.assertIn('goal: ""', template)
        self.assertIn('hypothesis: ""', template)
        self.assertIn("что проверить", template)
        self.assertNotIn("amount", template.casefold())
        self.assertNotIn("balance", template.casefold())
        self.assertNotIn("salary", template.casefold())
        self.assertNotIn("minor", template.casefold())
        demo = DEMO.read_text(encoding="utf-8")
        _assert_clean(self, demo)
        self.assertIn("сверка: matched", demo)
        self.assertIn("что проверить", demo)
        self.assertIn("finance_observation_status: open", demo)
        self.assertIn('hypothesis: ""', demo)
        self.assertIn("не с книг владельца", demo)
        self.assertNotIn("рекоменд", demo.casefold())


if __name__ == "__main__":
    unittest.main()
