"""Capital ledger unit tests — run: python -m tools.capital.tests"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.capital import ledger
from tools.capital.money import convert_minor, from_minor, to_minor
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

    def test_convert(self):
        # 100.00 USD * 90 = 9000.00 RUB
        self.assertEqual(convert_minor(10000, "USD", "RUB", "90"), 900000)
        self.assertIsNone(convert_minor(10000, "USD", "RUB", None))


class LedgerTests(unittest.TestCase):
    def test_recurring_monthly(self):
        rec = [
            {"type": "income", "amount_minor": 380_000_00, "cadence": "monthly", "status": "planned"},
            {"type": "expense", "amount_minor": 26_500_00, "cadence": "monthly", "status": "planned"},
            {"type": "expense", "amount_minor": 10_000_00, "cadence": "monthly", "status": "planned"},
        ]
        m = ledger.recurring_monthly_net(rec)
        self.assertEqual(m["net_cashflow_minor"], 343_500_00)

    def test_transfer_not_income(self):
        accounts = [
            {"id": "a", "opening_balance_minor": 100_000, "opening_date": "2026-11-01", "balance_known": True},
            {"id": "b", "opening_balance_minor": 0, "opening_date": "2026-11-01", "balance_known": True},
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
        self.assertEqual(bal["a"]["balance_minor"], 60_000)
        self.assertEqual(bal["b"]["balance_minor"], 40_000)
        flows = ledger.period_flows(txs, "2026-11-01", "2026-11-30")
        self.assertEqual(flows["income_minor"], 0)
        self.assertEqual(flows["expense_minor"], 0)

    def test_income_expense(self):
        accounts = [{"id": "a", "opening_balance_minor": 0, "opening_date": "2026-11-01", "balance_known": True}]
        txs = [
            {"type": "income", "status": "actual", "amount_minor": 100_000, "account_id": "a", "date": "2026-11-02"},
            {"type": "expense", "status": "actual", "amount_minor": 30_000, "account_id": "a", "date": "2026-11-03"},
            {"type": "expense", "status": "planned", "amount_minor": 99_000, "account_id": "a", "date": "2026-11-04"},
        ]
        bal = ledger.account_balances(accounts, txs)
        self.assertEqual(bal["a"]["balance_minor"], 70_000)
        flows = ledger.period_flows(txs, "2026-11-01", "2026-11-30")
        self.assertEqual(flows["net_cashflow_minor"], 70_000)

    def test_void_ignored(self):
        accounts = [{"id": "a", "opening_balance_minor": 0, "opening_date": "2026-11-01", "balance_known": True}]
        txs = [
            {"type": "income", "status": "void", "amount_minor": 100_000, "account_id": "a", "date": "2026-11-02"},
        ]
        self.assertEqual(ledger.account_balances(accounts, txs)["a"]["balance_minor"], 0)

    def test_future_ops_excluded_from_balance(self):
        accounts = [{"id": "a", "opening_balance_minor": 1000, "opening_date": "2026-11-01", "balance_known": True}]
        txs = [
            {"type": "income", "status": "actual", "amount_minor": 5000, "account_id": "a", "date": "2026-12-01"},
        ]
        bal = ledger.account_balances(accounts, txs, as_of="2026-11-15")
        self.assertEqual(bal["a"]["balance_minor"], 1000)

    def test_unknown_balance_not_zero(self):
        accounts = [{"id": "a", "opening_balance_minor": 0, "opening_date": "2026-11-01", "balance_known": False}]
        bals = ledger.account_balances(accounts, [])
        self.assertIsNone(bals["a"]["balance_minor"])
        self.assertFalse(bals["a"]["known"])
        nw = ledger.net_worth(bals, [], [], [])
        self.assertEqual(nw["liquid_minor"], 0)
        self.assertFalse(nw["liquid_complete"])
        self.assertIn("a", nw["unknown_accounts"])

    def test_multicurrency_requires_fx(self):
        bals = {
            "rub": {"balance_minor": 100_000, "currency": "RUB", "known": True},
            "usd": {"balance_minor": 10000, "currency": "USD", "known": True},
        }
        nw = ledger.net_worth(bals, [], [], [], fx_rates=[])
        self.assertEqual(nw["liquid_minor"], 100_000)
        self.assertTrue(any("USD" in x for x in nw["missing_fx"]))
        rates = [{"from_currency": "USD", "to_currency": "RUB", "rate": "90", "date": "2026-11-01"}]
        nw2 = ledger.net_worth(bals, [], [], [], fx_rates=rates, as_of="2026-11-25")
        self.assertEqual(nw2["liquid_minor"], 100_000 + 900_000)

    def test_debt_principal_reduces_liability(self):
        lia = [{"id": "m", "principal_remaining_minor": 3_100_000_00, "principal_as_of": "2026-11-01", "currency": "RUB"}]
        txs = [
            {
                "type": "debt_principal",
                "status": "actual",
                "amount_minor": 10_000_00,
                "account_id": "a",
                "liability_id": "m",
                "date": "2026-11-10",
            },
            {
                "type": "debt_interest",
                "status": "actual",
                "amount_minor": 16_500_00,
                "account_id": "a",
                "liability_id": "m",
                "date": "2026-11-10",
            },
        ]
        m = ledger.liability_principals(lia, txs, as_of="2026-11-30")
        self.assertEqual(m["m"]["principal_remaining_minor"], 3_090_000_00)

    def test_debt_before_statement_ignored(self):
        lia = [{"id": "m", "principal_remaining_minor": 3_100_000_00, "principal_as_of": "2026-11-15"}]
        txs = [
            {
                "type": "debt_principal",
                "status": "actual",
                "amount_minor": 10_000_00,
                "liability_id": "m",
                "account_id": "a",
                "date": "2026-11-10",
            }
        ]
        m = ledger.liability_principals(lia, txs, as_of="2026-11-30")
        self.assertEqual(m["m"]["principal_remaining_minor"], 3_100_000_00)

    def test_no_double_count_recurring(self):
        rec = [{"id": "r1", "type": "income", "amount_minor": 100, "cadence": "monthly", "name": "salary"}]
        txs = [
            {
                "status": "planned",
                "type": "income",
                "amount_minor": 100,
                "date": "2026-11-01",
                "recurring_id": "r1",
            }
        ]
        p = ledger.planned_without_double_count(txs, rec, "2026-11-01", "2026-11-30")
        self.assertEqual(p["income_minor"], 100)
        self.assertEqual(len(p["unmaterialized"]), 0)

    def test_budget_unfilled(self):
        rec = [
            {"id": "r1", "type": "income", "amount_minor": 1000, "category_id": "c1", "name": "ЗП"},
            {"id": "r2", "type": "expense", "amount_minor": 200, "category_id": "c2", "name": "Ипотека"},
        ]
        cats = [
            {"id": "c1", "budget_bucket": "income_regular", "name": "Доход"},
            {"id": "c2", "budget_bucket": "expense_fixed", "name": "Жильё"},
        ]
        b = ledger.budget_view([], rec, cats, "2026-11-01", "2026-11-30")
        self.assertIn("Переменные расходы", b["unfilled_budget_lines"])
        self.assertFalse(b["free_cash_complete"])

    def test_net_worth_legacy(self):
        bals = {"a": 100_000}
        assets = [{"id": "house", "status": "estimated"}]
        vals = [{"asset_id": "house", "value_minor": 9_000_000_00, "status": "estimated", "date": "2026-10-21"}]
        lia = [{"id": "m", "principal_remaining_minor": 3_100_000_00}]
        nw = ledger.net_worth(bals, assets, lia, vals)
        self.assertEqual(nw["net_worth_minor"], 100_000 + 9_000_000_00 - 3_100_000_00)

    def test_scenario_no_invented_yield(self):
        r = ledger.project_scenario(
            {
                "monthly_income_minor": 100,
                "monthly_expense_minor": 40,
                "starting_capital_minor": 1000,
                "fi_target_minor": 2000,
            },
            months=24,
        )
        self.assertTrue(r["ok"])
        self.assertFalse(r["assumptions"]["yield_applied"])
        self.assertEqual(r["months_to_fi"], 17)  # +60/mo from 1000 → 2000


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
                "balance_known": True,
                "status": "actual",
            },
        )
        self.lia = self.store.upsert(
            "liability",
            {
                "name": "Mortgage",
                "currency": "RUB",
                "principal_remaining_minor": 1_000_000_00,
                "principal_as_of": "2026-11-01",
                "status": "estimated",
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

    def test_debt_payment_and_void(self):
        tx = self.store.upsert(
            "transaction",
            {
                "type": "debt_principal",
                "date": "2026-11-10",
                "amount_minor": 50_000_00,
                "currency": "RUB",
                "account_id": self.acc["id"],
                "liability_id": self.lia["id"],
                "status": "actual",
            },
        )
        s = self.store.summary("2026-11-01", "2026-11-30")
        self.assertEqual(s["liability_principals"][self.lia["id"]]["principal_remaining_minor"], 950_000_00)
        self.store.void_transaction(tx["id"], "undo")
        s2 = self.store.summary("2026-11-01", "2026-11-30")
        self.assertEqual(s2["liability_principals"][self.lia["id"]]["principal_remaining_minor"], 1_000_000_00)

    def test_materialize_and_confirm(self):
        rec = self.store.upsert(
            "recurring",
            {
                "name": "Salary",
                "type": "income",
                "amount_minor": 1000,
                "currency": "RUB",
                "cadence": "monthly",
                "account_id": self.acc["id"],
                "status": "planned",
            },
        )
        created = self.store.materialize_recurring("2026-11")
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0]["recurring_id"], rec["id"])
        self.assertEqual(created[0]["status"], "planned")
        # second call no dup
        self.assertEqual(len(self.store.materialize_recurring("2026-11")), 0)
        actual = self.store.confirm_planned(created[0]["id"])
        self.assertEqual(actual["status"], "actual")
        s = self.store.summary("2026-11-01", "2026-11-30")
        self.assertEqual(s["flows"]["income_minor"], 1000)

    def test_fx_and_persist(self):
        self.store.record_fx_rate("USD", "RUB", "92.5", "2026-11-20")
        usd = self.store.upsert(
            "account",
            {
                "name": "USD cash",
                "account_kind": "cash",
                "currency": "USD",
                "opening_balance_minor": 200000,  # 2000.00
                "opening_date": "2026-11-01",
                "balance_known": True,
                "status": "actual",
            },
        )
        s = self.store.summary("2026-11-01", "2026-11-30")
        # 2000 * 92.5 = 185000 RUB = 18500000 minor
        self.assertIn(usd["id"], s["balances"])
        self.assertGreater(s["net_worth"]["liquid_minor"], 0)
        self.assertTrue(s["net_worth"]["liquid_complete"] or usd["id"] not in s["net_worth"]["unknown_accounts"])

    def test_set_principal_bank(self):
        self.store.set_liability_principal(self.lia["id"], 2_900_000_00, "2026-11-20", note="bank app")
        s = self.store.summary("2026-11-01", "2026-11-30")
        self.assertEqual(s["liability_principals"][self.lia["id"]]["principal_remaining_minor"], 2_900_000_00)

    def test_idempotent_upsert(self):
        tx = {
            "type": "expense",
            "date": "2026-11-10",
            "amount_minor": 100,
            "currency": "RUB",
            "account_id": self.acc["id"],
            "status": "actual",
            "comment": "x",
        }
        a = self.store.upsert("transaction", dict(tx))
        dup = self.store.find_duplicate_tx({**tx, "id": "other"})
        self.assertEqual(dup["id"], a["id"])


if __name__ == "__main__":
    unittest.main()
