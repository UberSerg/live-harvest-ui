from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MINOR = {"RUB": 100, "USD": 100, "EUR": 100}
BASE_CURRENCY = "RUB"
SUPPORTED = frozenset({"RUB", "USD", "EUR"})


def to_minor(amount: str | int | Decimal, currency: str = "RUB") -> int:
    """Parse human amount to integer minor units. Rejects binary float input path."""
    if isinstance(amount, float):
        raise TypeError("float money forbidden; pass str/Decimal/int minor")
    if isinstance(amount, int):
        return amount
    cur = currency.upper()
    scale = MINOR.get(cur, 100)
    try:
        d = Decimal(str(amount)).quantize(Decimal(1) / Decimal(scale), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as e:
        raise ValueError(f"bad amount: {amount!r}") from e
    return int(d * scale)


def from_minor(minor: int, currency: str = "RUB") -> str:
    scale = MINOR.get(currency.upper(), 100)
    d = Decimal(minor) / Decimal(scale)
    return f"{d:.2f}"


def format_display(minor: int, currency: str = "RUB") -> str:
    return f"{from_minor(minor, currency)} {currency}"


def convert_minor(
    amount_minor: int,
    from_currency: str,
    to_currency: str,
    rate: Decimal | str | None,
) -> int | None:
    """
    Convert minor units using explicit rate: 1 from_currency = rate to_currency.
    Returns None if rate missing and currencies differ. Never invents a rate.
    """
    src = from_currency.upper()
    dst = to_currency.upper()
    if src == dst:
        return int(amount_minor)
    if rate is None:
        return None
    try:
        r = Decimal(str(rate))
    except (InvalidOperation, ValueError):
        return None
    if r <= 0:
        return None
    src_scale = Decimal(MINOR.get(src, 100))
    dst_scale = Decimal(MINOR.get(dst, 100))
    major = Decimal(amount_minor) / src_scale
    converted = (major * r * dst_scale).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(converted)
