"""Проверка контракта lh_retrieve: пути и причины, без тел карточек."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "lh_retrieve.py"


def run(args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def main() -> int:
    code, out, err = run(["--query", "INTEGRATION-INVENTORY", "--limit", "5"])
    assert code == 0, err
    hidden = json.loads(out)
    assert hidden["count"] == 0, hidden

    code, out, err = run(
        ["--query", "INTEGRATION-INVENTORY", "--include-system", "--limit", "5"]
    )
    assert code == 0, err
    shown = json.loads(out)
    assert shown["count"] >= 1
    assert any(hit["path"].endswith("INTEGRATION-INVENTORY.md") for hit in shown["hits"])
    assert all("body" not in hit and "text" not in hit for hit in shown["hits"])
    assert all(hit.get("reason") and hit.get("detail") for hit in shown["hits"])
    assert all("\n" not in hit["detail"] for hit in shown["hits"])

    code, out, err = run(["--preflight", "Live Harvest"])
    assert code == 2, (code, err, out)
    exists = json.loads(out)
    assert exists["exists"] is True
    assert any(item["reason"] == "exact-stem" for item in exists["matches"])
    assert all(item.get("detail") for item in exists["matches"])

    code, out, err = run(["--preflight", "no-such-brain-evo-stem-xyz"])
    assert code == 0, err
    missing = json.loads(out)
    assert missing["exists"] is False

    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
