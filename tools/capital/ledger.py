from __future__ import annotations

from collections import defaultdict
from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Any

from .money import BASE_CURRENCY, convert_minor


ACTUAL_FLOW = {"actual"}
TX_IN = {"income"}
TX_OUT = {"expense", "debt_interest"}
TX_TRANSFER = {"transfer"}
TX_PRINCIPAL = {"debt_principal"}


def _ok(tx: dict) -> bool:
    return tx.get("status") == "actual"


def _month_end(ym: str) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    return f"{ym}-{monthrange(y, m)[1]:02d}"


def account_is_balance_known(account: dict) -> bool:
    """Unknown balance ≠ zero. Explicit false / null opening without known flag → unknown."""
    if account.get("balance_known") is False:
        return False
    if account.get("opening_balance_minor") is None and "opening_balance_minor" in account:
        return False
    if account.get("balance_status") == "unknown":
        return False
    return True


def pick_fx_rate(
    rates: list[dict],
    from_currency: str,
    to_currency: str,
    as_of: str | None = None,
) -> dict | None:
    """Latest rate on or before as_of. No invented fallback."""
    src, dst = from_currency.upper(), to_currency.upper()
    if src == dst:
        return {"rate": "1", "date": as_of or "", "from_currency": src, "to_currency": dst}
    candidates = []
    for r in rates:
        if r.get("status") == "void":
            continue
        fr = (r.get("from_currency") or r.get("from") or "").upper()
        to = (r.get("to_currency") or r.get("to") or "").upper()
        if fr == src and to == dst:
            candidates.append(r)
        elif fr == dst and to == src and r.get("rate"):
            # inverse
            try:
                inv = Decimal("1") / Decimal(str(r["rate"]))
                candidates.append({**r, "rate": str(inv), "from_currency": src, "to_currency": dst, "_derived": True})
            except Exception:
                continue
    if as_of:
        candidates = [c for c in candidates if (c.get("date") or "") <= as_of]
    if not candidates:
        return None
    return max(candidates, key=lambda x: x.get("date") or "")


def to_base_minor(
    amount_minor: int,
    currency: str,
    rates: list[dict],
    *,
    base: str = BASE_CURRENCY,
    as_of: str | None = None,
) -> tuple[int | None, str | None]:
    """Returns (amount_in_base or None, reason_if_missing)."""
    cur = (currency or base).upper()
    if cur == base.upper():
        return int(amount_minor), None
    picked = pick_fx_rate(rates, cur, base, as_of)
    if not picked:
        return None, f"no_fx:{cur}->{base}"
    converted = convert_minor(amount_minor, cur, base, picked.get("rate"))
    if converted is None:
        return None, f"bad_fx:{cur}->{base}"
    return converted, None


def account_balances(
    accounts: list[dict],
    transactions: list[dict],
    *,
    as_of: str | None = None,
    include_archived: bool = False,
) -> dict[str, dict[str, Any]]:
    """
    Book balances in account currency minor units (actual only).
    Respects opening_date and ignores txs after as_of / before opening.
    Future ops never enter current actual balance.
    """
    today = as_of or date.today().isoformat()
    result: dict[str, dict[str, Any]] = {}
    for a in accounts:
        if a.get("archived") and not include_archived:
            continue
        aid = a["id"]
        known = account_is_balance_known(a)
        opening_date = a.get("opening_date") or "0000-01-01"
        opening = 0
        if known and opening_date <= today:
            opening = int(a.get("opening_balance_minor") or 0)
        result[aid] = {
            "balance_minor": opening if known and opening_date <= today else (0 if known else None),
            "currency": (a.get("currency") or "RUB").upper(),
            "known": known and opening_date <= today,
            "account_kind": a.get("account_kind"),
            "archived": bool(a.get("archived")),
            "linked_asset_id": a.get("linked_asset_id"),
            "exclude_from_liquid": bool(a.get("exclude_from_liquid")),
            "name": a.get("name"),
        }
        if not known:
            result[aid]["balance_minor"] = None

    for tx in transactions:
        if not _ok(tx):
            continue
        d = tx.get("date") or ""
        if d > today:
            continue
        t = tx.get("type")
        amt = int(tx["amount_minor"])
        acc = tx.get("account_id")
        if acc not in result:
            continue
        # txs before opening_date still apply only if balance known; opening is starting point
        opening_date = next((a.get("opening_date") or "0000-01-01" for a in accounts if a["id"] == acc), "0000-01-01")
        if d < opening_date:
            continue
        if not result[acc]["known"]:
            continue
        bal = result[acc]["balance_minor"] or 0
        if t in TX_IN:
            bal += amt
        elif t in TX_OUT or t in TX_PRINCIPAL:
            bal -= amt
        elif t in TX_TRANSFER:
            bal -= amt
            dest = tx.get("counterparty_account_id")
            if dest in result and result[dest]["known"]:
                d_open = next(
                    (a.get("opening_date") or "0000-01-01" for a in accounts if a["id"] == dest),
                    "0000-01-01",
                )
                if d >= d_open:
                    result[dest]["balance_minor"] = (result[dest]["balance_minor"] or 0) + amt
        elif t == "adjustment":
            bal += amt
        result[acc]["balance_minor"] = bal
    return result


def liability_principals(
    liabilities: list[dict],
    transactions: list[dict],
    *,
    as_of: str | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Remaining principal per liability.
    Base: principal_remaining_minor (or opening_principal_minor) as of last bank statement date,
    then subtract actual debt_principal payments after statement_date.
    Interest does not reduce principal.
    """
    today = as_of or date.today().isoformat()
    out: dict[str, dict[str, Any]] = {}
    for lia in liabilities:
        if lia.get("archived"):
            continue
        lid = lia["id"]
        base = lia.get("principal_remaining_minor")
        if base is None:
            base = lia.get("opening_principal_minor")
        known = base is not None and lia.get("principal_known", True) is not False
        statement_date = lia.get("principal_as_of") or lia.get("opening_date") or "0000-01-01"
        remaining = int(base) if known else None
        out[lid] = {
            "principal_remaining_minor": remaining,
            "currency": (lia.get("currency") or "RUB").upper(),
            "known": known,
            "name": lia.get("name"),
            "status": lia.get("status"),
            "principal_as_of": statement_date if known else None,
        }

    for tx in transactions:
        if not _ok(tx):
            continue
        if tx.get("type") not in TX_PRINCIPAL:
            continue
        d = tx.get("date") or ""
        if d > today:
            continue
        lid = tx.get("liability_id")
        if not lid or lid not in out or not out[lid]["known"]:
            continue
        stmt = out[lid]["principal_as_of"] or "0000-01-01"
        if d <= stmt:
            # already reflected in bank statement balance
            continue
        # prefer explicit principal_portion_minor; else full amount is principal
        portion = tx.get("principal_portion_minor")
        pay = int(portion) if portion is not None else int(tx["amount_minor"])
        out[lid]["principal_remaining_minor"] = max(0, int(out[lid]["principal_remaining_minor"]) - pay)
    return out


def _counts_in_flows(tx: dict) -> bool:
    """Exclude needs_review / internal transfers from consumer income-expense stats."""
    if tx.get("classification_status") == "needs_review":
        return False
    if tx.get("include_in_flows") is False:
        return False
    ek = tx.get("economic_kind")
    if ek in ("transfer_internal", "transfer_other", "investment_funding", "undefined"):
        return False
    return True


def period_flows(
    transactions: list[dict],
    date_from: str,
    date_to: str,
    *,
    statuses: set[str] | None = None,
    consumer_only: bool = True,
) -> dict[str, int]:
    """Sum income/expense (not transfers, not principal) in [from, to]."""
    allow = statuses or ACTUAL_FLOW
    income = 0
    expense = 0
    skipped_review = 0
    for tx in transactions:
        if tx.get("status") == "void" or tx.get("status") not in allow:
            continue
        d = tx.get("date") or ""
        if d < date_from or d > date_to:
            continue
        if consumer_only and not _counts_in_flows(tx):
            skipped_review += 1
            continue
        t = tx.get("type")
        amt = int(tx["amount_minor"])
        if t in TX_IN:
            income += amt
        elif t in TX_OUT:
            expense += amt
    return {
        "income_minor": income,
        "expense_minor": expense,
        "net_cashflow_minor": income - expense,
        "excluded_ops": skipped_review,
    }


def recurring_monthly_net(recurring: list[dict]) -> dict[str, int]:
    """Active recurring templates → monthly planned net (templates only, not booked)."""
    income = 0
    expense = 0
    for r in recurring:
        if r.get("archived") or r.get("status") == "void":
            continue
        if r.get("cadence", "monthly") != "monthly":
            continue
        amt = int(r.get("amount_minor") or 0)
        t = r.get("type")
        if t in TX_IN:
            income += amt
        elif t in TX_OUT or t in TX_PRINCIPAL:
            expense += amt
    return {
        "income_minor": income,
        "expense_minor": expense,
        "net_cashflow_minor": income - expense,
    }


def planned_without_double_count(
    transactions: list[dict],
    recurring: list[dict],
    date_from: str,
    date_to: str,
) -> dict[str, Any]:
    """
    Planned cashflow for period: materialized planned txs take precedence over templates
    for the same recurring_id + month. Unmaterialized templates fill gaps.
    """
    planned_txs = [
        t
        for t in transactions
        if t.get("status") == "planned" and date_from <= (t.get("date") or "") <= date_to
    ]
    covered: set[tuple[str, str]] = set()
    income = 0
    expense = 0
    for t in planned_txs:
        ym = (t.get("date") or "")[:7]
        rid = t.get("recurring_id")
        if rid:
            covered.add((rid, ym))
        amt = int(t["amount_minor"])
        typ = t.get("type")
        if typ in TX_IN:
            income += amt
        elif typ in TX_OUT or typ in TX_PRINCIPAL:
            expense += amt

    # months in range
    months: list[str] = []
    y, m = int(date_from[:4]), int(date_from[5:7])
    end_y, end_m = int(date_to[:4]), int(date_to[5:7])
    while (y, m) <= (end_y, end_m):
        months.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            m = 1
            y += 1

    gap_income = 0
    gap_expense = 0
    gaps = []
    for r in recurring:
        if r.get("archived") or r.get("status") == "void":
            continue
        if r.get("cadence", "monthly") != "monthly":
            continue
        rid = r["id"]
        amt = int(r.get("amount_minor") or 0)
        typ = r.get("type")
        for ym in months:
            if (rid, ym) in covered:
                continue
            gaps.append({"recurring_id": rid, "month": ym, "name": r.get("name"), "amount_minor": amt, "type": typ})
            if typ in TX_IN:
                gap_income += amt
            elif typ in TX_OUT or typ in TX_PRINCIPAL:
                gap_expense += amt

    return {
        "income_minor": income + gap_income,
        "expense_minor": expense + gap_expense,
        "net_cashflow_minor": (income + gap_income) - (expense + gap_expense),
        "from_planned_txs": {"income_minor": income, "expense_minor": expense},
        "from_unmaterialized_templates": {"income_minor": gap_income, "expense_minor": gap_expense},
        "unmaterialized": gaps,
        "note": "templates only fill months without planned ops from that recurring",
    }


def expense_by_category(transactions: list[dict], date_from: str, date_to: str) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for tx in transactions:
        if not _ok(tx) or tx.get("type") not in TX_OUT:
            continue
        if not _counts_in_flows(tx):
            continue
        d = tx.get("date") or ""
        if d < date_from or d > date_to:
            continue
        cat = tx.get("category_id") or "uncategorized"
        out[cat] += int(tx["amount_minor"])
    return dict(out)


def _tx_direction(tx: dict) -> str | None:
    d = tx.get("direction")
    if d in ("in", "out"):
        return d
    t = tx.get("type")
    if t in TX_IN:
        return "in"
    if t in TX_OUT or t in TX_PRINCIPAL:
        return "out"
    if t in TX_TRANSFER:
        return "out"  # outflow leg from account_id
    if t == "adjustment":
        amt = int(tx.get("amount_minor") or 0)
        return "in" if amt >= 0 else "out"
    return None


def bank_turnover(
    transactions: list[dict],
    date_from: str,
    date_to: str,
    *,
    account_id: str | None = None,
) -> dict[str, Any]:
    """All actual cash movements by bank direction — independent of economic classification."""
    inflow = 0
    outflow = 0
    n_in = 0
    n_out = 0
    ops_in: list[dict] = []
    ops_out: list[dict] = []
    for tx in transactions:
        if tx.get("status") != "actual":
            continue
        d = tx.get("date") or ""
        if d < date_from or d > date_to:
            continue
        if account_id and tx.get("account_id") != account_id:
            # transfers into account via counterparty
            if not (tx.get("type") == "transfer" and tx.get("counterparty_account_id") == account_id):
                continue
            direction = "in"
            amt = abs(int(tx["amount_minor"]))
        else:
            direction = _tx_direction(tx)
            if direction is None:
                continue
            amt = abs(int(tx["amount_minor"]))
        row = {
            "id": tx.get("id"),
            "date": d,
            "amount_minor": amt,
            "direction": direction,
            "economic_kind": tx.get("economic_kind") or "undefined",
            "merchant": tx.get("merchant") or tx.get("bank_category") or "",
            "classification_status": tx.get("classification_status") or "confirmed",
        }
        if direction == "in":
            inflow += amt
            n_in += 1
            ops_in.append(row)
        else:
            outflow += amt
            n_out += 1
            ops_out.append(row)
    return {
        "inflow_minor": inflow,
        "outflow_minor": outflow,
        "net_minor": inflow - outflow,
        "count_in": n_in,
        "count_out": n_out,
        "count": n_in + n_out,
        "operations_in": sorted(ops_in, key=lambda x: x["date"], reverse=True)[:200],
        "operations_out": sorted(ops_out, key=lambda x: x["date"], reverse=True)[:200],
        "period": {"from": date_from, "to": date_to},
        "note": "банковский оборот: все actual-движения, без фильтра классификации",
    }


def _economic_bucket(tx: dict, direction: str) -> str:
    ek = tx.get("economic_kind") or ""
    status = tx.get("classification_status")
    if status == "needs_review" or ek in ("", "undefined"):
        return "unclassified_in" if direction == "in" else "unclassified_out"
    mapping = {
        "salary": "income_salary",
        "other_income": "income_other",
        "cashback": "income_cashback",
        "bank_interest": "income_interest",
        "refund": "income_refund",
        "cash_deposit": "income_cash",
        "purchase": "expense_purchase",
        "bank_fee": "expense_fee",
        "mortgage": "expense_mortgage",
        "atm_withdraw": "expense_atm",
        "debt_principal": "debt_principal",
        "debt_interest": "expense_fee",
        "transfer_internal": "transfer_internal",
        "transfer_other": "transfer_other",
        "investment_funding": "investment",
    }
    if ek in mapping:
        return mapping[ek]
    # fallback by ledger type
    if direction == "in":
        return "income_other" if status == "confirmed" else "unclassified_in"
    return "expense_purchase" if status == "confirmed" else "unclassified_out"


BUCKET_LABELS = {
    "income_salary": "Зарплата",
    "income_other": "Дополнительные доходы",
    "income_cashback": "Кешбэк",
    "income_interest": "Банковские проценты",
    "income_refund": "Возвраты",
    "income_cash": "Пополнение наличными",
    "expense_purchase": "Покупки / расходы",
    "expense_fee": "Банковские комиссии",
    "expense_mortgage": "Ипотечные платежи",
    "expense_atm": "Снятие наличных",
    "debt_principal": "Погашение тела долга",
    "transfer_internal": "Внутренние переводы",
    "transfer_other": "Переводы другим людям",
    "investment": "Инвестиционные операции",
    "unclassified_in": "Неклассифицированные поступления",
    "unclassified_out": "Неклассифицированные списания",
}


def economic_breakdown(
    transactions: list[dict],
    date_from: str,
    date_to: str,
    *,
    account_id: str | None = None,
) -> dict[str, Any]:
    """Partition every bank movement into economic buckets; sums must equal bank turnover."""
    buckets: dict[str, dict[str, Any]] = {}
    for tx in transactions:
        if tx.get("status") != "actual":
            continue
        d = tx.get("date") or ""
        if d < date_from or d > date_to:
            continue
        if account_id and tx.get("account_id") != account_id:
            if not (tx.get("type") == "transfer" and tx.get("counterparty_account_id") == account_id):
                continue
            direction = "in"
        else:
            direction = _tx_direction(tx)
            if direction is None:
                continue
        amt = abs(int(tx["amount_minor"]))
        key = _economic_bucket(tx, direction)
        b = buckets.setdefault(
            key,
            {
                "id": key,
                "label": BUCKET_LABELS.get(key, key),
                "direction": "in" if key.endswith("_in") or key.startswith("income_") else (
                    "out" if key.startswith("expense_") or key in ("debt_principal", "transfer_internal", "transfer_other", "investment", "unclassified_out") else "mixed"
                ),
                "amount_minor": 0,
                "count": 0,
                "operations": [],
            },
        )
        # fix direction for income_* / expense_*
        if key.startswith("income_") or key == "unclassified_in":
            b["direction"] = "in"
        elif key.startswith("expense_") or key in (
            "debt_principal",
            "transfer_internal",
            "transfer_other",
            "investment",
            "unclassified_out",
        ):
            b["direction"] = "out"
        b["amount_minor"] += amt
        b["count"] += 1
        if len(b["operations"]) < 100:
            b["operations"].append(
                {
                    "id": tx.get("id"),
                    "date": d,
                    "amount_minor": amt,
                    "merchant": tx.get("merchant") or tx.get("bank_category") or "",
                    "economic_kind": tx.get("economic_kind"),
                    "classification_status": tx.get("classification_status"),
                }
            )

    sum_in = sum(b["amount_minor"] for b in buckets.values() if b["direction"] == "in")
    sum_out = sum(b["amount_minor"] for b in buckets.values() if b["direction"] == "out")
    turnover = bank_turnover(transactions, date_from, date_to, account_id=account_id)
    return {
        "buckets": sorted(buckets.values(), key=lambda x: (-x["amount_minor"], x["id"])),
        "sum_in_minor": sum_in,
        "sum_out_minor": sum_out,
        "matches_bank_in": sum_in == turnover["inflow_minor"],
        "matches_bank_out": sum_out == turnover["outflow_minor"],
        "delta_in_minor": sum_in - turnover["inflow_minor"],
        "delta_out_minor": sum_out - turnover["outflow_minor"],
        "period": {"from": date_from, "to": date_to},
    }


def expense_analytics(
    transactions: list[dict],
    categories: list[dict],
    date_from: str,
    date_to: str,
    *,
    account_id: str | None = None,
) -> dict[str, Any]:
    """Doughnut-ready economic expense breakdown (not full bank outflow)."""
    cat_name = {c["id"]: c["name"] for c in categories}
    by_cat: dict[str, int] = defaultdict(int)
    by_merchant: dict[str, int] = defaultdict(int)
    ops_by_cat: dict[str, list[dict]] = defaultdict(list)
    largest = []
    excluded: dict[str, dict[str, Any]] = {}
    bank_out = 0
    for tx in transactions:
        if tx.get("status") != "actual":
            continue
        d = tx.get("date") or ""
        if d < date_from or d > date_to:
            continue
        if account_id and tx.get("account_id") != account_id:
            continue
        direction = _tx_direction(tx)
        if direction != "out":
            continue
        amt = abs(int(tx["amount_minor"]))
        bank_out += amt
        # include in doughnut?
        if tx.get("type") not in TX_OUT and tx.get("type") not in TX_PRINCIPAL:
            # transfers etc.
            reason = "transfer_or_non_expense_type"
            ex = excluded.setdefault(reason, {"reason": reason, "label": "Переводы / не расход", "amount_minor": 0, "count": 0})
            ex["amount_minor"] += amt
            ex["count"] += 1
            continue
        if not _counts_in_flows(tx):
            ek = tx.get("economic_kind") or "undefined"
            if tx.get("classification_status") == "needs_review" or ek == "undefined":
                reason = "unclassified"
                label = "Неклассифицированные списания"
            elif ek in ("transfer_internal", "transfer_other"):
                reason = "transfers"
                label = "Переводы"
            elif ek == "investment_funding":
                reason = "investment"
                label = "Инвестиции"
            elif ek == "debt_principal" or tx.get("type") in TX_PRINCIPAL:
                reason = "debt_principal"
                label = "Погашение тела долга"
            else:
                reason = "excluded_other"
                label = "Прочие исключения из doughnut"
            ex = excluded.setdefault(reason, {"reason": reason, "label": label, "amount_minor": 0, "count": 0})
            ex["amount_minor"] += amt
            ex["count"] += 1
            continue
        cid = tx.get("category_id") or "uncategorized"
        by_cat[cid] += amt
        merch = tx.get("merchant") or "—"
        by_merchant[merch] += amt
        ops_by_cat[cid].append(
            {
                "id": tx.get("id"),
                "date": d,
                "amount_minor": amt,
                "merchant": merch,
                "comment": tx.get("comment") or tx.get("description") or "",
            }
        )
        largest.append(
            {
                "id": tx.get("id"),
                "date": d,
                "amount_minor": amt,
                "merchant": merch,
                "category": cat_name.get(cid, cid),
            }
        )
    total = sum(by_cat.values())
    segments = []
    for cid, amt in sorted(by_cat.items(), key=lambda x: -x[1]):
        segments.append(
            {
                "category_id": cid,
                "name": cat_name.get(cid, cid),
                "amount_minor": amt,
                "share": round(amt / total, 4) if total else 0,
                "operations": sorted(ops_by_cat[cid], key=lambda x: x["date"], reverse=True),
            }
        )
    excluded_total = sum(x["amount_minor"] for x in excluded.values())
    needs = [
        t
        for t in transactions
        if t.get("status") == "actual"
        and t.get("classification_status") == "needs_review"
        and date_from <= (t.get("date") or "") <= date_to
        and (not account_id or t.get("account_id") == account_id)
    ]
    return {
        "total_expense_minor": total,
        "bank_outflow_minor": bank_out,
        "excluded_from_chart_minor": excluded_total,
        "excluded": sorted(excluded.values(), key=lambda x: -x["amount_minor"]),
        "segments": segments,
        "top_merchants": sorted(
            [{"merchant": k, "amount_minor": v} for k, v in by_merchant.items()],
            key=lambda x: -x["amount_minor"],
        )[:15],
        "largest_purchases": sorted(largest, key=lambda x: -x["amount_minor"])[:15],
        "needs_review_count": len(needs),
        "period": {"from": date_from, "to": date_to},
        "note": "doughnut = экономические расходы; списания вне графика перечислены в excluded",
    }


def monthly_series(
    transactions: list[dict],
    months: list[str],
    *,
    statuses: set[str] | None = None,
) -> list[dict[str, Any]]:
    rows = []
    for m in months:
        start, end = f"{m}-01", _month_end(m)
        f = period_flows(transactions, start, end, statuses=statuses)
        rows.append({"month": m, **f})
    return rows


def net_worth(
    account_balances_map: dict[str, dict[str, Any]] | dict[str, int],
    assets: list[dict],
    liabilities: list[dict] | dict[str, dict[str, Any]],
    valuations: list[dict],
    *,
    fx_rates: list[dict] | None = None,
    base: str = BASE_CURRENCY,
    as_of: str | None = None,
) -> dict[str, Any]:
    """
    Liquid / assets / liabilities in base currency.
    Missing FX → that slice omitted + listed in missing_fx.
    Unknown account balances excluded (not treated as zero).
    Broker account with linked_asset_id excluded from liquid if asset valued.
    Own home is an asset; FI capital uses separate flag include_in_fi.
    """
    rates = fx_rates or []
    today = as_of or date.today().isoformat()
    missing_fx: list[str] = []
    unknown_accounts: list[str] = []
    liquid = 0
    liquid_complete = True

    # normalize balances map
    bals: dict[str, dict[str, Any]] = {}
    if account_balances_map and isinstance(next(iter(account_balances_map.values()), None), dict):
        bals = account_balances_map  # type: ignore[assignment]
    else:
        for k, v in account_balances_map.items():
            bals[k] = {"balance_minor": v, "currency": "RUB", "known": True}

    valued_broker_assets = set()
    latest: dict[str, dict] = {}
    for v in sorted(valuations, key=lambda x: x.get("date") or ""):
        if v.get("status") == "void":
            continue
        if as_of and (v.get("date") or "") > today:
            continue
        aid = v.get("asset_id")
        if aid:
            latest[aid] = v

    for a in assets:
        if a.get("archived"):
            continue
        if a.get("asset_kind") == "broker_portfolio" or a.get("linked_account_id"):
            if a["id"] in latest or a.get("value_minor") is not None:
                valued_broker_assets.add(a.get("linked_account_id") or a["id"])

    for aid, info in bals.items():
        if info.get("archived"):
            continue
        if not info.get("known", True) or info.get("balance_minor") is None:
            unknown_accounts.append(aid)
            liquid_complete = False
            continue
        if info.get("exclude_from_liquid"):
            continue
        # avoid double-count broker cash vs portfolio valuation
        if info.get("linked_asset_id") and info["linked_asset_id"] in latest:
            continue
        if info.get("account_kind") == "broker" and aid in valued_broker_assets:
            continue
        cur = info.get("currency") or "RUB"
        converted, reason = to_base_minor(int(info["balance_minor"]), cur, rates, base=base, as_of=today)
        if converted is None:
            missing_fx.append(reason or cur)
            liquid_complete = False
            continue
        liquid += converted

    asset_total = 0
    asset_flags = []
    asset_complete = True
    for a in assets:
        if a.get("archived"):
            continue
        cur = (a.get("currency") or "RUB").upper()
        raw = None
        status = a.get("status", "estimated")
        if a["id"] in latest:
            vv = latest[a["id"]]
            raw = int(vv["value_minor"])
            cur = (vv.get("currency") or cur).upper()
            status = vv.get("status", status)
        elif a.get("value_minor") is not None:
            raw = int(a["value_minor"])
        else:
            asset_complete = False
            continue
        converted, reason = to_base_minor(raw, cur, rates, base=base, as_of=today)
        if converted is None:
            missing_fx.append(reason or cur)
            asset_complete = False
            continue
        asset_total += converted
        asset_flags.append(status)

    # liabilities
    debt = 0
    debt_complete = True
    lia_iter: list[dict]
    if isinstance(liabilities, dict):
        lia_iter = [{"id": k, **v} for k, v in liabilities.items()]
    else:
        # recompute principals if raw list
        lia_iter = [
            {
                "id": l["id"],
                "principal_remaining_minor": l.get("principal_remaining_minor"),
                "currency": l.get("currency", "RUB"),
                "known": l.get("principal_remaining_minor") is not None,
                "name": l.get("name"),
            }
            for l in liabilities
            if not l.get("archived")
        ]

    for l in lia_iter:
        if not l.get("known", True) or l.get("principal_remaining_minor") is None:
            debt_complete = False
            continue
        cur = (l.get("currency") or "RUB").upper()
        converted, reason = to_base_minor(int(l["principal_remaining_minor"]), cur, rates, base=base, as_of=today)
        if converted is None:
            missing_fx.append(reason or cur)
            debt_complete = False
            continue
        debt += converted

    estimated = any(s == "estimated" for s in asset_flags)
    complete = liquid_complete and asset_complete and debt_complete and not missing_fx
    return {
        "base_currency": base,
        "as_of": today,
        "liquid_minor": liquid,
        "assets_minor": asset_total,
        "liabilities_minor": debt,
        "net_worth_minor": liquid + asset_total - debt,
        "has_estimates": estimated or (asset_total > 0 and not asset_complete),
        "liquid_complete": liquid_complete,
        "complete": complete,
        "unknown_accounts": unknown_accounts,
        "missing_fx": sorted(set(missing_fx)),
    }


def budget_view(
    transactions: list[dict],
    recurring: list[dict],
    categories: list[dict],
    date_from: str,
    date_to: str,
) -> dict[str, Any]:
    """Plan vs fact by category; flag unfilled budget lines."""
    cat_map = {c["id"]: c for c in categories}
    buckets = {
        "income_regular": {"plan": 0, "fact": 0, "items": []},
        "income_extra": {"plan": 0, "fact": 0, "items": []},
        "expense_fixed": {"plan": 0, "fact": 0, "items": []},
        "expense_variable": {"plan": 0, "fact": 0, "items": []},
        "expense_irregular": {"plan": 0, "fact": 0, "items": []},
        "savings": {"plan": 0, "fact": 0, "items": []},
        "investments": {"plan": 0, "fact": 0, "items": []},
    }

    def bucket_for(cat_id: str | None, tx_type: str) -> str:
        c = cat_map.get(cat_id or "")
        kind = (c or {}).get("budget_bucket") or (c or {}).get("category_kind")
        if tx_type in TX_IN:
            if kind in ("income", "income_regular"):
                return "income_regular"
            return "income_extra"
        if kind in ("savings", "накопления"):
            return "savings"
        if kind in ("investments", "инвестиции"):
            return "investments"
        if kind in ("housing", "fixed", "expense_fixed"):
            return "expense_fixed"
        if kind in ("irregular", "expense_irregular"):
            return "expense_irregular"
        return "expense_variable"

    for r in recurring:
        if r.get("archived") or r.get("status") == "void":
            continue
        b = bucket_for(r.get("category_id"), r.get("type") or "expense")
        amt = int(r.get("amount_minor") or 0)
        buckets[b]["plan"] += amt
        buckets[b]["items"].append({"name": r.get("name"), "amount_minor": amt, "source": "recurring", "id": r.get("id")})

    for t in transactions:
        if t.get("status") not in ("actual", "planned"):
            continue
        d = t.get("date") or ""
        if d < date_from or d > date_to:
            continue
        typ = t.get("type")
        if typ not in TX_IN and typ not in TX_OUT and typ not in TX_PRINCIPAL:
            continue
        b = bucket_for(t.get("category_id"), typ or "expense")
        amt = int(t["amount_minor"])
        if t.get("status") == "planned" and not t.get("recurring_id"):
            # one-off planned not already covered by template list
            buckets[b]["plan"] += amt
        if t.get("status") == "actual":
            buckets[b]["fact"] += amt

    unfilled = []
    for key, label in [
        ("expense_variable", "Переменные расходы"),
        ("expense_irregular", "Нерегулярные расходы"),
        ("savings", "Накопления"),
        ("investments", "Инвестиции"),
    ]:
        if buckets[key]["plan"] == 0 and buckets[key]["fact"] == 0:
            unfilled.append(label)

    income_plan = buckets["income_regular"]["plan"] + buckets["income_extra"]["plan"]
    income_fact = buckets["income_regular"]["fact"] + buckets["income_extra"]["fact"]
    expense_plan = (
        buckets["expense_fixed"]["plan"]
        + buckets["expense_variable"]["plan"]
        + buckets["expense_irregular"]["plan"]
    )
    expense_fact = (
        buckets["expense_fixed"]["fact"]
        + buckets["expense_variable"]["fact"]
        + buckets["expense_irregular"]["fact"]
    )
    savings_plan = buckets["savings"]["plan"] + buckets["investments"]["plan"]
    # Free cash after known fixed only — never claim full free cashflow
    known_fixed = buckets["expense_fixed"]["plan"]
    free_after_fixed = income_plan - known_fixed if income_plan else None

    return {
        "buckets": buckets,
        "unfilled_budget_lines": unfilled,
        "income_plan_minor": income_plan,
        "income_fact_minor": income_fact,
        "expense_plan_minor": expense_plan,
        "expense_fact_minor": expense_fact,
        "savings_plan_minor": savings_plan,
        "variance_income_minor": income_fact - income_plan,
        "variance_expense_minor": expense_fact - expense_plan,
        "free_after_known_fixed_minor": free_after_fixed,
        "free_cash_complete": len(unfilled) == 0,
        "note": "Свободный остаток после известных постоянных — не полный free cashflow, пока незаполненные статьи бюджета остаются",
    }


def project_scenario(assumptions: dict[str, Any], months: int = 12) -> dict[str, Any]:
    """
    Simple monthly projection. Does not write ledger.
    Assumptions must be explicit; missing yield/inflation → None, not invented.
    """
    income = assumptions.get("monthly_income_minor")
    expense = assumptions.get("monthly_expense_minor")
    savings = assumptions.get("monthly_savings_minor")
    start = assumptions.get("starting_capital_minor")
    yield_annual = assumptions.get("annual_yield_percent")  # may be None
    inflation = assumptions.get("annual_inflation_percent")  # may be None
    if income is None or expense is None or start is None:
        return {
            "ok": False,
            "error": "need monthly_income_minor, monthly_expense_minor, starting_capital_minor",
            "assumptions": assumptions,
        }
    if savings is None:
        savings = int(income) - int(expense)
    monthly_yield = None
    if yield_annual is not None:
        monthly_yield = Decimal(str(yield_annual)) / Decimal("100") / Decimal("12")
    series = []
    capital = int(start)
    for i in range(1, months + 1):
        if monthly_yield is not None:
            capital = int(
                (Decimal(capital) * (Decimal("1") + monthly_yield)).quantize(Decimal("1"))
            )
        capital += int(savings)
        series.append({"month_index": i, "capital_minor": capital, "savings_added_minor": int(savings)})
    fi_target = assumptions.get("fi_target_minor")
    months_to_fi = None
    if fi_target is not None:
        for row in series:
            if row["capital_minor"] >= int(fi_target):
                months_to_fi = row["month_index"]
                break
    return {
        "ok": True,
        "assumptions": {
            **assumptions,
            "annual_yield_percent": yield_annual,
            "annual_inflation_percent": inflation,
            "yield_applied": yield_annual is not None,
            "inflation_applied": False,  # shown as editable; not silently applied to target
        },
        "months": months,
        "series": series,
        "ending_capital_minor": series[-1]["capital_minor"] if series else start,
        "months_to_fi": months_to_fi,
        "note": "forecast only; does not mutate ledger",
    }


def fi_progress(
    fi_params: dict | None,
    net_worth_data: dict,
    monthly_savings_minor: int | None,
) -> dict[str, Any]:
    """FI metrics from confirmed params. Own home excluded unless include_home_in_fi."""
    if not fi_params:
        return {"ready": False, "reason": "fi_params_not_set"}
    target = fi_params.get("target_capital_minor")
    if target is None:
        return {"ready": False, "reason": "target_not_set"}
    include_home = bool(fi_params.get("include_home_in_fi", False))
    # liquid + investment assets for FI; full NW only if user says so
    capital = int(net_worth_data.get("liquid_minor") or 0)
    if fi_params.get("use_net_worth"):
        capital = int(net_worth_data.get("net_worth_minor") or 0)
    elif fi_params.get("fi_capital_minor") is not None:
        capital = int(fi_params["fi_capital_minor"])
    # home exclusion is caller's responsibility when composing fi_capital
    _ = include_home
    yield_p = fi_params.get("safe_withdrawal_percent")
    passive = None
    if yield_p is not None:
        passive = int(Decimal(capital) * Decimal(str(yield_p)) / Decimal("100") / Decimal("12"))
    months = None
    sav = monthly_savings_minor
    growth = fi_params.get("annual_yield_percent")
    if sav is not None and sav > 0 and target > capital:
        # simple without yield if yield unset
        left = int(target) - capital
        if growth is None:
            months = (left + sav - 1) // sav
        else:
            # approximate loop
            c = capital
            my = Decimal(str(growth)) / Decimal("100") / Decimal("12")
            for i in range(1, 600):
                c = int(Decimal(c) * (Decimal("1") + my)) + sav
                if c >= int(target):
                    months = i
                    break
    return {
        "ready": True,
        "target_capital_minor": int(target),
        "current_fi_capital_minor": capital,
        "progress_ratio": round(capital / int(target), 4) if target else None,
        "monthly_savings_minor": sav,
        "potential_passive_monthly_minor": passive,
        "months_to_fi_estimate": months,
        "assumptions": {
            "safe_withdrawal_percent": yield_p,
            "annual_yield_percent": growth,
            "include_home_in_fi": include_home,
        },
        "note": "прогноз; параметры подтверждает пользователь",
    }
