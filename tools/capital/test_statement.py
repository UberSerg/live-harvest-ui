"""Statement import tests — synthetic only. python -m tools.capital.test_statement"""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from tools.capital import statement_parse
from tools.capital.gen_synthetic_statement import build
from tools.capital.statement_import import build_import_plan, execute_import, void_batch
from tools.capital.store import CapitalStore

SAMPLE = """ДАТА ОПЕРАЦИИ (МСК)
Дата обработки1
и код авторизации
КАТЕГОРИЯ
Описание операции
СУММА В ВАЛЮТЕ СЧЁТА
Сумма в валюте
операции2
24.11.2026 20:12 Супермаркеты 1 250,00
24.11.2026 123456 DEMO SHOP MOSCOW RUS. Операция по карте ****0001
24.11.2026 18:15 Рестораны и кафе 350,00
24.11.2026 654321 DEMO CAFE MOSCOW RUS. Операция по карте ****0001
Продолжение на следующей странице
Индивидуальная выписка по счёту дебетовой карты Страница 2 из 30
ДАТА ОПЕРАЦИИ (МСК)
Дата обработки1
и код авторизации
КАТЕГОРИЯ
Описание операции
СУММА В ВАЛЮТЕ СЧЁТА
Сумма в валюте
операции2
13.11.2026 15:31 Прочие операции +150 000,55
13.11.2026 345678 DEMO PAYMENT
"""


class ParseTests(unittest.TestCase):
    def test_sample(self):
        r = statement_parse.parse_statement(SAMPLE)
        self.assertEqual(r["count"], 3)
        ops = r["operations"]
        self.assertEqual(ops[0]["amount_minor"], 125000)
        self.assertEqual(ops[0]["direction"], "out")
        self.assertEqual(ops[0]["bank_category"], "Супермаркеты")
        self.assertEqual(ops[2]["direction"], "in")
        self.assertEqual(ops[2]["amount_minor"], 15000055)

    def test_page_break_mid_op(self):
        text = """01.10.2026 12:00 Супермаркеты 100,00
01.10.2026 111 DEMO SHOP
Продолжение на следующей странице
Индивидуальная выписка по счёту дебетовой карты Страница 2 из 2
ДАТА ОПЕРАЦИИ (МСК)
Дата обработки1
и код авторизации
КАТЕГОРИЯ
Описание операции
СУММА В ВАЛЮТЕ СЧЁТА
Сумма в валюте
операции2
PART TWO OF DESC
02.10.2026 13:00 Такси 200,00
02.10.2026 222 DEMO TAXI
"""
        r = statement_parse.parse_statement(text)
        self.assertEqual(r["count"], 2)
        self.assertIn("PART TWO", r["operations"][0]["description"])

    def test_synthetic_30p(self):
        text = build(30)
        r = statement_parse.parse_statement(text)
        self.assertGreaterEqual(r["count"], 300)
        self.assertLess(r["unrecognized_count"], r["count"] // 10)


class ImportStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = CapitalStore(self.tmp)
        self.acc = self.store.upsert(
            "account",
            {
                "name": "Demo Card",
                "account_kind": "checking",
                "currency": "RUB",
                "opening_balance_minor": None,
                "balance_known": False,
                "opening_date": "2026-01-01",
                "status": "actual",
            },
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_import_dedup_void(self):
        plan = build_import_plan(self.store, account_id=self.acc["id"], text=SAMPLE)
        self.assertTrue(plan["ok"], plan)
        res = execute_import(self.store, plan)
        self.assertEqual(res["imported"], 3)
        # categories created
        self.assertGreaterEqual(res["categories_created"], 1)
        # needs review for Прочие
        self.assertGreaterEqual(res["needs_review"], 1)
        # reimport
        plan2 = build_import_plan(self.store, account_id=self.acc["id"], text=SAMPLE)
        res2 = execute_import(self.store, plan2)
        self.assertEqual(res2["imported"], 0)
        self.assertEqual(res2["duplicates_skipped"], 3)
        # void
        void_batch(self.store, res["batch_id"])
        active = [t for t in self.store.list_kind("transaction") if t.get("status") != "void"]
        self.assertEqual(len(active), 0)

    def test_flows_exclude_needs_review(self):
        plan = build_import_plan(self.store, account_id=self.acc["id"], text=SAMPLE)
        execute_import(self.store, plan)
        s = self.store.summary("2026-11-01", "2026-11-30")
        # 1250 + 350 = 1600 rub = 160000 minor confirmed expenses
        self.assertEqual(s["flows"]["expense_minor"], 160000)
        # +150000.55 income is needs_review (Прочие) → excluded
        self.assertEqual(s["flows"]["income_minor"], 0)
        ea = s["expense_analytics"]
        self.assertEqual(ea["total_expense_minor"], 160000)
        self.assertTrue(any(seg["name"] == "Продукты" for seg in ea["segments"]))

    def test_unknown_balance_not_invented(self):
        plan = build_import_plan(self.store, account_id=self.acc["id"], text=SAMPLE)
        execute_import(self.store, plan)
        s = self.store.summary("2026-11-01", "2026-11-30")
        self.assertFalse(s["net_worth"]["liquid_complete"])
        self.assertIsNone(s["balances"][self.acc["id"]])


if __name__ == "__main__":
    unittest.main()
