from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from . import ledger
from .money import BASE_CURRENCY, SUPPORTED

ROOT_DEFAULT = Path(__file__).resolve().parents[2] / "harvest" / "Финансы" / "Капитал"

KINDS = {
    "account": "accounts",
    "category": "categories",
    "transaction": "transactions",
    "asset": "assets",
    "liability": "liabilities",
    "goal": "goals",
    "recurring": "recurring",
    "valuation": "valuations",
    "scenario": "scenarios",
    "journal": "_journal",
    "fx_rate": "fx_rates",
    "balance_statement": "balance_statements",
    "fi_params": "fi_params",
}

REQUIRED_TX = {"kind", "type", "date", "amount_minor", "currency", "account_id", "status"}
TX_TYPES = {
    "income",
    "expense",
    "transfer",
    "debt_principal",
    "debt_interest",
    "adjustment",
}
TX_STATUSES = {"actual", "planned", "estimated", "forecast", "void"}


class CapitalStore:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or ROOT_DEFAULT)
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for d in KINDS.values():
            (self.root / d).mkdir(parents=True, exist_ok=True)
        (self.root / "_backups").mkdir(parents=True, exist_ok=True)

    def _lock_path(self) -> Path:
        return self.root / "_meta.lock"

    def _acquire(self, timeout: float = 5.0) -> None:
        lock = self._lock_path()
        start = time.time()
        while True:
            try:
                fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(os.getpid()).encode())
                os.close(fd)
                return
            except FileExistsError:
                if time.time() - start > timeout:
                    try:
                        age = time.time() - lock.stat().st_mtime
                        if age > 120:
                            lock.unlink(missing_ok=True)
                            continue
                    except OSError:
                        pass
                    raise TimeoutError("capital store locked")
                time.sleep(0.05)

    def _release(self) -> None:
        self._lock_path().unlink(missing_ok=True)

    def new_id(self, prefix: str) -> str:
        day = date.today().strftime("%Y%m%d")
        return f"cap-{prefix}-{day}-{secrets.token_hex(2)}"

    def _atomic_write(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
        fd, tmp = tempfile.mkstemp(prefix=".cap_", suffix=".yaml", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    def _backup(self, path: Path) -> None:
        if not path.exists():
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = self.root / "_backups" / f"{path.stem}.{stamp}.yaml"
        dest.write_bytes(path.read_bytes())

    def path_for(self, kind: str, entity_id: str) -> Path:
        folder = KINDS[kind]
        # path traversal guard
        if ".." in entity_id or "/" in entity_id or "\\" in entity_id:
            raise ValueError("invalid id")
        return self.root / folder / f"{entity_id}.yaml"

    def list_kind(self, kind: str) -> list[dict]:
        folder = self.root / KINDS[kind]
        items = []
        for p in sorted(folder.glob("*.yaml")):
            if p.name.startswith("."):
                continue
            items.append(yaml.safe_load(p.read_text(encoding="utf-8")))
        return [x for x in items if x]

    def get(self, kind: str, entity_id: str) -> dict | None:
        p = self.path_for(kind, entity_id)
        if not p.exists():
            return None
        return yaml.safe_load(p.read_text(encoding="utf-8"))

    def validate_transaction(self, tx: dict, accounts: list[dict] | None = None) -> list[str]:
        errs = []
        missing = REQUIRED_TX - set(tx)
        if missing:
            errs.append(f"missing fields: {sorted(missing)}")
        if tx.get("type") not in TX_TYPES:
            errs.append("bad type")
        if tx.get("status") not in TX_STATUSES:
            errs.append("bad status")
        cur = (tx.get("currency") or "").upper()
        if cur and cur not in SUPPORTED:
            errs.append(f"unsupported currency {cur}")
        try:
            amt = int(tx.get("amount_minor"))
            if amt < 0:
                errs.append("amount_minor must be >= 0")
        except (TypeError, ValueError):
            errs.append("amount_minor must be int")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(tx.get("date") or "")):
            errs.append("date must be YYYY-MM-DD")
        if tx.get("type") == "transfer" and not tx.get("counterparty_account_id"):
            errs.append("transfer needs counterparty_account_id")
        if tx.get("type") in ("debt_principal", "debt_interest") and not tx.get("liability_id"):
            errs.append("debt ops need liability_id")
        if tx.get("type") == "adjustment" and not tx.get("corrects_id") and not tx.get("comment"):
            errs.append("adjustment needs corrects_id or comment")
        accs = accounts if accounts is not None else self.list_kind("account")
        ids = {a["id"] for a in accs}
        if tx.get("account_id") not in ids:
            errs.append("unknown account_id")
        if tx.get("counterparty_account_id") and tx["counterparty_account_id"] not in ids:
            errs.append("unknown counterparty_account_id")
        if tx.get("liability_id"):
            lids = {l["id"] for l in self.list_kind("liability")}
            if tx["liability_id"] not in lids:
                errs.append("unknown liability_id")
        return errs

    def find_duplicate_tx(self, tx: dict) -> dict | None:
        for other in self.list_kind("transaction"):
            if other.get("status") == "void":
                continue
            if other.get("id") == tx.get("id"):
                continue
            if (
                other.get("date") == tx.get("date")
                and other.get("type") == tx.get("type")
                and other.get("account_id") == tx.get("account_id")
                and int(other.get("amount_minor") or 0) == int(tx.get("amount_minor") or 0)
                and (other.get("comment") or "") == (tx.get("comment") or "")
                and (other.get("liability_id") or "") == (tx.get("liability_id") or "")
            ):
                return other
        return None

    def upsert(self, kind: str, data: dict, *, allow_overwrite: bool = True) -> dict:
        if data.get("kind") != kind:
            data["kind"] = kind
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not data.get("id"):
            prefix = {
                "account": "acc",
                "category": "cat",
                "transaction": "tx",
                "asset": "ast",
                "liability": "lia",
                "goal": "goal",
                "recurring": "rec",
                "valuation": "val",
                "scenario": "scn",
                "journal": "jrn",
                "fx_rate": "fx",
                "balance_statement": "bst",
                "fi_params": "fi",
            }[kind]
            data["id"] = self.new_id(prefix)
        if not data.get("created_at"):
            data["created_at"] = now
        data["updated_at"] = now
        data["schema"] = "capital.v1"
        data.setdefault("privacy", "sensitive")

        path = self.path_for(kind, data["id"])
        self._acquire()
        try:
            if path.exists():
                self._backup(path)
                if not allow_overwrite:
                    raise FileExistsError(data["id"])
            self._atomic_write(path, data)
            return data
        finally:
            self._release()

    def _write_unlocked(self, kind: str, data: dict) -> dict:
        """Write while lock already held."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if data.get("kind") != kind:
            data["kind"] = kind
        if not data.get("id"):
            raise ValueError("id required for unlocked write")
        if not data.get("created_at"):
            data["created_at"] = now
        data["updated_at"] = now
        data["schema"] = "capital.v1"
        data.setdefault("privacy", "sensitive")
        path = self.path_for(kind, data["id"])
        if path.exists():
            self._backup(path)
        self._atomic_write(path, data)
        return data

    def void_transaction(self, tx_id: str, reason: str) -> dict:
        tx = self.get("transaction", tx_id)
        if not tx:
            raise KeyError(tx_id)
        self._acquire()
        try:
            return self._void_unlocked(tx, reason)
        finally:
            self._release()

    def _void_unlocked(self, tx: dict, reason: str) -> dict:
        path = self.path_for("transaction", tx["id"])
        self._backup(path)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        tx = dict(tx)
        tx["status"] = "void"
        tx["void_reason"] = reason
        tx["updated_at"] = now
        self._atomic_write(path, tx)
        j = {
            "id": self.new_id("jrn"),
            "kind": "journal",
            "event": "void",
            "target_id": tx["id"],
            "reason": reason,
            "at": now,
            "snapshot": json.loads(json.dumps(tx, default=str)),
        }
        self._atomic_write(self.path_for("journal", j["id"]), j)
        return tx

    def correct_transaction(self, tx_id: str, patch: dict, reason: str) -> dict:
        """Atomic void + replacement + journal under one lock."""
        old = self.get("transaction", tx_id)
        if not old:
            raise KeyError(tx_id)
        if old.get("status") == "void":
            raise ValueError("cannot correct void transaction")
        new_tx = dict(old)
        new_tx.update(patch)
        new_tx["id"] = self.new_id("tx")
        new_tx["corrects_id"] = tx_id
        new_tx["status"] = patch.get("status", old.get("status", "actual"))
        new_tx.pop("void_reason", None)
        new_tx["kind"] = "transaction"
        errs = self.validate_transaction(new_tx)
        if errs:
            raise ValueError("; ".join(errs))

        self._acquire()
        try:
            # re-read under lock
            old2 = yaml.safe_load(self.path_for("transaction", tx_id).read_text(encoding="utf-8"))
            if not old2 or old2.get("status") == "void":
                raise ValueError("transaction already void or missing")
            self._void_unlocked(old2, reason=f"corrected→{new_tx['id']}: {reason}")
            saved = self._write_unlocked("transaction", new_tx)
            j = {
                "id": self.new_id("jrn"),
                "kind": "journal",
                "event": "correct",
                "target_id": tx_id,
                "replacement_id": saved["id"],
                "reason": reason,
                "at": saved["updated_at"],
            }
            self._write_unlocked("journal", j)
            return saved
        finally:
            self._release()

    def confirm_planned(self, planned_id: str, *, actual_date: str | None = None, patch: dict | None = None) -> dict:
        """Mark planned as void-linked and create actual; or convert via correct semantics."""
        planned = self.get("transaction", planned_id)
        if not planned:
            raise KeyError(planned_id)
        if planned.get("status") != "planned":
            raise ValueError("not a planned transaction")
        patch = dict(patch or {})
        patch["status"] = "actual"
        if actual_date:
            patch["date"] = actual_date
        patch["fulfills_planned_id"] = planned_id
        return self.correct_transaction(planned_id, patch, reason="confirm planned→actual")

    def set_liability_principal(
        self,
        liability_id: str,
        principal_remaining_minor: int,
        as_of: str,
        *,
        source: str = "bank_statement",
        note: str = "",
    ) -> dict:
        """Bank-reported remaining principal — preferred when interest split unknown."""
        lia = self.get("liability", liability_id)
        if not lia:
            raise KeyError(liability_id)
        lia = dict(lia)
        lia["principal_remaining_minor"] = int(principal_remaining_minor)
        lia["principal_as_of"] = as_of
        lia["principal_known"] = True
        lia["principal_source"] = source
        if note:
            lia["note"] = ((lia.get("note") or "") + f"\n{as_of}: {note}").strip()
        return self.upsert("liability", lia)

    def materialize_recurring(self, year_month: str, *, day: int = 1) -> list[dict]:
        """Create planned txs for templates not yet materialized in year_month."""
        if not re.match(r"^\d{4}-\d{2}$", year_month):
            raise ValueError("year_month must be YYYY-MM")
        date_str = f"{year_month}-{day:02d}"
        existing = self.list_kind("transaction")
        covered = {
            t.get("recurring_id")
            for t in existing
            if t.get("status") != "void"
            and t.get("recurring_id")
            and (t.get("date") or "").startswith(year_month)
        }
        created = []
        for r in self.list_kind("recurring"):
            if r.get("archived") or r.get("status") == "void":
                continue
            if r["id"] in covered:
                continue
            if not r.get("account_id"):
                continue
            tx = {
                "kind": "transaction",
                "type": r["type"],
                "date": date_str,
                "amount_minor": int(r["amount_minor"]),
                "currency": r.get("currency", "RUB"),
                "account_id": r["account_id"],
                "category_id": r.get("category_id"),
                "comment": r.get("comment") or r.get("name") or "",
                "status": "planned",
                "source": "recurring_materialize",
                "recurring_id": r["id"],
                "liability_id": r.get("liability_id"),
            }
            if r.get("type") == "transfer":
                tx["counterparty_account_id"] = r.get("counterparty_account_id")
            errs = self.validate_transaction(tx)
            if errs:
                continue
            created.append(self.upsert("transaction", tx))
        return created

    def record_fx_rate(
        self,
        from_currency: str,
        to_currency: str,
        rate: str,
        rate_date: str,
        *,
        source: str = "user",
    ) -> dict:
        fr, to = from_currency.upper(), to_currency.upper()
        if fr not in SUPPORTED or to not in SUPPORTED:
            raise ValueError("unsupported currency")
        if fr == to:
            raise ValueError("same currency")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", rate_date):
            raise ValueError("date must be YYYY-MM-DD")
        data = {
            "kind": "fx_rate",
            "from_currency": fr,
            "to_currency": to,
            "rate": str(rate),
            "date": rate_date,
            "status": "actual",
            "source": source,
        }
        return self.upsert("fx_rate", data)

    def record_balance_statement(
        self,
        account_id: str,
        balance_minor: int,
        statement_date: str,
        *,
        source: str = "bank",
        note: str = "",
    ) -> dict:
        """Reconcile: store statement and optionally set account opening/known."""
        acc = self.get("account", account_id)
        if not acc:
            raise KeyError(account_id)
        stmt = {
            "kind": "balance_statement",
            "account_id": account_id,
            "date": statement_date,
            "balance_minor": int(balance_minor),
            "currency": acc.get("currency", "RUB"),
            "status": "actual",
            "source": source,
            "note": note,
        }
        saved = self.upsert("balance_statement", stmt)
        # Update account known flag + opening as statement baseline for book calc
        # Strategy: set opening_balance to statement, opening_date to statement_date,
        # so only txs after statement_date affect book balance vs bank.
        acc = dict(acc)
        book = ledger.account_balances(
            [acc],
            [t for t in self.list_kind("transaction") if t.get("account_id") == account_id or t.get("counterparty_account_id") == account_id],
            as_of=statement_date,
            include_archived=True,
        ).get(account_id, {})
        book_bal = book.get("balance_minor") if book.get("known") else None
        acc["balance_known"] = True
        acc["last_statement_date"] = statement_date
        acc["last_statement_minor"] = int(balance_minor)
        if book_bal is None:
            acc["opening_balance_minor"] = int(balance_minor)
            acc["opening_date"] = statement_date
        else:
            # keep books; store variance
            acc["last_reconcile_variance_minor"] = int(balance_minor) - int(book_bal)
        self.upsert("account", acc)
        saved["book_balance_minor"] = book_bal
        saved["variance_minor"] = (
            None if book_bal is None else int(balance_minor) - int(book_bal)
        )
        return saved

    def get_fi_params(self) -> dict | None:
        items = self.list_kind("fi_params")
        if not items:
            return None
        return sorted(items, key=lambda x: x.get("updated_at") or "")[-1]

    def summary(self, date_from: str, date_to: str) -> dict:
        accounts_all = self.list_kind("account")
        accounts = [a for a in accounts_all if not a.get("archived")]
        txs = self.list_kind("transaction")
        assets = self.list_kind("asset")
        liabilities = self.list_kind("liability")
        valuations = self.list_kind("valuation")
        goals = self.list_kind("goal")
        fx_rates = self.list_kind("fx_rate")
        recurring = [r for r in self.list_kind("recurring") if not r.get("archived")]
        categories = self.list_kind("category")
        scenarios = self.list_kind("scenario")
        as_of = date_to if date_to <= date.today().isoformat() else date.today().isoformat()

        bals = ledger.account_balances(accounts_all, txs, as_of=as_of, include_archived=False)
        lia_map = ledger.liability_principals(liabilities, txs, as_of=as_of)
        flows = ledger.period_flows(txs, date_from, date_to)
        planned_flows = ledger.period_flows(txs, date_from, date_to, statuses={"planned"})
        planned_combined = ledger.planned_without_double_count(txs, recurring, date_from, date_to)
        recurring_month = ledger.recurring_monthly_net(recurring)
        nw = ledger.net_worth(bals, assets, lia_map, valuations, fx_rates=fx_rates, as_of=as_of)
        by_cat = ledger.expense_by_category(txs, date_from, date_to)
        months = sorted({t["date"][:7] for t in txs if t.get("date") and date_from <= t["date"] <= date_to})
        if not months:
            months = sorted({date_from[:7], date_to[:7]})
        series = ledger.monthly_series(txs, months)
        series_planned = ledger.monthly_series(txs, months, statuses={"planned"})
        budget = ledger.budget_view(txs, recurring, categories, date_from, date_to)
        fi_params = self.get_fi_params()
        # savings estimate: only if budget free_cash_complete OR user set monthly_savings
        monthly_sav = None
        if fi_params and fi_params.get("monthly_savings_minor") is not None:
            monthly_sav = int(fi_params["monthly_savings_minor"])
        elif budget.get("free_cash_complete") and budget.get("free_after_known_fixed_minor") is not None:
            monthly_sav = int(budget["free_after_known_fixed_minor"]) - int(budget.get("savings_plan_minor") or 0)
            # still incomplete signal — prefer explicit
            monthly_sav = budget.get("savings_plan_minor") or None
        fi = ledger.fi_progress(fi_params, nw, monthly_sav)

        # balances for UI: include unknown markers
        balances_ui = {
            k: v["balance_minor"] if v.get("known") else None for k, v in bals.items()
        }
        balances_meta = bals

        planned_txs = [t for t in txs if t.get("status") == "planned"]
        journal = sorted(self.list_kind("journal"), key=lambda x: x.get("at") or "", reverse=True)[:50]

        return {
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "base_currency": BASE_CURRENCY,
            "period": {"from": date_from, "to": date_to},
            "accounts": accounts,
            "balances": balances_ui,
            "balances_meta": balances_meta,
            "flows": flows,
            "planned_flows": planned_flows,
            "planned_combined": planned_combined,
            "recurring": recurring,
            "recurring_monthly": recurring_month,
            "net_worth": nw,
            "expense_by_category": by_cat,
            "monthly": series,
            "monthly_planned": series_planned,
            "budget": budget,
            "assets": assets,
            "liabilities": [
                {**l, "computed_principal_minor": (lia_map.get(l["id"]) or {}).get("principal_remaining_minor")}
                for l in liabilities
                if not l.get("archived")
            ],
            "liability_principals": lia_map,
            "goals": goals,
            "scenarios": scenarios,
            "fx_rates": fx_rates,
            "fi": fi,
            "fi_params": fi_params,
            "transactions": sorted(txs, key=lambda x: (x.get("date") or "", x.get("id") or ""), reverse=True),
            "planned_transactions": sorted(planned_txs, key=lambda x: x.get("date") or ""),
            "categories": categories,
            "journal": journal,
            "note": "actual / planned / forecast separated; unknown balance ≠ 0; FX only with explicit rates",
        }
