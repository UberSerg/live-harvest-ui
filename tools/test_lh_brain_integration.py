"""Приёмка lh_ingest, пакет исследования и манифест снимка. Только синтетические фикстуры."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.kb_validate import SKIP_DIR_NAMES
from tools.lh_ingest import body_checksum, split_frontmatter
from tools.lh_research_packet import EXPECTED_EXPORT
from tools.lh_ui_snapshot import (
    DEFAULT_RENDERED_SOURCES,
    builtin_manifest,
    coverage_report,
    load_source_manifest,
)

FIXTURES = ROOT / "tools" / "fixtures" / "lh_ingest"
RESEARCH = ROOT / "tools" / "fixtures" / "lh_research"
INGEST = ROOT / "tools" / "lh_ingest.py"
PACKET = ROOT / "tools" / "lh_research_packet.py"
SNAPSHOT = ROOT / "tools" / "lh_ui_snapshot.py"
SPEC = ROOT / "harvest" / "Мозг" / "_system" / "External Research Protocol.md"


def run(script: Path, args: list[str]) -> tuple[int, str, str]:
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def codes(payload: dict) -> set[str]:
    return {item["code"] for item in payload.get("errors") or []}


class IngestTests(unittest.TestCase):
    def test_spec_embeds_fixtures(self):
        spec = SPEC.read_text(encoding="utf-8")
        example = (FIXTURES / "hypothesis_research_ok.md").read_text(encoding="utf-8").strip()
        template = (FIXTURES / "hypothesis_research.template.md").read_text(encoding="utf-8").strip()
        self.assertIn(example, spec)
        self.assertIn(template, spec)
        self.assertEqual(template + "\n", EXPECTED_EXPORT if EXPECTED_EXPORT.endswith("\n") else EXPECTED_EXPORT + "\n")

    def test_validate_example_and_legacy_interview(self):
        code, out, err = run(INGEST, ["validate", str(FIXTURES / "hypothesis_research_ok.md"), "--no-default-scan"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["duplicate"])
        self.assertEqual(payload["type"], "hypothesis_research")
        self.assertEqual(payload["wrote"], [])

        code, out, err = run(INGEST, ["validate", str(FIXTURES / "interview_v1_ok.md"), "--no-default-scan"])
        self.assertEqual(code, 0, err)
        self.assertTrue(json.loads(out)["ok"])

        code, out, err = run(INGEST, ["validate", str(FIXTURES / "hypothesis_research.template.md"), "--no-default-scan"])
        self.assertEqual(code, 0, err)

    def test_reject_version_reserved_core_and_secret(self):
        code, out, _err = run(INGEST, ["validate", str(FIXTURES / "bad_version.md"), "--no-default-scan"])
        self.assertEqual(code, 1)
        self.assertIn("bad_version", codes(json.loads(out)))

        code, out, _err = run(INGEST, ["validate", str(FIXTURES / "capital_semantic_reserved.md"), "--no-default-scan"])
        self.assertEqual(code, 1)
        self.assertIn("reserved_not_implemented", codes(json.loads(out)))

        with tempfile.TemporaryDirectory() as tmp:
            code, out, _err = run(
                INGEST,
                ["import", str(FIXTURES / "core_instruction.md"), "--no-default-scan", "--inbox", tmp],
            )
            self.assertEqual(code, 2)
            payload = json.loads(out)
            self.assertIn("core_instruction", codes(payload))
            self.assertEqual(payload["wrote"], [])
            self.assertNotIn("hunter2", out)
            self.assertFalse(any((Path(tmp) / "pending").glob("*.md")))

        code, out, _err = run(INGEST, ["validate", str(FIXTURES / "secret_material.md"), "--no-default-scan"])
        self.assertEqual(code, 2)
        self.assertIn("secret_material", codes(json.loads(out)))
        self.assertNotIn("hunter2-example", out)

    def test_import_apply_is_proposal_only_and_duplicate_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox"
            sentinel = Path(tmp) / "Личность" / "НеТрогать.md"
            sentinel.parent.mkdir(parents=True)
            sentinel.write_text("ORIGINAL", encoding="utf-8")
            package = FIXTURES / "hypothesis_research_ok.md"
            code, out, err = run(
                INGEST,
                ["import", str(package), "--apply", "--inbox", str(inbox), "--no-default-scan"],
            )
            self.assertEqual(code, 0, err)
            payload = json.loads(out)
            self.assertFalse(payload["auto_applied"])
            self.assertTrue(payload["proposal"])
            pending = list((inbox / "pending").glob("*.md"))
            pending = [path for path in pending if path.name.lower() != "readme.md"]
            self.assertEqual(len(pending), 1)
            filed = pending[0].read_text(encoding="utf-8")
            self.assertIn("status: pending", filed)
            self.assertIn("ingest_status: pending_ingest", filed)
            self.assertIn("auto_applied: false", filed)
            proposal = (inbox / "proposals").glob("proposal-*.md")
            proposal_text = next(proposal).read_text(encoding="utf-8")
            self.assertIn("auto_applied: false", proposal_text)
            self.assertIn("не изменены", proposal_text)
            self.assertEqual(sentinel.read_text(encoding="utf-8"), "ORIGINAL")
            written = {path.resolve() for path in inbox.rglob("*") if path.is_file()}
            self.assertTrue(all(inbox.resolve() in path.parents for path in written))

            code, out, err = run(
                INGEST,
                ["import", str(package), "--apply", "--inbox", str(inbox), "--no-default-scan"],
            )
            self.assertEqual(code, 3, err)
            again = json.loads(out)
            self.assertTrue(again["duplicate"])
            self.assertEqual(again["wrote"], [])
            self.assertEqual(len(list((inbox / "proposals").glob("proposal-*.md"))), 1)

            code, out, _err = run(
                INGEST,
                ["validate", str(package), "--inbox", str(inbox), "--no-default-scan"],
            )
            self.assertEqual(code, 3)
            self.assertTrue(json.loads(out)["duplicate"])

    def test_absorbed_and_checksum(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, _err = run(
                INGEST,
                ["import", str(FIXTURES / "interview_absorbed.md"), "--no-default-scan", "--inbox", tmp],
            )
            self.assertEqual(code, 3)
            self.assertIn("already_absorbed", codes(json.loads(out)))
            self.assertFalse(any((Path(tmp) / "pending").glob("*.md")))

        text = (FIXTURES / "interview_v1_ok.md").read_text(encoding="utf-8")
        _fm, body, err = split_frontmatter(text)
        self.assertIsNone(err)
        digest = body_checksum(body)
        stamped = text.replace("status: pending_ingest", f"status: pending_ingest\nchecksum: {digest}", 1)
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / "stamped.md"
            package.write_text(stamped, encoding="utf-8")
            code, out, err = run(INGEST, ["validate", str(package), "--no-default-scan"])
            self.assertEqual(code, 0, err)
            broken = stamped.replace(digest, "ab" * 32)
            package.write_text(broken, encoding="utf-8")
            code, out, _err = run(INGEST, ["validate", str(package), "--no-default-scan"])
            self.assertEqual(code, 1)
            self.assertIn("checksum_mismatch", codes(json.loads(out)))


class PacketTests(unittest.TestCase):
    def test_packet_privacy_preview(self):
        code, out, err = run(PACKET, ["--json", str(RESEARCH / "hypothesis_card.md")])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertIn("короткий утренний блок", payload["research_goal"])
        self.assertTrue(payload["known"])
        self.assertTrue(payload["unknown"])
        self.assertIn("lh_ingest_version: 1", payload["expected_export_format"])
        self.assertIn("type: hypothesis_research", payload["expected_export_format"])
        self.assertTrue(payload["ready_prompt"])
        self.assertIn("source: hypothesis_card.md", payload["minimal_context"])
        self.assertTrue(any(item.startswith("link: ") for item in payload["minimal_context"]))
        secrets = [item for item in payload["privacy_preview"] if item["field"] == "section:Секреты"]
        self.assertTrue(secrets and secrets[0]["included"] is False)
        self.assertNotIn("hunter2", out)
        self.assertNotIn("[[", payload["ready_prompt"])

        code, out, _err = run(PACKET, ["--json", str(RESEARCH / "hypothesis_sensitive.md")])
        self.assertEqual(code, 0)
        sensitive = json.loads(out)
        self.assertFalse(sensitive["known"])
        self.assertNotIn("слишком подробный", out)
        self.assertIn("формулировки", sensitive["research_goal"])

        code, out, _err = run(PACKET, ["--json", str(RESEARCH / "hypothesis_secret.md")])
        self.assertEqual(code, 2)
        blocked = json.loads(out)
        self.assertFalse(blocked["ok"])
        self.assertNotIn("нельзя выносить", out)

    def test_packet_write_is_opt_in(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = run(PACKET, [str(RESEARCH / "hypothesis_card.md"), "--out", tmp])
            self.assertEqual(code, 0, err)
            written = list(Path(tmp).glob("*.md"))
            self.assertEqual(len(written), 1)
            text = written[0].read_text(encoding="utf-8")
            self.assertIn("status: актуально", text)
            self.assertIn("## Research goal", text)
            self.assertIn("## Privacy preview", text)
            self.assertNotIn("hunter2", text)


class SnapshotManifestTests(unittest.TestCase):
    def test_manifest_matches_builder_and_reports_gaps(self):
        self.assertIn("_inbox", SKIP_DIR_NAMES)
        manifest = load_source_manifest()
        rendered = [item["path"] for item in manifest["rendered"]]
        self.assertEqual(rendered, DEFAULT_RENDERED_SOURCES)
        self.assertEqual(manifest["mode"], "file")
        unread = {
            "Цели/Аренда в Москве — переезд с дочерью.md",
            "Личность/Волны вдохновения и фокус.md",
            "Финансы/Кеш — текущий.md",
        }
        self.assertTrue(unread.isdisjoint(DEFAULT_RENDERED_SOURCES))
        report = coverage_report(manifest, ROOT / "harvest")
        self.assertEqual(report["contract"], "snapshot-sources/1")
        self.assertEqual(report["builder_paths"], DEFAULT_RENDERED_SOURCES)
        missing_declared = {item["path"] for item in report["not_in_snapshot"]}
        self.assertIn("Финансы/Капитал/", missing_declared)
        self.assertIn("Мозг/_system/External Research Protocol.md", missing_declared)
        self.assertTrue(unread <= missing_declared)

        builtin = builtin_manifest()
        self.assertEqual(builtin["mode"], "builtin")
        with self.assertRaises(FileNotFoundError):
            load_source_manifest(ROOT / "tools" / "fixtures" / "no-such-manifest.yaml")

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Личность").mkdir()
            (root / "Личность" / "Сергей.md").write_text("synthetic", encoding="utf-8")
            custom = {
                "mode": "file",
                "path": None,
                "rendered": [
                    {"path": "Личность/Сергей.md", "slot": "", "reason": ""},
                    {"path": "Личность/Нет такой.md", "slot": "", "reason": ""},
                    {"path": "Заметки/Вне сборщика.md", "slot": "", "reason": ""},
                ],
                "extra_unrendered": [],
                "excluded": [],
            }
            coverage = coverage_report(custom, root)
            self.assertEqual(coverage["rendered_present"], ["Личность/Сергей.md"])
            self.assertEqual(coverage["rendered_missing"], ["Личность/Нет такой.md", "Заметки/Вне сборщика.md"])
            outside = [item["path"] for item in coverage["not_in_snapshot"]]
            self.assertEqual(outside, ["Личность/Нет такой.md", "Заметки/Вне сборщика.md"])

    def test_coverage_cli_does_not_write_snapshot(self):
        snapshot = ROOT / "harvest-ui" / "snapshot.json"
        data_js = ROOT / "harvest-ui" / "data.js"
        before = (
            snapshot.stat().st_mtime_ns if snapshot.exists() else None,
            data_js.stat().st_mtime_ns if data_js.exists() else None,
        )
        code, out, err = run(SNAPSHOT, ["--coverage"])
        self.assertEqual(code, 0, err)
        payload = json.loads(out)
        self.assertEqual(payload["mode"], "file")
        self.assertEqual(payload["builder_paths"], DEFAULT_RENDERED_SOURCES)
        after = (
            snapshot.stat().st_mtime_ns if snapshot.exists() else None,
            data_js.stat().st_mtime_ns if data_js.exists() else None,
        )
        self.assertEqual(before, after)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
