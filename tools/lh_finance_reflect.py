#!/usr/bin/env python3
"""Тонкий мост сценария F: класс сверки Capital → черновик наблюдения.

Читает локальный API http://127.0.0.1:8777/api/summary или /api/health.
В stdout и в markdown попадают только класс сверки, класс сообщения и
булевы флаги полноты. Суммы, маски счетов, проводки и сырой ledger не
печатаются и не записываются. Совет команда не сочиняет.

no_totals в языке наблюдения записывается как missing.
"""

from __future__ import annotations

import argparse
import json
import re
import secrets
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARVEST = ROOT / "harvest"
DEFAULT_BASE = "http://127.0.0.1:8777"
TIMEOUT_SEC = 2.0

OBSERVATION_CLASS = {
    "matched": "matched",
    "mismatch": "mismatch",
    "no_totals": "missing",
    "missing": "missing",
}
SAFE_TOKENS = frozenset(OBSERVATION_CLASS)
FLAG_SPECS = (
    ("net_worth", "liquid_complete", "liquid_complete"),
    ("net_worth", "complete", "net_worth_complete"),
    ("net_worth", "has_estimates", "has_estimates"),
    ("budget", "free_cash_complete", "free_cash_complete"),
)
COMPLETENESS_KEYS = frozenset(
    {
        "liquid_complete",
        "net_worth_complete",
        "has_estimates",
        "free_cash_complete",
        "fx_complete",
        "accounts_complete",
    }
)
TEMPLATE_REL = "harvest/Мозг/_system/templates/Шаблон финансового наблюдения.md"
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
ID_RE = re.compile(r"id: lh-\d{8}-[a-z0-9]{4}")
QUEUE_RE = re.compile(r"queue_id: stm-\d{8}-[a-z0-9]{4}")
SUFFIX_RE = re.compile(r"[a-z0-9]{4}")
GOAL_RE = re.compile(r"^\[\[[^\[\]\n]{1,120}\]\]$")
POISON_RE = re.compile(
    r"(amount_minor|balance_minor|net_worth_minor|salary|зарплат|₽|(?<![а-яёa-z])руб(?![а-яёa-z])|\*{2,}\d|\d\*{2,})",
    re.IGNORECASE,
)
ADVICE_RE = re.compile(r"(рекоменд|следует|надо\s|стоит\s)", re.IGNORECASE)


class FinanceReflectError(ValueError):
    """Отказ: путь не тот или публичный текст не прошёл проверку."""


class Offline(Exception):
    """Локальный API не ответил. Тело ответа сюда не кладётся."""


def offline_report() -> dict:
    return {
        "ok": True,
        "reachability": "offline",
        "source": "none",
        "reconciliation_status": None,
        "message_class": None,
        "completeness": {},
        "detail": "offline",
    }


def health_only_report() -> dict:
    return {
        "ok": True,
        "reachability": "online",
        "source": "health",
        "reconciliation_status": None,
        "message_class": None,
        "completeness": {},
        "detail": "summary_unavailable",
    }


def classify_status(value: object) -> tuple[str, str]:
    """Возвращает (слово для наблюдения, класс сообщения).

    Сырая строка, если она не один из четырёх токенов, наружу не выходит.
    """
    if isinstance(value, str):
        token = value.strip().casefold()
        if token in SAFE_TOKENS:
            return OBSERVATION_CLASS[token], token
    return "missing", "missing"


def _bool_flag(container: object, key: str) -> bool | None:
    if not isinstance(container, dict):
        return None
    value = container.get(key)
    if isinstance(value, bool):
        return value
    return None


def extract_completeness(data: dict) -> dict:
    flags: dict[str, bool] = {}
    for section, source_key, public_key in FLAG_SPECS:
        value = _bool_flag(data.get(section), source_key)
        if value is not None:
            flags[public_key] = value
    net_worth = data.get("net_worth") if isinstance(data.get("net_worth"), dict) else {}
    missing_fx = net_worth.get("missing_fx")
    if isinstance(missing_fx, list):
        flags["fx_complete"] = len(missing_fx) == 0
    unknown_accounts = net_worth.get("unknown_accounts")
    if isinstance(unknown_accounts, list):
        flags["accounts_complete"] = len(unknown_accounts) == 0
    return {key: flags[key] for key in sorted(flags) if key in COMPLETENESS_KEYS}


def extract_period(data: dict) -> dict | None:
    period = data.get("period")
    if not isinstance(period, dict):
        return None
    out: dict[str, str] = {}
    for key in ("from", "to"):
        value = period.get(key)
        if isinstance(value, str) and DATE_RE.fullmatch(value):
            out[key] = value
    return out or None


def interpret_summary(payload: object, source: str = "summary") -> dict:
    if not isinstance(payload, dict):
        return health_only_report()
    if payload.get("ok") is False and not isinstance(payload.get("data"), dict):
        return health_only_report()
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return health_only_report()
    recon = data.get("reconciliation") if isinstance(data.get("reconciliation"), dict) else {}
    observed, message_class = classify_status(recon.get("status") if isinstance(recon, dict) else None)
    if not isinstance(recon, dict) or "status" not in recon:
        observed, message_class = "missing", "missing"
    report = {
        "ok": True,
        "reachability": "online",
        "source": source,
        "reconciliation_status": observed,
        "message_class": message_class,
        "completeness": extract_completeness(data),
    }
    period = extract_period(data)
    if period:
        report["period"] = period
    return report


def probe(get_json) -> dict:
    try:
        payload = get_json("/api/summary")
    except Offline:
        try:
            get_json("/api/health")
        except Offline:
            return offline_report()
        return health_only_report()
    return interpret_summary(payload, source="summary")


def _allowed_local_url(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.port != 8777:
        raise FinanceReflectError("только http://127.0.0.1:8777")


def http_get_json(url: str, timeout: float = TIMEOUT_SEC) -> dict:
    _allowed_local_url(url)
    request = urllib.request.Request(url, headers={"Accept": "application/json", "X-LH-Capital": "local"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise Offline("offline") from exc
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise Offline("offline") from exc
    if not isinstance(loaded, dict):
        raise Offline("offline")
    return loaded


def default_get(base: str = DEFAULT_BASE):
    root = base.rstrip("/")

    def get_json(path: str) -> dict:
        return http_get_json(root + path, timeout=TIMEOUT_SEC)

    return get_json


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return False
    return True


def collect_status(*, fixture: Path | None = None, get_json=None, base: str = DEFAULT_BASE) -> dict:
    if fixture is not None:
        if not fixture.is_file():
            raise FinanceReflectError("нет фикстуры")
        try:
            loaded = json.loads(fixture.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise FinanceReflectError("фикстура не JSON") from exc
        report = interpret_summary(loaded, source="fixture")
        report["reachability"] = "fixture"
        report["source"] = "fixture"
        return report
    getter = get_json if get_json is not None else default_get(base)
    return probe(getter)


def unexpected_digits(text: str) -> bool:
    cleaned = DATE_RE.sub("", text)
    cleaned = ID_RE.sub("", cleaned)
    cleaned = QUEUE_RE.sub("", cleaned)
    return re.search(r"\d", cleaned) is not None


def assert_public_text(text: str) -> None:
    if unexpected_digits(text):
        raise FinanceReflectError("публичный текст содержит цифру вне даты и id")
    if POISON_RE.search(text):
        raise FinanceReflectError("публичный текст содержит денежный или масочный маркер")
    if ADVICE_RE.search(text):
        raise FinanceReflectError("публичный текст содержит сформулированный совет")


def assert_public_payload(payload: dict, *, skip_keys: frozenset[str] = frozenset()) -> None:
    visible = {key: value for key, value in payload.items() if key not in skip_keys}
    assert_public_text(json.dumps(visible, ensure_ascii=False, sort_keys=True))


def clean_goal(value: str | None) -> str:
    if value is None or not str(value).strip():
        return ""
    text = str(value).strip()
    if not GOAL_RE.fullmatch(text):
        raise FinanceReflectError("цель — одна вики-ссылка [[...]]")
    if re.search(r"\d", text):
        raise FinanceReflectError("в ссылке цели не должно быть цифр")
    return text


def placement(path: Path) -> str:
    resolved = path.resolve()
    if resolved.suffix.lower() != ".md":
        raise FinanceReflectError("нужен путь .md")
    if resolved.exists():
        raise FinanceReflectError("файл уже есть")
    try:
        rel = resolved.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        rel = None
    if rel is not None:
        if rel == TEMPLATE_REL:
            raise FinanceReflectError("бланк эта команда не меняет")
        if not rel.startswith("harvest/Мозг/_system/"):
            raise FinanceReflectError("внутри репозитория черновик можно писать только в harvest/Мозг/_system")
        if rel.startswith("harvest/Финансы/") or rel.endswith("capital.js"):
            raise FinanceReflectError("ledger и личные финансовые карточки не пишутся")
        kind = "stm" if "/stm/items/" in rel else "system"
    else:
        kind = "system"
    if not resolved.parent.is_dir():
        raise FinanceReflectError("каталог назначения не существует")
    return kind


def _suffix(explicit: str | None) -> str:
    if explicit is None:
        return secrets.token_hex(2)
    if not SUFFIX_RE.fullmatch(explicit):
        raise FinanceReflectError("id — четыре символа a-z0-9")
    return explicit


def _yaml_quote(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def written_class(report: dict) -> str:
    status = report.get("reconciliation_status")
    if status in {"matched", "mismatch", "missing"}:
        return str(status)
    return "missing"


def render_observation(
    report: dict,
    *,
    kind: str,
    when: date,
    goal: str = "",
    ident: str | None = None,
) -> str:
    if kind not in {"system", "stm"}:
        raise FinanceReflectError("kind: system или stm")
    day = when.isoformat()
    suffix = _suffix(ident)
    card_id = f"lh-{day.replace('-', '')}-{suffix}"
    observed = written_class(report)
    message_class = report.get("message_class")
    if message_class not in SAFE_TOKENS:
        message_class = None
    reach = str(report.get("reachability") or "none")
    source_kind = str(report.get("source") or "none")
    live = reach == "online" and source_kind == "summary"
    synthetic = not live
    privacy = "sensitive" if live else "personal"
    confidence = "medium" if live else "low"
    if source_kind == "fixture":
        source = "CLI lh_finance_reflect.py draft-observation — фикстура, не книги владельца"
        lead = (
            "**Синтетика.** Класс сверки снят с фикстуры, не с книг владельца. "
            "Суммы и маски счетов сюда не копируются. Команда совет не пишет."
        )
        title = "STM — финансовое наблюдение" if kind == "stm" else "DEMO — финансовое наблюдение"
    elif reach == "offline":
        source = "CLI lh_finance_reflect.py draft-observation — API offline, книги не читались"
        lead = (
            "**Синтетика.** Локальный API не ответил. Слово missing здесь значит, что класса сверки "
            "в ответе нет, а не то, что книги разошлись. Суммы сюда не копируются. Команда совет не пишет."
        )
        title = "STM — финансовое наблюдение" if kind == "stm" else "DEMO — финансовое наблюдение"
    elif source_kind == "health":
        source = "CLI lh_finance_reflect.py draft-observation — health без summary"
        lead = (
            "**Синтетика.** Ответ health есть, summary со сверкой нет. Слово missing — отсутствие поля, "
            "не вывод о книгах. Суммы сюда не копируются. Команда совет не пишет."
        )
        title = "STM — финансовое наблюдение" if kind == "stm" else "DEMO — финансовое наблюдение"
    else:
        source = "CLI lh_finance_reflect.py draft-observation — класс сверки локального API, без сумм"
        lead = (
            "Класс сверки снят с локального API. Суммы и маски счетов сюда не копируются. "
            "Команда совет не пишет."
        )
        title = "STM — финансовое наблюдение" if kind == "stm" else "Финансовое наблюдение"

    lines = [
        "---",
        f"id: {card_id}",
        "type: note",
        f"created: {day}",
        f"updated: {day}",
        "status: draft",
        f"source: {_yaml_quote(source)}",
        f"confidence: {confidence}",
        f"privacy: {privacy}",
        "related:",
        '  - "[[Шаблон финансового наблюдения]]"',
        '  - "[[Reflection Engine]]"',
        "tags: [protocol]",
        "aliases: []",
        f"synthetic: {'true' if synthetic else 'false'}",
        "finance_observation_status: open",
        f"reconciliation_class: {observed}",
        f"goal: {_yaml_quote(goal)}",
        'hypothesis: ""',
    ]
    if kind == "stm":
        lines.extend(
            [
                f"queue_id: stm-{day.replace('-', '')}-{suffix}",
                "queue_status: new",
                'proposed_name: "Финансовое наблюдение"',
                'target_card: ""',
                'audit_category: ""',
                "allow_link_only: false",
            ]
        )
    lines.append("---")
    lines.append("")
    lines.append(f"# {title}")
    lines.append("")
    lines.append(lead)
    lines.append("")
    lines.append("## Сверка")
    lines.append("")
    lines.append(f"сверка: {observed}")
    lines.append("")
    if message_class:
        lines.append(f"message_class: {message_class}")
        lines.append("")
    lines.append(f"Доступ к API: {reach}.")
    lines.append("")
    lines.append("## Полнота")
    lines.append("")
    completeness = report.get("completeness") if isinstance(report.get("completeness"), dict) else {}
    safe_flags = []
    for key in sorted(COMPLETENESS_KEYS):
        value = completeness.get(key)
        if isinstance(value, bool):
            safe_flags.append(f"- {key}: {'true' if value else 'false'}")
    if safe_flags:
        lines.extend(safe_flags)
    else:
        lines.append("Флаги полноты не получены.")
    lines.append("")
    period = report.get("period") if isinstance(report.get("period"), dict) else {}
    if isinstance(period.get("from"), str) and isinstance(period.get("to"), str):
        lines.append("## Период")
        lines.append("")
        lines.append(f"{period['from']} — {period['to']}")
        lines.append("")
    lines.append("## Гипотеза")
    lines.append("")
    lines.append("Пусто.")
    lines.append("")
    lines.append("## Открытый вопрос")
    lines.append("")
    lines.append("что проверить")
    lines.append("")
    lines.append("## Связанная цель")
    lines.append("")
    lines.append(goal if goal else "Не задана.")
    lines.append("")
    lines.append("## История")
    lines.append("")
    lines.append(
        f"- {day} — finance_observation_status пусто → open — сверка: {observed} — "
        "CLI lh_finance_reflect.py draft-observation"
    )
    lines.append("")
    text = "\n".join(lines)
    assert_public_text(text)
    return text


def draft_observation(
    path: Path,
    report: dict,
    *,
    when: date | None = None,
    goal: str | None = None,
    ident: str | None = None,
    kind: str | None = None,
) -> dict:
    target = path.resolve()
    detected = placement(target)
    use_kind = kind or detected
    if kind == "stm" and detected != "stm" and _inside_repo(target):
        raise FinanceReflectError("STM пишется только в harvest/Мозг/_system/stm/items")
    if use_kind not in {"system", "stm"}:
        raise FinanceReflectError("kind: system или stm")
    goal_text = clean_goal(goal)
    current = when or date.today()
    body = render_observation(report, kind=use_kind, when=current, goal=goal_text, ident=ident)
    target.write_text(body, encoding="utf-8", newline="\n")
    try:
        rel = target.relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        rel = target.as_posix()
    payload = {
        "ok": True,
        "path": rel,
        "kind": use_kind,
        "reachability": report.get("reachability"),
        "source": report.get("source"),
        "reconciliation_status": written_class(report),
        "message_class": report.get("message_class") if report.get("message_class") in SAFE_TOKENS else None,
        "completeness": {
            key: value
            for key, value in (report.get("completeness") or {}).items()
            if key in COMPLETENESS_KEYS and isinstance(value, bool)
        },
        "finance_observation_status": "open",
        "synthetic": not (report.get("reachability") == "online" and report.get("source") == "summary"),
    }
    assert_public_payload(payload, skip_keys=frozenset({"path"}))
    return payload


def public_status(report: dict) -> dict:
    payload = {
        "ok": True,
        "reachability": report.get("reachability"),
        "source": report.get("source"),
        "reconciliation_status": report.get("reconciliation_status"),
        "message_class": report.get("message_class") if report.get("message_class") in SAFE_TOKENS else None,
        "completeness": {
            key: value
            for key, value in (report.get("completeness") or {}).items()
            if key in COMPLETENESS_KEYS and isinstance(value, bool)
        },
    }
    period = report.get("period")
    if isinstance(period, dict):
        safe_period = {
            key: period[key]
            for key in ("from", "to")
            if isinstance(period.get(key), str) and DATE_RE.fullmatch(period[key])
        }
        if safe_period:
            payload["period"] = safe_period
    if report.get("detail") in {"offline", "summary_unavailable"}:
        payload["detail"] = report["detail"]
    assert_public_text(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return payload


def _parse_day(value: str | None) -> date:
    if not value:
        return date.today()
    if not DATE_RE.fullmatch(value):
        raise FinanceReflectError("дата нужна в виде YYYY-MM-DD")
    return date.fromisoformat(value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Класс сверки Capital и черновик финансового наблюдения. Суммы не печатает."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    status = sub.add_parser("status", help="Класс сверки и флаги полноты, без сумм")
    status.add_argument("--fixture", type=Path, default=None, help="JSON вместо живого API")

    draft = sub.add_parser("draft-observation", help="Черновик наблюдения: класс сверки и вопрос, без совета")
    draft.add_argument("--out", type=Path, required=True)
    draft.add_argument("--fixture", type=Path, default=None)
    draft.add_argument("--goal", default=None, help="Одна вики-ссылка [[...]] без цифр")
    draft.add_argument("--date", default=None, help="YYYY-MM-DD")
    draft.add_argument("--kind", choices=("system", "stm"), default=None)

    args = parser.parse_args(argv)
    try:
        report = collect_status(fixture=args.fixture)
        if args.cmd == "status":
            payload = public_status(report)
        else:
            payload = draft_observation(
                args.out,
                report,
                when=_parse_day(args.date),
                goal=args.goal,
                kind=args.kind,
            )
    except FinanceReflectError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
