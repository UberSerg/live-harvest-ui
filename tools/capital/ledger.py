from __future__ import annotations

from collections import defaultdict
from typing import Any


ACTUAL_FLOW = {"actual"}
TX_IN = {"income"}
TX_OUT = {"expense", "debt_interest"}
TX_TRANSFER = {"transfer"}
TX_PRINCIPAL = {"debt_principal"}


def _ok(tx: dict) -> bool:
    return tx.get("status") in ACTUAL_FLOW and tx.get("status") != "void"


def account_balances(accounts: list[dict], transactions: list[dict]) -> dict[str, int]:
    """Book balances in account currency minor units (actual only)."""
    bal = {a["id"]: int(a.get("opening_balance_minor") or 0) for a in accounts if not a.get("archived")}
    for tx in transactions:
        if not _ok(tx):
            continue
        t = tx.get("type")
        amt = int(tx["amount_minor"])
        acc = tx.get("account_id")
        if acc not in bal:
            continue
        if t in TX_IN:
            bal[acc] += amt
        elif t in TX_OUT or t in TX_PRINCIPAL:
            bal[acc] -= amt
        elif t in TX_TRANSFER:
            bal[acc] -= amt
            dest = tx.get("counterparty_account_id")
            if dest in bal:
                bal[dest] += amt
        elif t == "adjustment":
            # signed amount_minor: positive credits account
            bal[acc] += amt
    return bal


def period_flows(transactions: list[dict], date_from: str, date_to: str) -> dict[str, int]:
    """Sum income/expense (not transfers) in [from, to], actual only. Single-currency aggregate caller-side."""
    income = 0
    expense = 0
    for tx in transactions:
        if not _ok(tx):
            continue
        d = tx.get("date") or ""
        if d < date_from or d > date_to:
            continue
        t = tx.get("type")
        amt = int(tx["amount_minor"])
        if t in TX_IN:
            income += amt
        elif t in TX_OUT:
            expense += amt
        # transfer / principal tracked elsewhere
    return {
        "income_minor": income,
        "expense_minor": expense,
        "net_cashflow_minor": income - expense,
    }


def expense_by_category(transactions: list[dict], date_from: str, date_to: str) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for tx in transactions:
        if not _ok(tx) or tx.get("type") not in TX_OUT:
            continue
        d = tx.get("date") or ""
        if d < date_from or d > date_to:
            continue
        cat = tx.get("category_id") or "uncategorized"
        out[cat] += int(tx["amount_minor"])
    return dict(out)


def monthly_series(transactions: list[dict], months: list[str]) -> list[dict[str, Any]]:
    """months like ['2026-09','2026-10']. Transfers excluded from income/expense."""
    rows = []
    for m in months:
        start, end = f"{m}-01", f"{m}-31"
        f = period_flows(transactions, start, end)
        rows.append({"month": m, **f})
    return rows


def net_worth(
    account_balances_map: dict[str, int],
    assets: list[dict],
    liabilities: list[dict],
    valuations: list[dict],
) -> dict[str, Any]:
    """
    Liquid = sum account balances (actual books).
    Assets estimated = latest valuation per asset (estimated/actual marked).
    Liabilities = principal_remaining.
    """
    liquid = sum(account_balances_map.values())
    latest: dict[str, dict] = {}
    for v in sorted(valuations, key=lambda x: x.get("date") or ""):
        if v.get("status") == "void":
            continue
        aid = v.get("asset_id")
        if aid:
            latest[aid] = v
    asset_total = 0
    asset_flags = []
    for a in assets:
        if a.get("archived"):
            continue
        if a["id"] in latest:
            vv = latest[a["id"]]
            asset_total += int(vv["value_minor"])
            asset_flags.append(vv.get("status", "estimated"))
        elif a.get("value_minor") is not None:
            asset_total += int(a["value_minor"])
            asset_flags.append(a.get("status", "estimated"))
    debt = sum(int(l.get("principal_remaining_minor") or 0) for l in liabilities if not l.get("archived"))
    # Net worth = liquid accounts + non-cash assets - debt
    # Avoid double-count: broker account balance vs broker asset valuation — caller should not both.
    estimated = any(s == "estimated" for s in asset_flags) or not asset_flags and asset_total == 0
    return {
        "liquid_minor": liquid,
        "assets_minor": asset_total,
        "liabilities_minor": debt,
        "net_worth_minor": liquid + asset_total - debt,
        "has_estimates": estimated or asset_total > 0,
    }
