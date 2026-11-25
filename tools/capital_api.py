#!/usr/bin/env python3
"""Local Capital API — bind 127.0.0.1 only."""

from __future__ import annotations

import json
import sys
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.capital.money import to_minor  # noqa: E402
from tools.capital.store import CapitalStore  # noqa: E402

HOST = "127.0.0.1"
PORT = 8777
STORE = CapitalStore()


def _json(handler: BaseHTTPRequestHandler, code: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    # local UI only
    origin = handler.headers.get("Origin", "")
    if origin.startswith("http://127.0.0.1:") or origin.startswith("http://localhost:"):
        handler.send_header("Access-Control-Allow-Origin", origin)
        handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        handler.send_header("Access-Control-Allow-Headers", "Content-Type, X-LH-Capital")
        handler.send_header("Vary", "Origin")
    handler.end_headers()
    handler.wfile.write(body)


def _check_mutation(handler: BaseHTTPRequestHandler) -> str | None:
    """Return error message or None if ok."""
    if handler.client_address[0] not in ("127.0.0.1", "::1"):
        return "non-local client rejected"
    origin = handler.headers.get("Origin", "")
    # allow no Origin (same-origin fetch from file unlikely) and local UI
    if origin and not (
        origin.startswith("http://127.0.0.1:") or origin.startswith("http://localhost:")
    ):
        return "origin not allowed"
    token = handler.headers.get("X-LH-Capital", "")
    if token != "local":
        return "missing or bad X-LH-Capital header"
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "LHCapital/0.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("capital_api: " + (fmt % args) + "\n")

    def do_OPTIONS(self) -> None:
        err = _check_mutation(self)
        # preflight: still only local
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            _json(self, 403, {"ok": False, "error": "forbidden"})
            return
        self.send_response(204)
        origin = self.headers.get("Origin", "")
        if origin.startswith("http://127.0.0.1:") or origin.startswith("http://localhost:"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-LH-Capital")
        self.end_headers()

    def do_GET(self) -> None:
        if self.client_address[0] not in ("127.0.0.1", "::1"):
            _json(self, 403, {"ok": False, "error": "forbidden"})
            return
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if u.path == "/api/health":
            _json(self, 200, {"ok": True, "service": "capital", "bind": f"{HOST}:{PORT}"})
            return
        if u.path == "/api/summary":
            today = date.today()
            dfrom = qs.get("from", [f"{today.year}-01-01"])[0]
            dto = qs.get("to", [today.isoformat()])[0]
            _json(self, 200, {"ok": True, "data": STORE.summary(dfrom, dto)})
            return
        if u.path == "/api/transactions":
            _json(self, 200, {"ok": True, "data": STORE.list_kind("transaction")})
            return
        if u.path == "/api/accounts":
            _json(self, 200, {"ok": True, "data": STORE.list_kind("account")})
            return
        if u.path == "/api/categories":
            _json(self, 200, {"ok": True, "data": STORE.list_kind("category")})
            return
        if u.path == "/api/recurring":
            _json(self, 200, {"ok": True, "data": STORE.list_kind("recurring")})
            return
        if u.path == "/api/liabilities":
            _json(self, 200, {"ok": True, "data": STORE.list_kind("liability")})
            return
        _json(self, 404, {"ok": False, "error": "not found"})

    def do_POST(self) -> None:
        err = _check_mutation(self)
        if err:
            _json(self, 403, {"ok": False, "error": err})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            _json(self, 400, {"ok": False, "error": "invalid json"})
            return
        u = urlparse(self.path)
        try:
            if u.path == "/api/accounts":
                data = {
                    "kind": "account",
                    "name": body["name"],
                    "account_kind": body.get("account_kind", "checking"),
                    "currency": body.get("currency", "RUB"),
                    "opening_balance_minor": int(body.get("opening_balance_minor") or 0),
                    "opening_date": body.get("opening_date") or date.today().isoformat(),
                    "status": body.get("status", "actual"),
                    "source": body.get("source", "user"),
                    "archived": False,
                }
                if "amount" in body and "opening_balance_minor" not in body:
                    data["opening_balance_minor"] = to_minor(body["amount"], data["currency"])
                saved = STORE.upsert("account", data)
                _json(self, 200, {"ok": True, "data": saved})
                return
            if u.path == "/api/transactions":
                currency = body.get("currency", "RUB")
                amount_minor = body.get("amount_minor")
                if amount_minor is None and "amount" in body:
                    amount_minor = to_minor(body["amount"], currency)
                tx = {
                    "kind": "transaction",
                    "type": body["type"],
                    "date": body["date"],
                    "amount_minor": int(amount_minor),
                    "currency": currency,
                    "account_id": body["account_id"],
                    "counterparty_account_id": body.get("counterparty_account_id"),
                    "category_id": body.get("category_id"),
                    "comment": body.get("comment") or "",
                    "status": body.get("status", "actual"),
                    "source": body.get("source", "user"),
                }
                if body.get("id"):
                    tx["id"] = body["id"]
                errs = STORE.validate_transaction(tx)
                if errs:
                    _json(self, 400, {"ok": False, "error": "; ".join(errs)})
                    return
                dup = STORE.find_duplicate_tx(tx)
                if dup and not body.get("allow_duplicate"):
                    _json(self, 409, {"ok": False, "error": "duplicate_suspect", "duplicate_id": dup["id"]})
                    return
                saved = STORE.upsert("transaction", tx)
                _json(self, 200, {"ok": True, "data": saved})
                return
            if u.path == "/api/transactions/void":
                saved = STORE.void_transaction(body["id"], body.get("reason") or "user void")
                _json(self, 200, {"ok": True, "data": saved})
                return
            if u.path == "/api/transactions/correct":
                saved = STORE.correct_transaction(
                    body["id"], body.get("patch") or {}, body.get("reason") or "correction"
                )
                _json(self, 200, {"ok": True, "data": saved})
                return
            if u.path == "/api/assets":
                data = {
                    "kind": "asset",
                    "name": body["name"],
                    "asset_kind": body.get("asset_kind", "other"),
                    "currency": body.get("currency", "RUB"),
                    "status": body.get("status", "estimated"),
                    "value_minor": int(body.get("value_minor") or 0),
                    "source": body.get("source", "user"),
                    "note": body.get("note") or "",
                    "harvest_link": body.get("harvest_link"),
                }
                saved = STORE.upsert("asset", data)
                if body.get("value_minor") is not None:
                    val = {
                        "kind": "valuation",
                        "asset_id": saved["id"],
                        "date": body.get("date") or date.today().isoformat(),
                        "value_minor": int(body["value_minor"]),
                        "currency": data["currency"],
                        "status": data["status"],
                        "source": data["source"],
                    }
                    STORE.upsert("valuation", val)
                _json(self, 200, {"ok": True, "data": saved})
                return
            if u.path == "/api/liabilities":
                data = {
                    "kind": "liability",
                    "name": body["name"],
                    "currency": body.get("currency", "RUB"),
                    "principal_remaining_minor": int(body.get("principal_remaining_minor") or 0),
                    "rate_apr_percent": body.get("rate_apr_percent"),
                    "payment_minor": body.get("payment_minor"),
                    "status": body.get("status", "estimated"),
                    "source": body.get("source", "user"),
                    "harvest_link": body.get("harvest_link"),
                    "note": body.get("note") or "",
                }
                saved = STORE.upsert("liability", data)
                _json(self, 200, {"ok": True, "data": saved})
                return
            if u.path == "/api/categories":
                data = {
                    "kind": "category",
                    "name": body["name"],
                    "category_kind": body.get("category_kind", "expense"),
                    "status": "actual",
                    "source": "user",
                }
                saved = STORE.upsert("category", data)
                _json(self, 200, {"ok": True, "data": saved})
                return
            if u.path == "/api/recurring":
                currency = body.get("currency", "RUB")
                amount_minor = body.get("amount_minor")
                if amount_minor is None and "amount" in body:
                    amount_minor = to_minor(body["amount"], currency)
                data = {
                    "kind": "recurring",
                    "name": body["name"],
                    "type": body["type"],
                    "amount_minor": int(amount_minor),
                    "currency": currency,
                    "cadence": body.get("cadence", "monthly"),
                    "account_id": body.get("account_id"),
                    "category_id": body.get("category_id"),
                    "status": body.get("status", "planned"),
                    "source": body.get("source", "user"),
                    "comment": body.get("comment") or "",
                    "harvest_link": body.get("harvest_link"),
                    "archived": False,
                }
                if body.get("id"):
                    data["id"] = body["id"]
                if data["type"] not in {
                    "income",
                    "expense",
                    "debt_interest",
                    "debt_principal",
                }:
                    _json(self, 400, {"ok": False, "error": "bad recurring type"})
                    return
                saved = STORE.upsert("recurring", data)
                _json(self, 200, {"ok": True, "data": saved})
                return
            _json(self, 404, {"ok": False, "error": "not found"})
        except KeyError as e:
            _json(self, 400, {"ok": False, "error": f"missing field {e}"})
        except ValueError as e:
            _json(self, 400, {"ok": False, "error": str(e)})
        except Exception as e:  # noqa: BLE001
            _json(self, 500, {"ok": False, "error": str(e)})


def main() -> None:
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Capital API on http://{HOST}:{PORT}/  (local only)", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
