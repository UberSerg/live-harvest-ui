"""Mechanical contest marker check. Does not merge cards or read meaning.

Opt-in is the frontmatter key claim_track or contested. A heading
«Оспаривание» in a protocol note is not a contest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

HARVEST = Path(__file__).resolve().parents[1] / "harvest"
CLAIM_TITLES = ("Формулировка", "Утверждение", "Суть", "Факты")
VERBS = ("подтверждено", "оспорено", "уточнить")
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.M)
CONTEST_LINE_RE = re.compile(
    r"^[-*]\s+(\d{4}-\d{2}-\d{2})\s+[—–-]\s+(подтверждено|оспорено|уточнить)\s+[—–-]\s+причина:\s*(\S.*?)\s*$",
    re.M,
)
HISTORY_LINE_RE = re.compile(
    r"^[-*]\s+(\d{4}-\d{2}-\d{2})\s+[—–-]\s+(\S.*?)\s*$",
    re.M,
)
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_fm(text: str):
    if not text.startswith("---"):
        return None, text
    end = text.find("---", 3)
    if end == -1:
        return None, text
    try:
        fm = yaml.safe_load(text[3:end]) or {}
    except Exception:
        return {"_parse_error": True}, text[end + 3 :]
    if not isinstance(fm, dict):
        return {"_parse_error": True}, text[end + 3 :]
    return fm, text[end + 3 :]


def sections(body: str) -> dict[str, str]:
    matches = list(HEADING_RE.finditer(body))
    found: dict[str, str] = {}
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        found[title] = body[start:end]
    return found


def significant_claim_text(body: str) -> str:
    found = sections(body)
    parts = [found[title].strip() for title in CLAIM_TITLES if found.get(title, "").strip()]
    return "\n\n".join(parts)


def normalize_claim(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def claim_digest(text: str) -> str:
    return hashlib.sha256(normalize_claim(text).encode("utf-8")).hexdigest()


def _history_lines(block: str) -> list[tuple[str, str]]:
    return [(match.group(1), match.group(2)) for match in HISTORY_LINE_RE.finditer(block or "")]


def _records_dispute(line: str) -> bool:
    folded = line.casefold()
    return any(verb in folded for verb in VERBS) or "оспарив" in folded


def _records_change(line: str) -> bool:
    folded = line.casefold()
    return "→" in line or "->" in line or "было" in folded


def contest_findings(text: str, rel: str) -> list[dict]:
    """Return mechanical CONTEST findings. Empty when the card did not opt in."""
    fm, body = parse_fm(text)
    if not isinstance(fm, dict) or fm.get("_parse_error"):
        return []
    found = sections(body)
    contested_key = "contested" in fm
    track_key = "claim_track" in fm
    contested = fm.get("contested")
    tracked = fm.get("claim_track") is True
    if not contested_key and not track_key:
        return []

    findings: list[dict] = []

    def add(code: str, detail: str) -> None:
        safe = re.sub(r"[^A-Za-z0-9._/-]+", "-", rel)
        findings.append(
            {
                "id": f"{code}-{safe}",
                "category": "CONTEST",
                "path": rel.replace("\\", "/"),
                "title": Path(rel).stem,
                "code": code,
                "detail": detail,
            }
        )

    if contested_key and not isinstance(contested, bool):
        add("contested-not-bool", "contested must be true or false")
    if track_key and not isinstance(fm.get("claim_track"), bool):
        add("claim-track-not-bool", "claim_track must be true or false")

    contest_open = contested is True
    history_block = found.get("История", "")
    history = _history_lines(history_block)
    needs_history = contest_open or tracked
    if needs_history and not history:
        add("contest-dropped-history", "tracked or contested card has no dated ## История bullet")

    if contest_open:
        reasons = list(CONTEST_LINE_RE.finditer(found.get("Оспаривание", "")))
        if not reasons:
            add(
                "contested-without-reason",
                "need ## Оспаривание bullet: YYYY-MM-DD — подтверждено|оспорено|уточнить — причина: …",
            )

    if contest_open and not any(_records_dispute(line) for _, line in history):
        add(
            "contest-without-history-line",
            "contested card must keep a ## История line that records оспорено, уточнить, подтверждено, or оспаривание",
        )

    updated = str(fm.get("updated") or "")
    if tracked:
        dated = [day for day, _line in history]
        if not DATE_RE.match(updated) or updated not in dated:
            add(
                "claim-updated-without-history",
                f"claim_track card updated {updated or 'missing'} has no ## История bullet on that date",
            )
        pinned = fm.get("claim_digest")
        if isinstance(pinned, str) and pinned.strip():
            current = claim_digest(significant_claim_text(body))
            if current != pinned.strip():
                waived = any(day == updated and _records_change(line) for day, line in history)
                if not waived:
                    add(
                        "claim-digest-without-history",
                        "significant claim text does not match claim_digest and ## История has no было/→ line on updated",
                    )
    return findings


def iter_markdown(root: Path) -> list[Path]:
    return [path for path in root.rglob("*.md") if ".obsidian" not in path.parts]


def scan_path(path: Path, root: Path | None = None) -> list[dict]:
    base = root or path.parent
    try:
        rel = str(path.relative_to(base))
    except ValueError:
        rel = path.name
    text = path.read_text(encoding="utf-8-sig")
    return contest_findings(text, rel)


def scan_root(root: Path) -> list[dict]:
    findings: list[dict] = []
    for path in iter_markdown(root):
        findings.extend(scan_path(path, root))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Проверка маркера оспаривания. Смысл карточек не читает.")
    parser.add_argument("--root", type=Path, default=HARVEST, help="Корень markdown. По умолчанию harvest/")
    parser.add_argument("--file", type=Path, default=None, help="Один файл вместо дерева")
    parser.add_argument(
        "--digest",
        action="store_true",
        help="Напечатать claim_digest значимых секций одного --file и выйти 0",
    )
    args = parser.parse_args(argv)
    if args.digest:
        if args.file is None or not args.file.is_file():
            print("need --file", file=sys.stderr)
            return 2
        _fm, body = parse_fm(args.file.read_text(encoding="utf-8-sig"))
        print(claim_digest(significant_claim_text(body)))
        return 0
    if args.file is not None:
        if not args.file.is_file():
            print(f"missing file: {args.file}", file=sys.stderr)
            return 2
        findings = scan_path(args.file, args.file.parent)
    else:
        if not args.root.is_dir():
            print(f"missing root: {args.root}", file=sys.stderr)
            return 2
        findings = scan_root(args.root)
    codes: dict[str, int] = {}
    for item in findings:
        codes[item["code"]] = codes.get(item["code"], 0) + 1
    payload = {"ok": not findings, "total": len(findings), "counts": codes, "findings": findings}
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
