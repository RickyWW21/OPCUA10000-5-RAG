"""Filesystem error contracts for optional artifacts and graph exports."""

from __future__ import annotations

import ast
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from opcua_kb import KnowledgeBase
from opcua_kb.builder import (
    _build_fts,
    _connect_fts,
    _create_fts_schema,
    _make_directory,
    _read_source_text,
    _write_jsonl,
    build,
)
from opcua_kb.errors import format_action_error
from opcua_kb.graph import write_graph_html, write_graph_json
from tests.helpers import write_knowledge_base


def _tui_handler_error_boundaries() -> dict[str, ast.Try]:
    """Return the narrow KB error boundary for each affected TUI handler."""

    path = Path(__file__).resolve().parents[1] / "tools" / "tui.py"
    module = ast.parse(path.read_text(encoding="utf-8"))
    app = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "KnowledgeBaseTUI")
    boundaries: dict[str, ast.Try] = {}
    for method in app.body:
        if not isinstance(method, ast.FunctionDef) or method.name not in {
            "_search",
            "_show_entity",
            "_show_relations",
            "_show_chapter",
            "_show_table",
        }:
            continue
        boundary = next((node for node in ast.walk(method) if isinstance(node, ast.Try)), None)
        if boundary is not None:
            boundaries[method.name] = boundary
    return boundaries


class ErrorBoundaryTests(unittest.TestCase):
    """Verify callers receive actionable errors without hiding root causes."""

    def test_tui_action_error_includes_action_and_original_error(self) -> None:
        self.assertEqual(
            "行动失败：搜索：indexes/fts.sqlite: read failed",
            format_action_error("搜索", OSError("indexes/fts.sqlite: read failed")),
        )

    def test_tui_handlers_limit_error_boundaries_to_knowledge_base_calls(self) -> None:
        boundaries = _tui_handler_error_boundaries()

        self.assertEqual(
            {"_search", "_show_entity", "_show_relations", "_show_chapter", "_show_table"},
            set(boundaries),
        )
        for handler, boundary in boundaries.items():
            with self.subTest(handler=handler):
                caught = {
                    exception.id
                    for clause in boundary.handlers
                    if isinstance(clause.type, ast.Tuple)
                    for exception in clause.type.elts
                    if isinstance(exception, ast.Name)
                }
                self.assertEqual({"OSError", "ValueError"}, caught)
                calls = [
                    node
                    for node in ast.walk(ast.Module(body=boundary.body, type_ignores=[]))
                    if isinstance(node, ast.Call)
                ]
                self.assertEqual(1, len(calls))
                self.assertIsInstance(calls[0].func, ast.Attribute)
                self.assertIsInstance(calls[0].func.value, ast.Attribute)
                self.assertIsInstance(calls[0].func.value.value, ast.Name)
                self.assertEqual("self", calls[0].func.value.value.id)
                self.assertEqual("kb", calls[0].func.value.attr)

    def test_invalid_aliases_json_identifies_artifact_and_preserves_decode_cause(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_knowledge_base(root)
            aliases = root / "kb" / "aliases.json"
            aliases.write_text("{not valid json}", encoding="utf-8")

            with self.assertRaises(ValueError) as raised:
                KnowledgeBase(root).get_entity("ServerType")

            self.assertIn(str(aliases), str(raised.exception))
            self.assertIsNotNone(raised.exception.__cause__)

    def test_invalid_aliases_utf8_identifies_artifact_and_preserves_decode_cause(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_knowledge_base(root)
            aliases = root / "kb" / "aliases.json"
            aliases.write_bytes(b"\xff")

            with self.assertRaises(ValueError) as raised:
                KnowledgeBase(root).get_entity("ServerType")

            self.assertIn(str(aliases), str(raised.exception))
            self.assertIsInstance(raised.exception.__cause__, UnicodeDecodeError)

    def test_aliases_json_array_is_rejected_as_an_invalid_artifact(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_knowledge_base(root)
            aliases = root / "kb" / "aliases.json"
            aliases.write_text("[]", encoding="utf-8")

            with self.assertRaises(ValueError) as raised:
                KnowledgeBase(root).get_entity("ServerType")

            self.assertIn(str(aliases), str(raised.exception))

    def test_aliases_json_requires_string_keys_and_values(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_knowledge_base(root)
            aliases = root / "kb" / "aliases.json"
            aliases.write_text('{"server": []}', encoding="utf-8")

            with self.assertRaises(ValueError) as raised:
                KnowledgeBase(root).get_entity("server")

            self.assertIn(str(aliases), str(raised.exception))

    def test_missing_aliases_json_remains_an_empty_optional_artifact(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_knowledge_base(root)
            (root / "kb" / "aliases.json").unlink()

            self.assertEqual({}, KnowledgeBase(root)._load_aliases())

    def test_aliases_directory_is_not_treated_as_a_missing_optional_artifact(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            write_knowledge_base(root)
            aliases = root / "kb" / "aliases.json"
            aliases.unlink()
            aliases.mkdir()

            with self.assertRaises(OSError) as raised:
                KnowledgeBase(root).get_entity("ServerType")

            self.assertIn(str(aliases), str(raised.exception))
            self.assertIn("read", str(raised.exception).lower())
            self.assertIsInstance(raised.exception.__cause__, OSError)
            self.assertIsNotNone(raised.exception.__cause__)

    def test_build_missing_source_identifies_read_operation_and_source_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "output"
            source = Path(temporary_directory) / "missing.md"

            with self.assertRaises(OSError) as raised:
                build(root, source)

            self.assertIn(str(source.resolve()), str(raised.exception))
            self.assertIn("source", str(raised.exception).lower())
            self.assertIn("read", str(raised.exception).lower())
            self.assertIsInstance(raised.exception.__cause__, OSError)

    def test_build_invalid_utf8_source_identifies_read_operation_and_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "output"
            source = Path(temporary_directory) / "source.md"
            source.write_bytes(b"\xff")

            with self.assertRaises(ValueError) as raised:
                build(root, source)

            self.assertIn(str(source.resolve()), str(raised.exception))
            self.assertIn("read source", str(raised.exception).lower())
            self.assertIsInstance(raised.exception.__cause__, UnicodeDecodeError)

    def test_build_directory_creation_identifies_operation_and_blocked_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            blocked_parent = root / "blocked"
            blocked_parent.write_text("not a directory", encoding="utf-8")
            destination = blocked_parent / "kb"

            with self.assertRaises(OSError) as raised:
                _make_directory(destination)

            self.assertIn(str(destination), str(raised.exception))
            self.assertIn("directory", str(raised.exception).lower())
            self.assertIsInstance(raised.exception.__cause__, OSError)

    def test_source_text_read_identifies_operation_and_directory_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "source.md"
            source.mkdir()

            with self.assertRaises(OSError) as raised:
                _read_source_text(source)

            self.assertIn(str(source), str(raised.exception))
            self.assertIn("source", str(raised.exception).lower())
            self.assertIn("read", str(raised.exception).lower())
            self.assertIsInstance(raised.exception.__cause__, OSError)

    def test_build_source_copy_identifies_source_and_destination_paths(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            root = temporary / "output"
            source = temporary / "source.md"
            source.write_text("1 Introduction\n", encoding="utf-8")
            target_source = root / "source" / source.name
            (target_source / source.name).mkdir(parents=True)

            with self.assertRaises(OSError) as raised:
                build(root, source, rebuild=True)

            self.assertIn(str(source), str(raised.exception))
            self.assertIn(str(target_source), str(raised.exception))
            self.assertIn("copy", str(raised.exception).lower())
            self.assertIsInstance(raised.exception.__cause__, OSError)

    def test_build_blocked_manifest_identifies_write_operation_and_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            root = temporary / "output"
            source = temporary / "source.md"
            source.write_text("1 Introduction\n", encoding="utf-8")
            manifest_path = root / "source" / "source_manifest.json"
            manifest_path.mkdir(parents=True)

            with self.assertRaises(OSError) as raised:
                build(root, source)

            self.assertIn(str(manifest_path), str(raised.exception))
            self.assertIn("write source manifest", str(raised.exception).lower())
            self.assertIsInstance(raised.exception.__cause__, OSError)

    def test_build_blocked_jsonl_identifies_write_operation_and_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            root = temporary / "output"
            source = temporary / "source.md"
            source.write_text("1 Introduction\n", encoding="utf-8")
            jsonl_path = root / "kb" / "chapters.jsonl"
            jsonl_path.mkdir(parents=True)

            with self.assertRaises(OSError) as raised:
                build(root, source)

            self.assertIn(str(jsonl_path), str(raised.exception))
            self.assertIn("jsonl", str(raised.exception).lower())
            self.assertIsInstance(raised.exception.__cause__, OSError)

    def test_build_blocked_alias_output_identifies_write_operation_and_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "output"
            source = Path(temporary_directory) / "source.md"
            source.write_text("1 Introduction\n", encoding="utf-8")
            alias_path = root / "kb" / "aliases.json"
            alias_path.parent.mkdir(parents=True)
            alias_path.mkdir()

            with self.assertRaises(OSError) as raised:
                build(root, source)

            self.assertIn(str(alias_path), str(raised.exception))
            self.assertIn("write", str(raised.exception).lower())
            self.assertIsInstance(raised.exception.__cause__, OSError)

    def test_build_blocked_fts_output_identifies_index_operation_and_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "output"
            source = Path(temporary_directory) / "source.md"
            source.write_text("1 Introduction\n", encoding="utf-8")
            index_path = root / "indexes" / "fts.sqlite"
            index_path.parent.mkdir(parents=True)
            index_path.mkdir()

            with self.assertRaises(OSError) as raised:
                build(root, source)

            self.assertIn(str(index_path), str(raised.exception))
            self.assertIn("fts", str(raised.exception).lower())
            self.assertIsInstance(raised.exception.__cause__, OSError)

    def test_fts_connection_failure_identifies_open_operation_and_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            index_path = Path(temporary_directory) / "fts.sqlite"
            index_path.mkdir()

            with self.assertRaises(OSError) as raised:
                _connect_fts(index_path)

            self.assertIn(str(index_path), str(raised.exception))
            self.assertIn("open fts", str(raised.exception).lower())
            self.assertIsInstance(raised.exception.__cause__, sqlite3.OperationalError)

    def test_fts_schema_setup_failure_identifies_setup_operation_and_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            index_path = Path(temporary_directory) / "fts.sqlite"
            connection = sqlite3.connect(":memory:")
            self.addCleanup(connection.close)
            connection.execute("CREATE TABLE search_fts (item_type TEXT)")

            with self.assertRaises(OSError) as raised:
                _create_fts_schema(connection, index_path)

            self.assertIn(str(index_path), str(raised.exception))
            self.assertIn("set up fts", str(raised.exception).lower())
            self.assertIsInstance(raised.exception.__cause__, sqlite3.OperationalError)

    def test_fts_insert_failure_identifies_write_operation_and_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            index_path = Path(temporary_directory) / "fts.sqlite"
            chunks = [
                {
                    "id": "chunk-invalid",
                    "heading_path": [],
                    "section": "",
                    "table_ids": [],
                    "text": object(),
                }
            ]

            with self.assertRaises(OSError) as raised:
                _build_fts(index_path, [], [], [], chunks)

            self.assertIn(str(index_path), str(raised.exception))
            self.assertIn("write fts", str(raised.exception).lower())
            self.assertIsInstance(raised.exception.__cause__, sqlite3.ProgrammingError)

    def test_jsonl_serialization_failure_propagates_without_persistence_wrapper(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            jsonl_path = Path(temporary_directory) / "records.jsonl"

            with self.assertRaises(TypeError) as raised:
                _write_jsonl(jsonl_path, [{"unsupported": object()}])

            self.assertIsNone(raised.exception.__cause__)

    def test_build_blocked_readme_identifies_write_operation_and_path(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            root = temporary / "output"
            source = temporary / "source.md"
            source.write_text("1 Introduction\n", encoding="utf-8")
            readme_path = root / "README.md"
            readme_path.mkdir(parents=True)

            with self.assertRaises(OSError) as raised:
                build(root, source)

            self.assertIn(str(readme_path), str(raised.exception))
            self.assertIn("write readme", str(raised.exception).lower())
            self.assertIsInstance(raised.exception.__cause__, OSError)

    def test_failed_rebuild_restores_previously_published_artifacts(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            root = temporary / "output"
            source = temporary / "source.md"
            source.write_text("1 Introduction\n", encoding="utf-8")
            build(root, source)
            entities = (root / "kb" / "entities.jsonl").read_bytes()
            fts = (root / "indexes" / "fts.sqlite").read_bytes()

            source.write_text("1 Rebuilt\n", encoding="utf-8")
            with patch("opcua_kb.builder._write_readme", side_effect=OSError("README failure")):
                with self.assertRaises(OSError):
                    build(root, source, rebuild=True)

            self.assertEqual(entities, (root / "kb" / "entities.jsonl").read_bytes())
            self.assertEqual(fts, (root / "indexes" / "fts.sqlite").read_bytes())
            self.assertEqual("Introduction", KnowledgeBase(root).chapter("1")["title"])

    def test_graph_json_mkdir_failure_identifies_destination_and_operation(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            blocked_parent = root / "blocked"
            blocked_parent.write_text("not a directory", encoding="utf-8")
            destination = blocked_parent / "graph.json"

            with self.assertRaises(OSError) as raised:
                write_graph_json({}, destination)

            self.assertIn(str(destination), str(raised.exception))
            self.assertIn("directory", str(raised.exception).lower())
            self.assertIsNotNone(raised.exception.__cause__)

    def test_graph_json_write_failure_identifies_destination_and_operation(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "graph.json"
            destination.mkdir()

            with self.assertRaises(OSError) as raised:
                write_graph_json({}, destination)

            self.assertIn(str(destination), str(raised.exception))
            self.assertIn("write", str(raised.exception).lower())
            self.assertIsNotNone(raised.exception.__cause__)

    def test_graph_html_mkdir_failure_identifies_destination_and_operation(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            blocked_parent = root / "blocked"
            blocked_parent.write_text("not a directory", encoding="utf-8")
            destination = blocked_parent / "graph.html"

            with self.assertRaises(OSError) as raised:
                write_graph_html({}, destination)

            self.assertIn(str(destination), str(raised.exception))
            self.assertIn("directory", str(raised.exception).lower())
            self.assertIsNotNone(raised.exception.__cause__)

    def test_graph_html_write_failure_identifies_destination_and_operation(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory) / "graph.html"
            destination.mkdir()

            with self.assertRaises(OSError) as raised:
                write_graph_html({}, destination)

            self.assertIn(str(destination), str(raised.exception))
            self.assertIn("write", str(raised.exception).lower())
            self.assertIsNotNone(raised.exception.__cause__)


class CliErrorBoundaryTests(unittest.TestCase):
    """Verify CLI commands turn expected artifact failures into concise errors."""

    def test_commands_report_missing_artifacts_without_tracebacks(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            commands = {
                "query_kb.py": ["anything"],
                "inspect_entity.py": ["ServerType"],
                "trace_entity.py": ["ServerType"],
                "graph_kb.py": ["--format", "json"],
                "demo_graph.py": [],
            }

            for script, arguments in commands.items():
                with self.subTest(script=script):
                    root = Path(temporary_directory) / script
                    write_knowledge_base(root)
                    artifact = root / "kb" / (
                        "relationships.jsonl" if script in {"graph_kb.py", "demo_graph.py"} else "aliases.json"
                    )
                    artifact.unlink()
                    artifact.mkdir()
                    result = self._run(script, *arguments, "--root", str(root))

                    self.assertEqual(1, result.returncode)
                    self.assertIn("错误:", result.stderr)
                    self.assertNotIn("Traceback", result.stderr)

    def test_build_reports_missing_source_without_traceback(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "output"
            missing_source = Path(temporary_directory) / "missing.md"

            result = self._run("build_kb.py", "--root", str(root), "--source", str(missing_source))

            self.assertEqual(1, result.returncode)
            self.assertIn("错误:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_builder_direct_script_reports_missing_source_without_traceback(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "output"
            missing_source = Path(temporary_directory) / "missing.md"

            result = self._run_builder_script("--root", str(root), "--source", str(missing_source))

            self.assertEqual(1, result.returncode)
            self.assertIn("\u9519\u8bef:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_builder_module_reports_missing_source_without_traceback(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "output"
            missing_source = Path(temporary_directory) / "missing.md"

            result = self._run_module("opcua_kb.builder", "--root", str(root), "--source", str(missing_source))

            self.assertEqual(1, result.returncode)
            self.assertIn("\u9519\u8bef:", result.stderr)
            self.assertNotIn("Traceback", result.stderr)

    def test_builder_module_reports_invalid_utf8_source_without_traceback(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "output"
            source = Path(temporary_directory) / "source.md"
            source.write_bytes(b"\xff")

            result = self._run_module("opcua_kb.builder", "--root", str(root), "--source", str(source))

            self.assertEqual(1, result.returncode)
            self.assertIn(str(source.resolve()), result.stderr)
            self.assertIn("read source", result.stderr.lower())
            self.assertNotIn("Traceback", result.stderr)

    def test_build_uses_the_required_utf8_error_prefix(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "output"
            missing_source = Path(temporary_directory) / "missing.md"

            result = self._run("build_kb.py", "--root", str(root), "--source", str(missing_source))

            self.assertEqual(1, result.returncode)
            self.assertIn("\u9519\u8bef:", result.stderr)

    def test_builder_parser_factory_defines_tool_options_and_defaults(self) -> None:
        from opcua_kb.builder import create_parser

        arguments = create_parser().parse_args([])

        self.assertEqual(r"C:\Users\admin\Downloads\OPC-10000-5-v1.05.06.md", arguments.source)
        self.assertEqual(".", arguments.root)
        self.assertFalse(arguments.rebuild)

    def test_commands_preserve_normal_output_paths(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            temporary = Path(temporary_directory)
            root = temporary / "knowledge-base"
            write_knowledge_base(root)

            commands = {
                "query_kb.py": (["ServerType", "--root", str(root)], "ServerType"),
                "inspect_entity.py": (["ServerType", "--root", str(root)], "ServerType"),
                "trace_entity.py": (["ServerType", "--root", str(root)], "HAS_COMPONENT"),
                "graph_kb.py": (["--format", "json", "--root", str(root)], "Graph written:"),
                "demo_graph.py": (["--root", str(root)], "Knowledge Graph Demo"),
            }

            for script, (arguments, expected_output) in commands.items():
                with self.subTest(script=script):
                    result = self._run(script, *arguments)

                    self.assertEqual(0, result.returncode, result.stderr)
                    self.assertIn(expected_output, result.stdout)
                    self.assertEqual("", result.stderr)

            source = temporary / "source.md"
            source.write_text("1 Introduction\n", encoding="utf-8")
            build_root = temporary / "built"
            result = self._run("build_kb.py", "--root", str(build_root), "--source", str(source))

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn('"chapters"', result.stdout)
            self.assertTrue((build_root / "kb" / "entities.jsonl").exists())

    def test_trace_preserves_no_relationships_message(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "knowledge-base"
            write_knowledge_base(root)

            result = self._run("trace_entity.py", "UnknownType", "--root", str(root))

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn("\u672a\u627e\u5230\u5173\u7cfb\u3002", result.stdout)
            self.assertEqual("", result.stderr)

    def test_cli_help_remains_argparse_success(self) -> None:
        for script in ("query_kb.py", "inspect_entity.py", "trace_entity.py", "graph_kb.py", "demo_graph.py", "build_kb.py"):
            with self.subTest(script=script):
                result = self._run(script, "--help")

                self.assertEqual(0, result.returncode)
                self.assertIn("usage:", result.stdout.lower())
                self.assertEqual("", result.stderr)

    @staticmethod
    def _run(script: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        project_root = Path(__file__).resolve().parents[1]
        return subprocess.run(
            [sys.executable, str(project_root / "tools" / script), *arguments],
            cwd=project_root,
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def _run_module(module: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        project_root = Path(__file__).resolve().parents[1]
        return subprocess.run(
            [sys.executable, "-m", module, *arguments],
            cwd=project_root,
            text=True,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def _run_builder_script(*arguments: str) -> subprocess.CompletedProcess[str]:
        project_root = Path(__file__).resolve().parents[1]
        return subprocess.run(
            [sys.executable, str(project_root / "opcua_kb" / "builder.py"), *arguments],
            cwd=project_root,
            text=True,
            capture_output=True,
            check=False,
        )
