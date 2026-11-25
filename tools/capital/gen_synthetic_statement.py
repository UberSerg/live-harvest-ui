"""Generate synthetic multi-page bank statement for tests. No personal data."""

from __future__ import annotations

from pathlib import Path

HEADER = """ДАТА ОПЕРАЦИИ (МСК)
Дата обработки1
и код авторизации
КАТЕГОРИЯ
Описание операции
СУММА В ВАЛЮТЕ СЧЁТА
Сумма в валюте
операции2"""

MERCHANTS = [
    ("Супермаркеты", "DEMO PYATEROCHKA MOSCOW RUS. Операция по карте ****0001", 45000, False),
    ("Супермаркеты", "DEMO MAGNIT MOSCOW RUS. Операция по карте ****0001", 128050, False),
    ("Рестораны и кафе", "DEMO CAFE MOSCOW RUS. Операция по карте ****0001", 35000, False),
    ("Фастфуд", "DEMO BURGER MOSCOW RUS. Операция по карте ****0001", 59000, False),
    ("Такси", "DEMO YANDEX GO MOSCOW RUS. Операция по карте ****0001", 42000, False),
    ("АЗС", "DEMO LUKOIL MOSCOW RUS. Операция по карте ****0001", 350000, False),
    ("Аптеки", "DEMO APTEKA MOSCOW RUS. Операция по карте ****0001", 89000, False),
    ("Связь", "DEMO MOBILE OPERATOR. Операция по карте ****0001", 55000, False),
    ("Развлечения", "DEMO CINEMA MOSCOW RUS. Операция по карте ****0001", 120000, False),
    ("Одежда и обувь", "DEMO FASHION STORE. Операция по карте ****0001", 499000, False),
    ("Прочие операции", "DEMO PAYMENT UNKNOWN", 15000055, True),  # income-like other
    ("Прочие операции", "DEMO TRANSFER SELF", 5000000, False),
    ("ЖКХ", "DEMO UTILITY MOSCOW", 1000000, False),
    ("Финансовые услуги", "DEMO CASHBACK ACCRUAL", 32000, True),
]

PAGE_SIZE = 12  # ops per page


def fmt_amount(minor: int, income: bool) -> str:
    sign = "+" if income else ""
    rub = minor // 100
    kop = minor % 100
    # thousands with spaces
    s = f"{rub:,}".replace(",", " ")
    return f"{sign}{s},{kop:02d}"


def build(pages: int = 30) -> str:
    lines: list[str] = [HEADER, ""]
    day = 1
    month = 9
    year = 2026
    auth = 100000
    op_i = 0
    total_ops = pages * PAGE_SIZE
    sum_in = 0
    sum_out = 0
    for p in range(1, pages + 1):
        if p > 1:
            lines.append("Продолжение на следующей странице")
            lines.append(f"Индивидуальная выписка по счёту дебетовой карты Страница {p} из {pages}")
            lines.append(HEADER)
            lines.append("")
        for _ in range(PAGE_SIZE):
            cat, desc, amount, income = MERCHANTS[op_i % len(MERCHANTS)]
            # vary amounts
            amount = amount + (op_i % 17) * 100
            if income:
                sum_in += amount
            else:
                sum_out += amount
            hour = 10 + (op_i % 10)
            minute = (op_i * 3) % 60
            dmy = f"{day:02d}.{month:02d}.{year}"
            # split description across page boundary occasionally
            if op_i % 37 == 0 and p < pages:
                lines.append(f"{dmy} {hour:02d}:{minute:02d} {cat} {fmt_amount(amount, income)}")
                lines.append(f"{dmy} {auth} {desc[:20]}")
                # page break mid-description
                lines.append("Продолжение на следующей странице")
                lines.append(f"Индивидуальная выписка по счёту дебетовой карты Страница {p} из {pages}")
                lines.append(HEADER)
                lines.append(desc[20:])
            else:
                lines.append(f"{dmy} {hour:02d}:{minute:02d} {cat} {fmt_amount(amount, income)}")
                lines.append(f"{dmy} {auth} {desc}")
            auth += 1
            op_i += 1
            day += 1
            if day > 28:
                day = 1
                month += 1
                if month > 12:
                    month = 1
                    year += 1
            if op_i >= total_ops:
                break
        if op_i >= total_ops:
            break
    lines.append("")
    lines.append(f"Пополнение +{fmt_amount(sum_in, False)}")
    lines.append(f"Списание {fmt_amount(sum_out, False)}")
    return "\n".join(lines) + "\n"


def main() -> None:
    out = Path(__file__).resolve().parent / "fixtures" / "synthetic_statement_30p.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    text = build(30)
    out.write_text(text, encoding="utf-8")
    print(f"OK {out} chars={len(text)} lines={text.count(chr(10))}")


if __name__ == "__main__":
    main()
