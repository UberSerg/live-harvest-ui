"""Seed confirmed recurring flows into Capital ledger (idempotent by name)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.capital.money import to_minor
from tools.capital.store import CapitalStore


def find_by_name(items, name):
    for x in items:
        if x.get("name") == name and not x.get("archived"):
            return x
    return None


def main() -> None:
    s = CapitalStore()
    # categories
    cats = {c["name"]: c for c in s.list_kind("category")}
    if "Коммуналка" not in cats:
        cats["Коммуналка"] = s.upsert(
            "category",
            {"name": "Коммуналка", "category_kind": "expense", "status": "actual", "source": "user"},
        )
    if "Ипотека" not in cats:
        cats["Ипотека"] = s.upsert(
            "category",
            {"name": "Ипотека", "category_kind": "expense", "status": "actual", "source": "user"},
        )
    if "Зарплата" not in cats:
        cats["Зарплата"] = s.upsert(
            "category",
            {"name": "Зарплата", "category_kind": "income", "status": "actual", "source": "user"},
        )

    acc = find_by_name(s.list_kind("account"), "Основной (зарплатный)")
    if not acc:
        acc = s.upsert(
            "account",
            {
                "name": "Основной (зарплатный)",
                "account_kind": "checking",
                "currency": "RUB",
                "opening_balance_minor": 0,
                "opening_date": "2026-11-25",
                "status": "actual",
                "source": "user",
                "note": "Счёт для регулярных потоков; остаток не задан до подтверждения кеша",
            },
        )

    lia = find_by_name(s.list_kind("liability"), "Ипотека")
    principal = to_minor("3100000", "RUB")
    payment = to_minor("26500", "RUB")
    if not lia:
        lia = s.upsert(
            "liability",
            {
                "name": "Ипотека",
                "currency": "RUB",
                "principal_remaining_minor": principal,
                "rate_apr_percent": 6,
                "payment_minor": payment,
                "status": "estimated",
                "source": "user",
                "harvest_link": "[[Ипотека и жильё]]",
                "note": "Остаток 3.1 млн и платёж 26.5 тыс — подтверждение для Капитала 2026-11-25; актуальность ставки/срока — из среза 2026-10-21",
            },
        )
    else:
        lia["principal_remaining_minor"] = principal
        lia["payment_minor"] = payment
        lia["status"] = "estimated"
        lia["note"] = "Обновлено 2026-11-25: платёж 26.5 тыс, остаток 3.1 млн"
        s.upsert("liability", lia)

    specs = [
        {
            "name": "Зарплата",
            "type": "income",
            "amount": "380000",
            "category_id": cats["Зарплата"]["id"],
            "status": "planned",
            "comment": "Постоянный доход (ЗП). Подтверждено для Капитала 2026-11-25.",
            "harvest_link": "[[Доход — текущий]]",
        },
        {
            "name": "Ипотека (платёж)",
            "type": "expense",
            "amount": "26500",
            "category_id": cats["Ипотека"]["id"],
            "status": "planned",
            "comment": "Постоянный расход. Платёж 26.5 тыс — 2026-11-25.",
            "harvest_link": "[[Ипотека и жильё]]",
        },
        {
            "name": "Коммуналка",
            "type": "expense",
            "amount": "10000",
            "category_id": cats["Коммуналка"]["id"],
            "status": "planned",
            "comment": "Ориентир 10 тыс — задан пользователем 2026-11-25.",
            "harvest_link": "[[Доход — текущий]]",
        },
    ]

    existing = {r["name"]: r for r in s.list_kind("recurring") if not r.get("archived")}
    for spec in specs:
        payload = {
            "name": spec["name"],
            "type": spec["type"],
            "amount_minor": to_minor(spec["amount"], "RUB"),
            "currency": "RUB",
            "cadence": "monthly",
            "account_id": acc["id"],
            "category_id": spec["category_id"],
            "status": spec["status"],
            "source": "user",
            "comment": spec["comment"],
            "harvest_link": spec["harvest_link"],
            "archived": False,
        }
        if spec["name"] in existing:
            payload["id"] = existing[spec["name"]]["id"]
            payload["created_at"] = existing[spec["name"]].get("created_at")
        saved = s.upsert("recurring", payload)
        print("recurring", saved["id"], saved["name"], saved["amount_minor"])

    # current-month planned txs (one-shot sketch for calendar visibility)
    from datetime import date

    month_anchor = date.today().replace(day=1).isoformat()
    planned_specs = [
        ("planned: Зарплата", "income", "380000", cats["Зарплата"]["id"]),
        ("planned: Ипотека", "expense", "26500", cats["Ипотека"]["id"]),
        ("planned: Коммуналка", "expense", "10000", cats["Коммуналка"]["id"]),
    ]
    txs = s.list_kind("transaction")
    for comment, typ, amount, cat in planned_specs:
        exists = any(
            t.get("comment") == comment and t.get("date", "").startswith(month_anchor[:7]) and t.get("status") == "planned"
            for t in txs
        )
        if exists:
            print("skip planned tx", comment)
            continue
        t = s.upsert(
            "transaction",
            {
                "type": typ,
                "date": month_anchor,
                "amount_minor": to_minor(amount, "RUB"),
                "currency": "RUB",
                "account_id": acc["id"],
                "category_id": cat,
                "comment": comment,
                "status": "planned",
                "source": "user",
            },
        )
        print("planned tx", t["id"], comment)

    print("account", acc["id"])
    print("liability", lia["id"])
    print("OK")


if __name__ == "__main__":
    main()
