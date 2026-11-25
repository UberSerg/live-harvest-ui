"""Import bank statement into Capital YAML ledger."""

from __future__ import annotations

import base64
import secrets
from datetime import date, datetime, timezone
from typing import Any

from . import statement_classify, statement_parse
from .money import to_minor


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_import_plan(
    store: Any,
    *,
    account_id: str,
    text: str,
    currency: str = "RUB",
) -> dict[str, Any]:
    """Parse + classify without writing. Safe for dry-run."""
    if not text or not text.strip():
        return {"ok": False, "error": "empty_statement"}
    acc = store.get("account", account_id)
    if not acc:
        return {"ok": False, "error": "unknown_account"}

    parsed = statement_parse.parse_statement(text, currency=currency or acc.get("currency") or "RUB")
    recon = parsed.get("reconciliation") or {}
    bank_totals = parsed.get("bank_totals") or {}
    if parsed["count"] == 0:
        return {
            "ok": False,
            "error": "no_operations_parsed",
            "unrecognized_count": parsed.get("unrecognized_count", 0),
            "unrecognized_preview": (parsed.get("unrecognized_lines") or [])[:5],
            "reconciliation": recon,
            "bank_totals": bank_totals,
        }

    # Critical: too many orphan lines relative to ops → abort
    unrec = parsed.get("unrecognized_count") or 0
    if unrec > max(20, parsed["count"] // 5):
        return {
            "ok": False,
            "error": "parse_integrity_failed",
            "detail": f"unrecognized_lines={unrec} ops={parsed['count']}",
            "unrecognized_preview": (parsed.get("unrecognized_lines") or [])[:8],
            "reconciliation": recon,
            "bank_totals": bank_totals,
        }

    # Footer totals present but don't match parsed ops → stop package save
    if recon.get("status") == "mismatch":
        return {
            "ok": False,
            "error": "reconciliation_mismatch",
            "detail": recon.get("message"),
            "reconciliation": recon,
            "bank_totals": bank_totals,
            "parsed_count": parsed["count"],
            "sum_in_minor": parsed.get("sum_in_minor"),
            "sum_out_minor": parsed.get("sum_out_minor"),
            "date_from": parsed.get("date_from"),
            "date_to": parsed.get("date_to"),
        }

    rules = store.list_kind("classification_rule")
    existing = store.list_kind("transaction")
    fp_index = {
        t.get("fingerprint"): t
        for t in existing
        if t.get("fingerprint") and t.get("status") != "void"
    }

    cats = {c["name"]: c for c in store.list_kind("category")}
    to_create_cats: dict[str, dict] = {}
    prepared = []
    duplicates = []
    needs_review = []
    confirmed = []

    for op in parsed["operations"]:
        fp = statement_parse.ParsedOp(
            operation_date=op["operation_date"],
            operation_time=op["operation_time"],
            processing_date=op.get("processing_date"),
            authorization_code=op.get("authorization_code"),
            bank_category=op["bank_category"],
            description=op.get("description") or "",
            merchant=op.get("merchant") or "",
            amount_minor=op["amount_minor"],
            direction=op["direction"],
            currency=op.get("currency") or "RUB",
        ).fingerprint(account_id)

        if fp in fp_index:
            duplicates.append({"fingerprint": fp, "existing_id": fp_index[fp].get("id")})
            continue

        clf = statement_classify.apply_rules(op, rules)
        cat_name = clf["category_name"]
        if cat_name not in cats and cat_name not in to_create_cats:
            to_create_cats[cat_name] = {
                "kind": "category",
                "name": cat_name,
                "category_kind": "expense" if op["direction"] == "out" else "income",
                "budget_bucket": "expense_variable" if op["direction"] == "out" else "income_extra",
                "status": "actual",
                "source": "bank_import",
            }

        row = {
            **op,
            "fingerprint": fp,
            **clf,
            "category_name": cat_name,
        }
        prepared.append(row)
        if clf["classification_status"] == "needs_review":
            needs_review.append(row)
        else:
            confirmed.append(row)

    return {
        "ok": True,
        "account_id": account_id,
        "parsed_count": parsed["count"],
        "to_import": len(prepared),
        "duplicates": len(duplicates),
        "duplicate_samples": duplicates[:10],
        "needs_review": len(needs_review),
        "confirmed": len(confirmed),
        "categories_to_create": list(to_create_cats.keys()),
        "date_from": parsed.get("date_from"),
        "date_to": parsed.get("date_to"),
        "sum_in_minor": parsed.get("sum_in_minor"),
        "sum_out_minor": parsed.get("sum_out_minor"),
        "unrecognized_count": unrec,
        "bank_totals": bank_totals,
        "reconciliation": recon,
        "_prepared": prepared,
        "_cats": to_create_cats,
    }


def execute_import(store: Any, plan: dict[str, Any], *, source_label: str = "paste") -> dict[str, Any]:
    if not plan.get("ok"):
        return plan
    account_id = plan["account_id"]
    batch_id = f"cap-batch-{date.today().strftime('%Y%m%d')}-{secrets.token_hex(3)}"
    now = _now()
    created_cats = []
    created_txs = []

    # categories first
    cat_ids = {c["name"]: c["id"] for c in store.list_kind("category")}
    for name, data in (plan.get("_cats") or {}).items():
        if name in cat_ids:
            continue
        saved = store.upsert("category", data)
        cat_ids[name] = saved["id"]
        created_cats.append(saved["id"])

    for row in plan.get("_prepared") or []:
        cat_id = cat_ids.get(row["category_name"])
        tx = {
            "kind": "transaction",
            "type": row["ledger_type"],
            "date": row["operation_date"],
            "operation_time": row.get("operation_time"),
            "processing_date": row.get("processing_date"),
            "authorization_code": row.get("authorization_code"),
            "amount_minor": int(row["amount_minor"]),
            "currency": row.get("currency") or "RUB",
            "account_id": account_id,
            "category_id": cat_id,
            "bank_category": row.get("bank_category"),
            "merchant": row.get("merchant"),
            "comment": (row.get("description") or "")[:300],
            "description": (row.get("description") or "")[:500],
            "direction": row.get("direction"),
            "economic_kind": row.get("economic_kind"),
            "classification_status": row.get("classification_status"),
            "include_in_flows": bool(row.get("include_in_flows")),
            "classification_source": row.get("classification_source"),
            "fingerprint": row["fingerprint"],
            "batch_id": batch_id,
            "status": "actual",
            "source": "bank_import",
            "imported_at": now,
            "privacy": "sensitive",
        }
        # Pairing hint for transfers left empty
        saved = store.upsert("transaction", tx)
        created_txs.append(saved["id"])

    recon = plan.get("reconciliation") or {}
    bank_totals = plan.get("bank_totals") or {}
    batch = {
        "kind": "import_batch",
        "id": batch_id,
        "account_id": account_id,
        "source_label": source_label,  # paste|txt|pdf — not raw text
        "imported_at": now,
        "date_from": plan.get("date_from"),
        "date_to": plan.get("date_to"),
        "parsed_count": plan.get("parsed_count"),
        "imported_count": len(created_txs),
        "duplicates_skipped": plan.get("duplicates"),
        "needs_review": plan.get("needs_review"),
        "categories_created": len(created_cats),
        "transaction_ids": created_txs,
        "sum_in_minor": plan.get("sum_in_minor"),
        "sum_out_minor": plan.get("sum_out_minor"),
        "bank_total_in_minor": bank_totals.get("bank_total_in_minor"),
        "bank_total_out_minor": bank_totals.get("bank_total_out_minor"),
        "reconciliation_status": recon.get("status") or "no_totals",
        "reconciliation_message": recon.get("message") or "",
        "status": "actual",
        "source": "bank_import",
        "privacy": "sensitive",
        # NEVER store raw statement text
    }
    store.upsert("import_batch", batch)
    store.upsert(
        "journal",
        {
            "kind": "journal",
            "event": "import_batch",
            "target_id": batch_id,
            "reason": f"imported {len(created_txs)} ops",
            "at": now,
        },
    )

    # Harvest questions queue (grouped)
    questions = group_review_questions(plan.get("_prepared") or [])
    if questions:
        store.upsert(
            "import_batch",
            {
                **batch,
                "harvester_queue": questions,
            },
        )

    return {
        "ok": True,
        "batch_id": batch_id,
        "imported": len(created_txs),
        "duplicates_skipped": plan.get("duplicates"),
        "categories_created": len(created_cats),
        "needs_review": plan.get("needs_review"),
        "unrecognized_lines": plan.get("unrecognized_count"),
        "date_from": plan.get("date_from"),
        "date_to": plan.get("date_to"),
        "sum_in_minor": plan.get("sum_in_minor"),
        "sum_out_minor": plan.get("sum_out_minor"),
        "reconciliation": recon,
        "harvester_queue": questions,
    }


def repair_bank_import_metadata(store: Any) -> dict[str, Any]:
    """
    Fix existing bank_import txs: direction, economic defaults.
    Does not invent balances or delete data. No raw statement required.
    """
    rules = store.list_kind("classification_rule")
    updated = 0
    for tx in store.list_kind("transaction"):
        if tx.get("status") == "void":
            continue
        if tx.get("source") != "bank_import" and not tx.get("fingerprint"):
            continue
        changed = False
        tx = dict(tx)
        if not tx.get("direction"):
            if tx.get("type") in ("income",):
                tx["direction"] = "in"
                changed = True
            elif tx.get("type") in ("expense", "debt_interest", "debt_principal"):
                tx["direction"] = "out"
                changed = True
        if not tx.get("economic_kind") or tx.get("classification_status") is None:
            op = {
                "bank_category": tx.get("bank_category") or "",
                "description": tx.get("description") or tx.get("comment") or "",
                "merchant": tx.get("merchant") or "",
                "direction": tx.get("direction") or "out",
            }
            clf = statement_classify.apply_rules(op, rules)
            for k in (
                "economic_kind",
                "classification_status",
                "include_in_flows",
                "classification_source",
            ):
                if tx.get(k) is None or (k == "economic_kind" and not tx.get(k)):
                    tx[k] = clf[k]
                    changed = True
            if not tx.get("type") or tx.get("type") not in (
                "income",
                "expense",
                "transfer",
                "debt_principal",
                "debt_interest",
                "adjustment",
            ):
                tx["type"] = clf["ledger_type"]
                changed = True
        if changed:
            store.upsert("transaction", tx)
            updated += 1

    # refresh batch reconcile status from stored op sums vs stored bank totals
    batches_fixed = 0
    for batch in store.list_kind("import_batch"):
        if batch.get("status") == "void":
            continue
        ids = set(batch.get("transaction_ids") or [])
        txs = [t for t in store.list_kind("transaction") if t.get("id") in ids and t.get("status") != "void"]
        sum_in = sum(int(t["amount_minor"]) for t in txs if t.get("direction") == "in")
        sum_out = sum(int(t["amount_minor"]) for t in txs if t.get("direction") == "out")
        recon = statement_parse.reconcile_ops_to_totals(
            sum_in,
            sum_out,
            batch.get("bank_total_in_minor"),
            batch.get("bank_total_out_minor"),
        )
        batch = dict(batch)
        batch["sum_in_minor"] = sum_in
        batch["sum_out_minor"] = sum_out
        batch["reconciliation_status"] = recon["status"]
        batch["reconciliation_message"] = recon["message"]
        store.upsert("import_batch", batch)
        batches_fixed += 1

    return {"ok": True, "transactions_updated": updated, "batches_refreshed": batches_fixed}


def group_review_questions(prepared: list[dict]) -> list[dict]:
    """Group similar needs_review ops into one question each."""
    buckets: dict[str, dict] = {}
    for row in prepared:
        if row.get("classification_status") != "needs_review":
            continue
        key = (
            (row.get("merchant") or row.get("bank_category") or "other").lower().strip()
            + "|"
            + (row.get("direction") or "")
        )
        b = buckets.setdefault(
            key,
            {
                "merchant": row.get("merchant"),
                "bank_category": row.get("bank_category"),
                "direction": row.get("direction"),
                "count": 0,
                "amount_sum_minor": 0,
                "fingerprints": [],
                "sample_description": row.get("description"),
            },
        )
        b["count"] += 1
        b["amount_sum_minor"] += int(row.get("amount_minor") or 0)
        b["fingerprints"].append(row["fingerprint"])
    out = []
    for i, b in enumerate(buckets.values(), 1):
        out.append(
            {
                "id": f"q{i}",
                "question": (
                    f"Что это за операции ({b['count']}×) «{b['merchant'] or b['bank_category']}» "
                    f"на сумму ~{b['amount_sum_minor']/100:.2f}? "
                    f"Доход / расход / перевод себе / перевод людям / другое?"
                ),
                **b,
            }
        )
    return out


def void_batch(store: Any, batch_id: str, reason: str = "user void import") -> dict[str, Any]:
    batch = store.get("import_batch", batch_id)
    if not batch:
        raise KeyError(batch_id)
    n = 0
    for tx_id in batch.get("transaction_ids") or []:
        tx = store.get("transaction", tx_id)
        if tx and tx.get("status") != "void":
            store.void_transaction(tx_id, reason=f"void batch {batch_id}: {reason}")
            n += 1
    batch = dict(batch)
    batch["status"] = "void"
    batch["void_reason"] = reason
    batch["updated_at"] = _now()
    store.upsert("import_batch", batch)
    return {"ok": True, "voided_transactions": n, "batch_id": batch_id}


def decode_upload_payload(body: dict) -> tuple[str, str]:
    """Return (text, source_label). Never logs content."""
    if body.get("text"):
        return str(body["text"]), "paste"
    b64 = body.get("file_base64")
    filename = body.get("filename") or "upload.txt"
    if not b64:
        raise ValueError("text or file_base64 required")
    raw = base64.b64decode(b64)
    text = statement_parse.extract_text_from_upload(filename, raw)
    label = "pdf" if filename.lower().endswith(".pdf") else "txt"
    return text, label


def remember_rule(store: Any, *, match: str, pattern: str, category_name: str, economic_kind: str, ledger_type: str) -> dict:
    data = {
        "kind": "classification_rule",
        "match": match,
        "pattern": pattern,
        "category_name": category_name,
        "economic_kind": economic_kind,
        "ledger_type": ledger_type,
        "confirmed": True,
        "status": "actual",
        "source": "user",
        "privacy": "sensitive",
    }
    return store.upsert("classification_rule", data)


def apply_classification_to_similar(
    store: Any,
    *,
    fingerprints: list[str],
    category_name: str,
    economic_kind: str,
    ledger_type: str,
    remember: dict | None = None,
) -> dict:
    cats = {c["name"]: c for c in store.list_kind("category")}
    if category_name not in cats:
        cat = store.upsert(
            "category",
            {
                "kind": "category",
                "name": category_name,
                "category_kind": "expense" if ledger_type == "expense" else "income",
                "status": "actual",
                "source": "user",
            },
        )
        cats[category_name] = cat
    cat_id = cats[category_name]["id"]
    updated = 0
    for tx in store.list_kind("transaction"):
        if tx.get("fingerprint") not in fingerprints:
            continue
        if tx.get("status") == "void":
            continue
        patch = {
            "category_id": cat_id,
            "economic_kind": economic_kind,
            "type": ledger_type,
            "classification_status": "confirmed",
            "include_in_flows": economic_kind
            not in ("transfer_internal", "transfer_other", "investment_funding", "undefined"),
        }
        # correct via upsert overwrite (same id) with backup
        new = {**tx, **patch}
        store.upsert("transaction", new)
        updated += 1
    rule = None
    if remember:
        rule = remember_rule(store, **remember)
    return {"ok": True, "updated": updated, "rule": rule}
