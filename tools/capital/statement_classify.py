"""Local rule-based classification for bank imports. No LLM."""

from __future__ import annotations

import re
from typing import Any


BANK_TO_HARVEST = {
    "супермаркеты": "Продукты",
    "рестораны и кафе": "Кафе и рестораны",
    "фастфуд": "Кафе и рестораны",
    "транспорт": "Транспорт",
    "такси": "Транспорт",
    "азс": "Автомобиль",
    "автоуслуги": "Автомобиль",
    "аптеки": "Здоровье",
    "медицинские услуги": "Здоровье",
    "одежда и обувь": "Одежда",
    "развлечения": "Развлечения",
    "образование": "Образование",
    "жкх": "Коммунальные услуги",
    "связь": "Связь и интернет",
    "путешествия": "Путешествия",
    "дом и ремонт": "Дом и ремонт",
    "красота": "Уход за собой",
    "прочие операции": "Требует классификации",
    "перевод": "Переводы",
    "снятие наличных": "Наличные",
    "пополнение": "Пополнения",
    "финансовые услуги": "Финансовые услуги",
    "кэшбэк": "Кешбэк",
    "кешбэк": "Кешбэк",
}

# merchant / description substring → harvest category (lower)
MERCHANT_RULES_DEFAULT = [
    (r"\byandex[\s.]?go\b|\buber\b|\bтакси\b", "Транспорт"),
    (r"\bpyaterochka\b|\bпятерочк|\bmagnit\b|\bмагнит\b|\blenta\b|\bлента\b", "Продукты"),
    (r"\bapteka\b|\bаптек", "Здоровье"),
    (r"\bazs\b|\bлукойл\b|\bгазпромнефть\b|\brosneft\b", "Автомобиль"),
]

ECONOMIC_HINTS = [
    # (regex on desc+category, economic_kind, ledger_type, confirmed?)
    (r"зарплат|заработн|salary|wage|начислен.*оплат.*труд", "salary", "income", True),
    (r"кэшбэк|кешбэк|cashback", "cashback", "income", True),
    (r"процент.*вклад|начислен.*процент|interest", "bank_interest", "income", True),
    (r"комисси[яи]|commission|fee\b", "bank_fee", "expense", True),
    (r"ипотек|mortgage|жкх.*ипотек", "mortgage", "expense", True),
    (r"брокер|invest|тинькофф\s*инвест|сбер\s*инвест|пополнен.*брокер", "investment_funding", "transfer", True),
    (r"снятие наличных|atm|банкомат|cash\s*out", "atm_withdraw", "expense", True),
    (r"внесение наличных|cash\s*in|пополнение.*наличн", "cash_deposit", "income", True),
    (r"возврат|refund|отмен.*операц", "refund", "income", True),
    (r"перевод.*себе|между своими|internal\s*transfer|свой сч[её]т", "transfer_internal", "transfer", True),
    (r"перевод", "transfer_other", "transfer", False),
]


def normalize_bank_category(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip())


def harvest_category_for_bank(bank_category: str) -> str:
    key = normalize_bank_category(bank_category).lower()
    if key in BANK_TO_HARVEST:
        return BANK_TO_HARVEST[key]
    # unknown bank category → create under same name, but flag review if "прочие"
    if "прочие" in key:
        return "Требует классификации"
    # Title-case bank category as harvest name
    return normalize_bank_category(bank_category) or "Требует классификации"


def apply_rules(
    op: dict[str, Any],
    user_rules: list[dict] | None = None,
) -> dict[str, Any]:
    """
    Priority: user rules → merchant/description → bank category.
    Returns classification fields.
    """
    bank_cat = normalize_bank_category(op.get("bank_category") or "")
    desc = (op.get("description") or "").lower()
    merchant = (op.get("merchant") or "").lower()
    blob = f"{bank_cat} {merchant} {desc}".lower()
    direction = op.get("direction") or "out"

    harvest_cat = None
    economic = None
    ledger_type = None
    confirmed = True
    rule_id = None
    source = "bank_category"

    # 1) user rules
    for r in user_rules or []:
        if r.get("archived") or r.get("status") == "void":
            continue
        pat = (r.get("pattern") or "").lower()
        match_field = r.get("match") or "description"  # merchant|description|bank_category
        hay = {"merchant": merchant, "description": desc, "bank_category": bank_cat.lower()}.get(match_field, desc)
        if not pat:
            continue
        if pat in hay or (r.get("regex") and re.search(pat, hay, re.I)):
            harvest_cat = r.get("category_name")
            economic = r.get("economic_kind")
            ledger_type = r.get("ledger_type")
            confirmed = r.get("confirmed", True)
            rule_id = r.get("id")
            source = "user_rule"
            break

    # 2) merchant/default regex
    if harvest_cat is None:
        for pat, cat in MERCHANT_RULES_DEFAULT:
            if re.search(pat, blob, re.I):
                harvest_cat = cat
                source = "merchant_rule"
                break

    # 3) bank category map
    if harvest_cat is None:
        harvest_cat = harvest_category_for_bank(bank_cat)
        source = "bank_category"

    # economic classification
    strong_hint = False
    if economic is None:
        economic = "purchase" if direction == "out" else "other_income"
        ledger_type = "expense" if direction == "out" else "income"
        for pat, ek, lt, conf in ECONOMIC_HINTS:
            if re.search(pat, blob, re.I):
                economic = ek
                ledger_type = lt
                confirmed = conf
                # Explicit text/merchant signals beat generic bank bucket «Прочие операции»
                strong_hint = ek in {
                    "salary",
                    "cashback",
                    "bank_interest",
                    "bank_fee",
                    "mortgage",
                    "atm_withdraw",
                    "cash_deposit",
                    "refund",
                    "investment_funding",
                    "transfer_internal",
                }
                break
        # «Прочие операции» alone is not enough to call something salary/expense —
        # but do NOT wipe a strong description/merchant match (e.g. «Заработная плата»).
        if "прочие" in bank_cat.lower() and not strong_hint:
            confirmed = False
            if economic in ("purchase", "other_income"):
                economic = "undefined"
                ledger_type = "expense" if direction == "out" else "income"

    if economic == "salary" and (harvest_cat is None or harvest_cat == "Требует классификации"):
        harvest_cat = "Зарплата"
        if source == "bank_category":
            source = "economic_hint"

    if harvest_cat == "Требует классификации":
        confirmed = False
        if economic == "purchase":
            economic = "undefined"

    # transfers: not consumer expense
    if economic in ("transfer_internal", "transfer_other", "investment_funding"):
        ledger_type = "transfer"
        # without counterparty we keep as expense/income that is excluded from analytics via flags
        # Prefer: type expense/income with exclude_from_analytics — but schema uses type.
        # Use transfer only when counterparty known; else mark meta.
        if not op.get("counterparty_account_id"):
            ledger_type = "expense" if direction == "out" else "income"

    classification_status = "confirmed" if confirmed else "needs_review"
    include_in_flows = confirmed and economic not in (
        "transfer_internal",
        "transfer_other",
        "investment_funding",
        "undefined",
    )
    # purchases and confirmed income/fees etc.
    if confirmed and economic in (
        "purchase",
        "salary",
        "cashback",
        "bank_interest",
        "bank_fee",
        "mortgage",
        "atm_withdraw",
        "cash_deposit",
        "refund",
        "other_income",
    ):
        include_in_flows = True
    if economic in ("transfer_internal", "transfer_other", "investment_funding", "undefined"):
        include_in_flows = False
    if not confirmed:
        include_in_flows = False

    return {
        "category_name": harvest_cat,
        "economic_kind": economic,
        "ledger_type": ledger_type or ("expense" if direction == "out" else "income"),
        "classification_status": classification_status,
        "include_in_flows": include_in_flows,
        "rule_id": rule_id,
        "classification_source": source,
    }
