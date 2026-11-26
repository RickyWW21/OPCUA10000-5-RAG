"""Contract tests for the LLM Wiki checker.

The fixture deliberately uses a stale absolute ``local_source_path`` in the
manifest.  The checker must locate the source by its file name below
``<root>/source`` so a moved checkout keeps working.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKER = PROJECT_ROOT / "tools" / "check_wiki.py"
SOURCE_NAME = "OPC-TEST-v1.05.06.md"
SOURCE_REL = f"../../source/{SOURCE_NAME}"


def _reference(section: str, start: int, end: int, table: str | None = None) -> str:
    """Render the single citation format understood by the checker."""

    label = f"§{section}"
    if table is not None:
        label += f" Table {table}"
    label += f" L{start}-L{end}"
    return f"[{label}]({SOURCE_REL}#L{start}-L{end})"


def _frontmatter(
    page_id: str,
    kind: str,
    sha256: str,
    sources: list[dict[str, str]],
    entity_id: str | None = None,
) -> str:
    rows = [
        "---",
        f"page_id: {page_id}",
        f"kind: {kind}",
    ]
    if entity_id is not None:
        rows.append(f"entity_id: {entity_id}")
    rows.extend(
        [
            "source_doc: OPC-10000-5",
            "source_version: 1.05.06",
            f"source_sha256: {sha256}",
            "status: draft",
            "updated: 2026-11-18",
            f"sources: {json.dumps(sources, ensure_ascii=False)}",
            "---",
            "",
        ]
    )
    return "\n".join(rows)


class WikiFixture:
    """Build a complete, small wiki that must pass all structural checks."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.page_paths: dict[str, Path] = {}
        self.digest = ""

    def build(self) -> None:
        source_dir = self.root / "source"
        source_dir.mkdir(parents=True)
        source_lines = [
            "OPC-10000-5 fixture source line 1",
            "Version: 1.05.06 fixture source line 2",
        ]
        source_lines.extend(
            f"fixture source line {number}" for number in range(3, 231)
        )
        source_text = "\n".join(source_lines) + "\n"
        source_path = source_dir / SOURCE_NAME
        source_path.write_text(source_text, encoding="utf-8")
        self.digest = hashlib.sha256(source_path.read_bytes()).hexdigest()

        manifest = {
            "doc": "OPC-10000-5",
            "title": "Fixture Part 5",
            "version": "1.05.06",
            "local_source_path": "C:\\stale\\checkout\\source\\" + SOURCE_NAME,
            "sha256": self.digest,
        }
        (source_dir / "source_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )

        self._write_jsonl(
            "kb/chapters.jsonl",
            [
                {"id": "sec-6.1", "section": "6.1", "start_line": 1, "end_line": 4},
                {"id": "sec-6.2", "section": "6.2", "start_line": 5, "end_line": 20},
                {"id": "sec-6.3.1", "section": "6.3.1", "start_line": 21, "end_line": 50},
            ],
        )
        self._write_jsonl(
            "kb/tables.jsonl",
            [
                {"id": "table-8", "number": "8", "section": "6.2", "start_line": 10, "end_line": 15},
                {"id": "table-9", "number": "9", "section": "6.3.1", "start_line": 25, "end_line": 40},
            ],
        )
        self._write_jsonl(
            "kb/entities.jsonl",
            [
                {
                    "id": "ObjectType:BaseObjectType",
                    "name": "BaseObjectType",
                    "kind": "ObjectType",
                    "section": "6.2",
                    "related_tables": ["table-8"],
                },
                {
                    "id": "ObjectType:ServerType",
                    "name": "ServerType",
                    "kind": "ObjectType",
                    "section": "6.3.1",
                    "related_tables": ["table-9"],
                },
            ],
        )

        self._write_page(
            "entities/baseobjecttype.md",
            _frontmatter(
                "baseobjecttype",
                "entity",
                self.digest,
                [
                    {"section": "6.2", "table": "8", "lines": "10-15"},
                    {"section": "6.1", "lines": "1-4"},
                ],
                entity_id="ObjectType:BaseObjectType",
            )
            + "# BaseObjectType\n\nFixture entity page.\n\n"
            + _reference("6.2", 10, 15, "8")
            + "\n\n"
            + _reference("6.1", 1, 4)
            + "\n\n## Links\n\n- [Index](../index.md)\n- [ServerType](servertype.md)\n",
        )
        self._write_page(
            "entities/servertype.md",
            _frontmatter(
                "servertype",
                "entity",
                self.digest,
                [
                    {"section": "6.3.1", "table": "9", "lines": "25-40"},
                    {"section": "6.3.1", "lines": "45-48"},
                ],
                entity_id="ObjectType:ServerType",
            )
            + "# ServerType\n\nFixture entity page.\n\n"
            + _reference("6.3.1", 25, 40, "9")
            + "\n\n"
            + _reference("6.3.1", 45, 48)
            + "\n\n## Links\n\n- [Index](../index.md)\n- [BaseObjectType](baseobjecttype.md)\n",
        )

        topic_sources = [
            ("6.1", 1, 4),
            ("6.2", 16, 20),
            ("6.3.1", 41, 44),
        ]
        for number in range(1, 9):
            section, start, end = topic_sources[(number - 1) % len(topic_sources)]
            page_id = f"topic-{number}"
            other = f"topic-{number + 1}" if number < 8 else "baseobjecttype"
            other_path = f"{other}.md" if number < 8 else f"../entities/{other}.md"
            body = (
                f"# Topic {number}\n\nFixture topic page.\n\n"
                + _reference(section, start, end)
                + f"\n\n## Links\n\n- [Index](../index.md)\n- [Other]({other_path})\n"
            )
            self._write_page(
                f"topics/{page_id}.md",
                _frontmatter(
                    page_id,
                    "topic",
                    self.digest,
                    [{"section": section, "lines": f"{start}-{end}"}],
                )
                + body,
            )

        links = "\n".join(
            f"- [{path.stem}]({path.relative_to(self.root / 'wiki').as_posix()})"
            for path in sorted(self.page_paths.values())
        )
        (self.root / "wiki" / "index.md").write_text(
            "# Fixture Wiki Index\n\n" + links + "\n", encoding="utf-8"
        )
        (self.root / "wiki" / "log.md").write_text("# Log\n\nFixture.\n", encoding="utf-8")
        (self.root / "wiki" / "AGENTS.md").write_text("# Agents\n\nFixture.\n", encoding="utf-8")

    def _write_jsonl(self, relative: str, records: list[dict[str, object]]) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
            encoding="utf-8",
        )

    def _write_page(self, relative: str, text: str) -> None:
        path = self.root / "wiki" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        self.page_paths[relative] = path


class WikiCheckerTests(unittest.TestCase):
    """Verify the checker accepts the contract and rejects broken wikis."""

    def setUp(self) -> None:
        self._temporary = tempfile.TemporaryDirectory()
        self.root = Path(self._temporary.name)
        self.fixture = WikiFixture(self.root)
        self.fixture.build()

    def tearDown(self) -> None:
        self._temporary.cleanup()

    def _run(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(self.root)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

    def _assert_rejected(self, proc: subprocess.CompletedProcess[str], needle: str) -> None:
        self.assertNotEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn(needle.lower(), (proc.stdout + proc.stderr).lower())

    def _mutate(self, relative: str, replacements: list[tuple[str, str]]) -> None:
        path = self.root / "wiki" / relative
        text = path.read_text(encoding="utf-8")
        for old, new in replacements:
            self.assertIn(old, text)
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")

    def test_valid_fixture_passes(self) -> None:
        proc = self._run()

        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("ok (10 content pages", proc.stdout.lower())
        self.assertIn("no semantic review", proc.stdout.lower())

    def test_missing_internal_link_is_rejected(self) -> None:
        page = self.root / "wiki" / "topics" / "topic-1.md"
        page.write_text(
            page.read_text(encoding="utf-8") + "\n[Broken](does-not-exist.md)\n",
            encoding="utf-8",
        )

        self._assert_rejected(self._run(), "does not exist")

    def test_stale_frontmatter_hash_is_rejected(self) -> None:
        self._mutate(
            "entities/baseobjecttype.md",
            [(self.fixture.digest, "0" * 64)],
        )

        self._assert_rejected(self._run(), "sha256")

    def test_unknown_section_is_rejected(self) -> None:
        self._mutate(
            "topics/topic-1.md",
            [
                ('"section": "6.1"', '"section": "9.9"'),
                ("[§6.1 L1-L4]", "[§9.9 L1-L4]"),
            ],
        )

        self._assert_rejected(self._run(), "unknown section")

    def test_unknown_table_is_rejected(self) -> None:
        self._mutate(
            "entities/servertype.md",
            [
                ('"table": "9"', '"table": "999"'),
                ("[§6.3.1 Table 9 L25-L40]", "[§6.3.1 Table 999 L25-L40]"),
            ],
        )

        self._assert_rejected(self._run(), "unknown table")

    def test_out_of_range_line_anchor_is_rejected(self) -> None:
        self._mutate(
            "topics/topic-2.md",
            [
                ('"lines": "16-20"', '"lines": "900-901"'),
                ("[§6.2 L16-L20](../../source/OPC-TEST-v1.05.06.md#L16-L20)",
                 "[§6.2 L900-L901](../../source/OPC-TEST-v1.05.06.md#L900-L901)"),
            ],
        )

        self._assert_rejected(self._run(), "beyond")

    def test_duplicate_page_id_is_rejected(self) -> None:
        self._mutate("topics/topic-1.md", [("page_id: topic-1", "page_id: topic-2")])

        self._assert_rejected(self._run(), "duplicate page_id")

    def test_link_escaping_project_root_is_rejected(self) -> None:
        page = self.root / "wiki" / "topics" / "topic-3.md"
        page.write_text(
            page.read_text(encoding="utf-8") + "\n[Escape](../../../../outside.md)\n",
            encoding="utf-8",
        )

        self._assert_rejected(self._run(), "outside")


if __name__ == "__main__":
    unittest.main()
