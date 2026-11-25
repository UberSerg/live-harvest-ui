from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


MINOR = {"RUB": 100, "USD": 100, "EUR": 100}


def to_minor(amount: str | int | Decimal, currency: str = "RUB") -> int:
    """Parse human amount to integer minor units. Rejects binary float input path."""
    if isinstance(amount, float):
        raise TypeError("float money forbidden; pass str/Decimal/int minor")
    if isinstance(amount, int):
        return amount
    scale = MINOR.get(currency.upper(), 100)
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
