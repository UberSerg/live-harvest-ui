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
}

REQUIRED_TX = {"kind", "type", "date", "amount_minor", "currency", "account_id", "status"}


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
                    # stale lock > 120s → break
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
        if tx.get("type") not in {
            "income",
            "expense",
            "transfer",
            "debt_principal",
            "debt_interest",
            "adjustment",
        }:
            errs.append("bad type")
        if tx.get("status") not in {"actual", "planned", "estimated", "forecast", "void"}:
            errs.append("bad status")
        try:
            int(tx.get("amount_minor"))
        except (TypeError, ValueError):
            errs.append("amount_minor must be int")
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(tx.get("date") or "")):
            errs.append("date must be YYYY-MM-DD")
        if tx.get("type") == "transfer" and not tx.get("counterparty_account_id"):
            errs.append("transfer needs counterparty_account_id")
        if tx.get("type") == "adjustment" and not tx.get("corrects_id") and not tx.get("comment"):
            errs.append("adjustment needs corrects_id or comment")
        accs = accounts if accounts is not None else self.list_kind("account")
        ids = {a["id"] for a in accs}
        if tx.get("account_id") not in ids:
            errs.append("unknown account_id")
        if tx.get("counterparty_account_id") and tx["counterparty_account_id"] not in ids:
            errs.append("unknown counterparty_account_id")
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
            ):
                return other
        return None

    def upsert(self, kind: str, data: dict, *, allow_overwrite: bool = True) -> dict:
        if data.get("kind") != kind:
            data["kind"] = kind
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not data.get("id"):
            prefix = {"account": "acc", "category": "cat", "transaction": "tx", "asset": "ast", "liability": "lia", "goal": "goal", "recurring": "rec", "valuation": "val", "scenario": "scn", "journal": "jrn"}[kind]
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

    def void_transaction(self, tx_id: str, reason: str) -> dict:
        tx = self.get("transaction", tx_id)
        if not tx:
            raise KeyError(tx_id)
        self._acquire()
        try:
            path = self.path_for("transaction", tx_id)
            self._backup(path)
            now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            tx["status"] = "void"
            tx["void_reason"] = reason
            tx["updated_at"] = now
            self._atomic_write(path, tx)
            j = {
                "id": self.new_id("jrn"),
                "kind": "journal",
                "event": "void",
                "target_id": tx_id,
                "reason": reason,
                "at": now,
                "snapshot": json.loads(json.dumps(tx, default=str)),
            }
            self._atomic_write(self.path_for("journal", j["id"]), j)
            return tx
        finally:
            self._release()

    def correct_transaction(self, tx_id: str, patch: dict, reason: str) -> dict:
        """Void old + create replacement linked by corrects_id; journal both."""
        old = self.get("transaction", tx_id)
        if not old:
            raise KeyError(tx_id)
        new_tx = dict(old)
        new_tx.update(patch)
        new_tx["id"] = self.new_id("tx")
        new_tx["corrects_id"] = tx_id
        new_tx["status"] = patch.get("status", old.get("status", "actual"))
        new_tx.pop("void_reason", None)
        errs = self.validate_transaction(new_tx)
        if errs:
            raise ValueError("; ".join(errs))
        self.void_transaction(tx_id, reason=f"corrected→{new_tx['id']}: {reason}")
        saved = self.upsert("transaction", new_tx)
        j = {
            "id": self.new_id("jrn"),
            "kind": "journal",
            "event": "correct",
            "target_id": tx_id,
            "replacement_id": saved["id"],
            "reason": reason,
            "at": saved["updated_at"],
        }
        self.upsert("journal", j)
        return saved

    def summary(self, date_from: str, date_to: str) -> dict:
        accounts_all = self.list_kind("account")
        accounts = [a for a in accounts_all if not a.get("archived")]
        txs = self.list_kind("transaction")
        assets = self.list_kind("asset")
        liabilities = self.list_kind("liability")
        valuations = self.list_kind("valuation")
        goals = self.list_kind("goal")
        bals = ledger.account_balances(accounts_all, txs)
        bals = {k: v for k, v in bals.items() if k in {a["id"] for a in accounts}}
        flows = ledger.period_flows(txs, date_from, date_to)
        nw = ledger.net_worth(bals, assets, liabilities, valuations)
        by_cat = ledger.expense_by_category(txs, date_from, date_to)
        # months in range (simple)
        months = sorted({t["date"][:7] for t in txs if t.get("date") and date_from <= t["date"] <= date_to})
        if not months:
            months = [date_from[:7], date_to[:7]]
            months = sorted(set(months))
        series = ledger.monthly_series(txs, months)
        return {
            "as_of": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "period": {"from": date_from, "to": date_to},
            "accounts": accounts,
            "balances": bals,
            "flows": flows,
            "net_worth": nw,
            "expense_by_category": by_cat,
            "monthly": series,
            "assets": assets,
            "liabilities": liabilities,
            "goals": goals,
            "transactions": sorted(txs, key=lambda x: x.get("date") or "", reverse=True),
            "categories": self.list_kind("category"),
            "note": "actual-only in flows/balances; estimates flagged in net_worth",
        }
