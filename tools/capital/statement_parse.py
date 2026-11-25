"""Deterministic bank statement parser (T-Bank-like text export). No LLM / no network."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any


OP_START = re.compile(
    r"^(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\s+(.+?)\s+([+-]?(?:\d{1,3}(?:\s\d{3})*|\d+),\d{2})\s*$"
)
PROC_LINE = re.compile(
    r"^(\d{2}\.\d{2}\.\d{4})\s+(\d+)\s+(.*)$"
)
AMOUNT_RE = re.compile(r"^([+-]?(?:\d{1,3}(?:\s\d{3})*|\d+),\d{2})$")
PAGE_BANNER = re.compile(
    r"Индивидуальная выписка по счёту.*Страница\s+\d+\s+из\s+\d+",
    re.IGNORECASE,
)
CONTINUE_LINE = re.compile(r"^Продолжение на следующей странице\s*$", re.IGNORECASE)

HEADER_NOISE = {
    "ДАТА ОПЕРАЦИИ (МСК)",
    "Дата обработки1",
    "и код авторизации",
    "КАТЕГОРИЯ",
    "Описание операции",
    "СУММА В ВАЛЮТЕ СЧЁТА",
    "Сумма в валюте",
    "операции2",
    "Дата обработки",
    "и код авторизации1",
}

# Footer totals (T-Bank-like and close variants)
TOTAL_IN_RE = re.compile(
    r"(?:^|\b)(?:пополнение|поступления|всего\s+пополнен\w*|итого\s+пополнен\w*)\s*:?\s*\+?\s*"
    r"([+-]?(?:\d{1,3}(?:\s\d{3})*|\d+),\d{2})",
    re.IGNORECASE,
)
TOTAL_OUT_RE = re.compile(
    r"(?:^|\b)(?:списание|списания|всего\s+списан\w*|итого\s+списан\w*|расход(?:ы)?)\s*:?\s*\+?\s*"
    r"([+-]?(?:\d{1,3}(?:\s\d{3})*|\d+),\d{2})",
    re.IGNORECASE,
)
TOTAL_LINE_RE = re.compile(
    r"^(?:пополнение|поступления|списание|списания|всего\s+пополнен|всего\s+списан|итого\s+пополнен|итого\s+списан)",
    re.IGNORECASE,
)


@dataclass
class ParsedOp:
    operation_date: str  # YYYY-MM-DD
    operation_time: str  # HH:MM
    processing_date: str | None
    authorization_code: str | None
    bank_category: str
    description: str
    merchant: str
    amount_minor: int
    direction: str  # in | out
    currency: str = "RUB"
    raw_first_line: str = ""
    parse_ok: bool = True
    parse_error: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def fingerprint(self, account_id: str) -> str:
        desc = re.sub(r"\s+", " ", (self.description or "").strip().lower())
        # strip card masks already normalized
        desc = re.sub(r"\*{2,}\d{2,4}", "****", desc)
        key = "|".join(
            [
                account_id,
                self.operation_date,
                self.operation_time or "",
                self.direction,
                str(self.amount_minor),
                self.currency,
                self.authorization_code or "",
                desc[:240],
            ]
        )
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def normalize_text(text: str) -> str:
    if not text:
        return ""
    # NBSP, thin spaces, etc.
    t = unicodedata.normalize("NFKC", text)
    t = t.replace("\u00a0", " ").replace("\u202f", " ").replace("\u2009", " ")
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\t", " ")
    # collapse spaces but keep newlines
    lines = []
    for line in t.split("\n"):
        line = re.sub(r"[ ]{2,}", " ", line).strip()
        lines.append(line)
    return "\n".join(lines)


def _is_noise(line: str) -> bool:
    if not line:
        return True
    if line in HEADER_NOISE:
        return True
    if CONTINUE_LINE.match(line):
        return True
    if PAGE_BANNER.search(line):
        return True
    # bare header fragments
    low = line.lower()
    if low.startswith("индивидуальная выписка"):
        return True
    if re.fullmatch(r"Страница\s+\d+\s+из\s+\d+", line, re.I):
        return True
    if TOTAL_LINE_RE.match(line):
        # keep out of op stream; extracted separately
        return True
    return False


def strip_service_blocks(text: str) -> list[str]:
    out = []
    for line in normalize_text(text).split("\n"):
        if _is_noise(line):
            continue
        out.append(line)
    return out


def extract_bank_totals(text: str) -> dict[str, Any]:
    """Pull statement footer totals. Last matching value wins (final page)."""
    tot_in = None
    tot_out = None
    in_line = None
    out_line = None
    for line in normalize_text(text).split("\n"):
        if not line:
            continue
        low = line.lower()
        is_in = bool(re.search(r"пополнен|поступлен", low))
        is_out = bool(re.search(r"списан", low)) and not is_in
        if not is_in and not is_out:
            continue
        m = re.search(r"([+-]?(?:\d{1,3}(?:\s\d{3})*|\d+),\d{2})", line)
        if not m:
            continue
        try:
            amt, _dir = parse_amount_to_minor(m.group(1))
        except ValueError:
            continue
        if is_in:
            tot_in = amt
            in_line = line[:100]
        elif is_out:
            tot_out = amt
            out_line = line[:100]
    return {
        "bank_total_in_minor": tot_in,
        "bank_total_out_minor": tot_out,
        "has_totals": tot_in is not None or tot_out is not None,
        "total_in_line": in_line,
        "total_out_line": out_line,
    }


def reconcile_ops_to_totals(
    sum_in_minor: int,
    sum_out_minor: int,
    bank_total_in_minor: int | None,
    bank_total_out_minor: int | None,
) -> dict[str, Any]:
    """Compare parsed op sums to statement footer — must match to the kopeck."""
    if bank_total_in_minor is None and bank_total_out_minor is None:
        return {
            "status": "no_totals",
            "matched": None,
            "delta_in_minor": None,
            "delta_out_minor": None,
            "message": "Итоги выписки отсутствуют",
        }
    delta_in = None if bank_total_in_minor is None else int(sum_in_minor) - int(bank_total_in_minor)
    delta_out = None if bank_total_out_minor is None else int(sum_out_minor) - int(bank_total_out_minor)
    ok_in = delta_in is None or delta_in == 0
    ok_out = delta_out is None or delta_out == 0
    matched = ok_in and ok_out
    reasons = []
    if not ok_in:
        reasons.append(f"пополнение: parsed−bank={delta_in}")
    if not ok_out:
        reasons.append(f"списание: parsed−bank={delta_out}")
    return {
        "status": "matched" if matched else "mismatch",
        "matched": matched,
        "delta_in_minor": delta_in,
        "delta_out_minor": delta_out,
        "message": "Сверено до копейки" if matched else ("Обнаружено расхождение: " + "; ".join(reasons)),
        "reasons": reasons,
    }


def parse_amount_to_minor(token: str) -> tuple[int, str]:
    """Return (amount_minor absolute, direction in|out). + → in."""
    raw = token.strip()
    direction = "in" if raw.startswith("+") else "out"
    raw = raw.lstrip("+").replace(" ", "").replace("\u00a0", "")
    if "," in raw:
        whole, frac = raw.rsplit(",", 1)
    else:
        whole, frac = raw, "00"
    whole = whole.replace(".", "")
    frac = (frac + "00")[:2]
    minor = int(whole) * 100 + int(frac)
    return minor, direction


def dmy_to_iso(dmy: str) -> str:
    d, m, y = dmy.split(".")
    return f"{y}-{m}-{d}"


def _extract_merchant(description: str) -> str:
    d = description.strip()
    # drop trailing card op boilerplate
    d = re.sub(r"\.\s*Операция по карте\s*\*{0,4}\d+.*$", "", d, flags=re.I)
    d = re.sub(r"Операция по карте\s*\*{0,4}\d+.*$", "", d, flags=re.I)
    # mask any residual long digits (accounts)
    d = re.sub(r"\d{10,}", "[num]", d)
    d = re.sub(r"\*{4,}\d{2,6}", "****", d)
    # take first chunk before city/country codes often ALLCAPS
    part = d.split(".")[0].strip()
    part = re.sub(r"\s+", " ", part)
    return part[:120] if part else "unknown"


def parse_statement(text: str, *, currency: str = "RUB") -> dict[str, Any]:
    """
    Parse full statement text → ops + diagnostics.
    Never logs the raw text; caller must not print it.
    """
    lines = strip_service_blocks(text)
    ops: list[ParsedOp] = []
    unrecognized: list[dict[str, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = OP_START.match(line)
        if not m:
            # orphan line — keep for diagnostics
            if line and not _is_noise(line):
                unrecognized.append({"line_index": i, "text_preview": line[:80]})
            i += 1
            continue
        dmy, hm, mid, amount_tok = m.group(1), m.group(2), m.group(3).strip(), m.group(4)
        bank_category = mid
        try:
            amount_minor, direction = parse_amount_to_minor(amount_tok)
        except ValueError:
            unrecognized.append({"line_index": i, "text_preview": line[:80], "error": "bad_amount"})
            i += 1
            continue

        # accumulate until next op start
        body: list[str] = []
        j = i + 1
        while j < len(lines):
            if OP_START.match(lines[j]):
                break
            body.append(lines[j])
            j += 1

        processing_date = None
        auth_code = None
        desc_parts: list[str] = []
        for bl in body:
            pm = PROC_LINE.match(bl)
            if pm and processing_date is None:
                processing_date = dmy_to_iso(pm.group(1))
                auth_code = pm.group(2)
                rest = pm.group(3).strip()
                if rest:
                    desc_parts.append(rest)
            else:
                desc_parts.append(bl)

        description = " ".join(desc_parts).strip()
        description = re.sub(r"\s+", " ", description)
        # privacy: mask long digit sequences (accounts)
        description = re.sub(r"(?<!\*)\b\d{10,}\b", "[redacted]", description)
        merchant = _extract_merchant(description)

        ops.append(
            ParsedOp(
                operation_date=dmy_to_iso(dmy),
                operation_time=hm,
                processing_date=processing_date,
                authorization_code=auth_code,
                bank_category=bank_category,
                description=description,
                merchant=merchant,
                amount_minor=amount_minor,
                direction=direction,
                currency=currency.upper(),
                raw_first_line=f"{dmy} {hm} {bank_category} …",
            )
        )
        i = j

    sum_in = sum(o.amount_minor for o in ops if o.direction == "in")
    sum_out = sum(o.amount_minor for o in ops if o.direction == "out")
    totals = extract_bank_totals(text)
    recon = reconcile_ops_to_totals(
        sum_in,
        sum_out,
        totals.get("bank_total_in_minor"),
        totals.get("bank_total_out_minor"),
    )
    return {
        "ok": True,
        "operations": [asdict(o) for o in ops],
        "count": len(ops),
        "unrecognized_lines": unrecognized,
        "unrecognized_count": len(unrecognized),
        "date_from": min((o.operation_date for o in ops), default=None),
        "date_to": max((o.operation_date for o in ops), default=None),
        "sum_in_minor": sum_in,
        "sum_out_minor": sum_out,
        "bank_totals": totals,
        "reconciliation": recon,
    }


def extract_text_from_upload(filename: str, data: bytes) -> str:
    """TXT always; PDF if pypdf available. No network."""
    name = (filename or "").lower()
    if name.endswith(".txt") or name.endswith(".csv") or not name:
        for enc in ("utf-8", "cp1251", "utf-16"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")
    if name.endswith(".pdf"):
        try:
            from io import BytesIO

            from pypdf import PdfReader  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "PDF support requires local package pypdf. Paste text or upload TXT."
            ) from e
        reader = PdfReader(BytesIO(data))
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        return "\n".join(parts)
    raise RuntimeError("unsupported file type; use TXT or PDF with text layer")
