"""Capital ledger unit tests — run: python -m tools.capital.tests"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.capital import ledger
from tools.capital.money import from_minor, to_minor
from tools.capital.store import CapitalStore


class MoneyTests(unittest.TestCase):
    def test_to_minor(self):
        self.assertEqual(to_minor("1500.50", "RUB"), 150050)
        self.assertEqual(to_minor(150050), 150050)

    def test_reject_float(self):
        with self.assertRaises(TypeError):
            to_minor(1.5)  # type: ignore[arg-type]

    def test_roundtrip(self):
        self.assertEqual(from_minor(150050, "RUB"), "1500.50")


class LedgerTests(unittest.TestCase):
    def test_transfer_not_income(self):
        accounts = [
            {"id": "a", "opening_balance_minor": 100_000},
            {"id": "b", "opening_balance_minor": 0},
        ]
        txs = [
            {
                "id": "t1",
                "type": "transfer",
                "status": "actual",
                "amount_minor": 40_000,
                "account_id": "a",
                "counterparty_account_id": "b",
                "date": "2026-11-01",
            }
        ]
        bal = ledger.account_balances(accounts, txs)
        self.assertEqual(bal["a"], 60_000)
        self.assertEqual(bal["b"], 40_000)
        flows = ledger.period_flows(txs, "2026-11-01", "2026-11-30")
        self.assertEqual(flows["income_minor"], 0)
        self.assertEqual(flows["expense_minor"], 0)

    def test_income_expense(self):
        accounts = [{"id": "a", "opening_balance_minor": 0}]
        txs = [
            {"type": "income", "status": "actual", "amount_minor": 100_000, "account_id": "a", "date": "2026-11-02"},
            {"type": "expense", "status": "actual", "amount_minor": 30_000, "account_id": "a", "date": "2026-11-03"},
            {"type": "expense", "status": "planned", "amount_minor": 99_000, "account_id": "a", "date": "2026-11-04"},
        ]
        bal = ledger.account_balances(accounts, txs)
        self.assertEqual(bal["a"], 70_000)
        flows = ledger.period_flows(txs, "2026-11-01", "2026-11-30")
        self.assertEqual(flows["net_cashflow_minor"], 70_000)

    def test_void_ignored(self):
        accounts = [{"id": "a", "opening_balance_minor": 0}]
        txs = [
            {"type": "income", "status": "void", "amount_minor": 100_000, "account_id": "a", "date": "2026-11-02"},
        ]
        self.assertEqual(ledger.account_balances(accounts, txs)["a"], 0)

    def test_net_worth(self):
        bals = {"a": 100_000}
        assets = [{"id": "house", "status": "estimated"}]
        vals = [{"asset_id": "house", "value_minor": 9_000_000_00, "status": "estimated", "date": "2026-10-21"}]
        lia = [{"id": "m", "principal_remaining_minor": 3_100_000_00}]
        nw = ledger.net_worth(bals, assets, lia, vals)
        self.assertEqual(nw["net_worth_minor"], 100_000 + 9_000_000_00 - 3_100_000_00)
        self.assertTrue(nw["has_estimates"])


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = CapitalStore(self.tmp)
        self.acc = self.store.upsert(
            "account",
            {
                "name": "Test",
                "account_kind": "checking",
                "currency": "RUB",
                "opening_balance_minor": 0,
                "opening_date": "2026-11-01",
                "status": "actual",
            },
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_create_and_correct(self):
        tx = self.store.upsert(
            "transaction",
            {
                "type": "expense",
                "date": "2026-11-10",
                "amount_minor": 50000,
                "currency": "RUB",
                "account_id": self.acc["id"],
                "status": "actual",
                "comment": "coffee",
            },
        )
        new = self.store.correct_transaction(tx["id"], {"amount_minor": 45000}, "typo")
        self.assertEqual(new["amount_minor"], 45000)
        self.assertEqual(new["corrects_id"], tx["id"])
        old = self.store.get("transaction", tx["id"])
        self.assertEqual(old["status"], "void")
        s = self.store.summary("2026-11-01", "2026-11-30")
        self.assertEqual(s["flows"]["expense_minor"], 45000)


if __name__ == "__main__":
    unittest.main()
