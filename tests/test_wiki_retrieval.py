import json
import shutil
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import Mock

from opcua_kb.api import KnowledgeBase
from opcua_kb.retrieval import Part5Retriever, RetrievedRecord
from opcua_kb.rag import RAGPipeline
from opcua_kb.wiki import search_wiki

SOURCE_NAME = "OPC-10000-5-v1.05.06.md"
SOURCE_LINES = [
    "OPC 10000-5 Information Model",
    "Version: 1.05.06",
    "",
    "6.3.1 ServerType",
    "ServerType defines the Server Object.",
    "Table 9 - ServerType definition",
    "BrowseName,ServerType",
    "ServerArray,String[],Mandatory",
    "NamespaceArray,String[],Mandatory",
    "ServerType also carries 服务器诊断 information.",
    "6.3.2 Other",
    "Server diagnostics 服务器诊断 text.",
]
SPEC_RESULTS = [
    {"type": "chunk", "id": "chunk-1", "title": "Scope", "snippet": "spec one"},
    {"type": "chunk", "id": "chunk-2", "title": "ServerType", "snippet": "spec two"},
    {"type": "chunk", "id": "chunk-3", "title": "Diagnostics", "snippet": "spec three"},
]


class WikiRetrievalTests(unittest.TestCase):
    def test_chinese_namespace_query_finds_english_wiki_identifier(self):
        root = self._root()
        self._add_page(
            root, "wiki/entities/servertype.md", "servertype",
            body="# NamespaceArray\n\nNamespaceArray belongs to ServerType.\n",
        )
        hits = search_wiki(self._kb(root, []), "缓存命名空间索引如何检查？", top_k=1)
        self.assertEqual(["wiki:servertype"], [hit["id"] for hit in hits])

    def test_wiki_expands_relevant_second_source_even_when_spec_hits_exist(self):
        root = self._root()
        sources = [
            {"section": "6.3.1", "table": "9", "lines": "7-9"},
            {"section": "6.3.1", "lines": "12-12"},
        ]
        body = (
            "# 服务器诊断\n\n"
            "ServerType standard members.\n\n"
            "服务器诊断信息对应此处的规范规则。"
            f"[原文](../../source/{SOURCE_NAME}#L12-L12)\n"
        )
        for name in ("diagnostics", "diagnostics-other"):
            self._add_page(root, f"wiki/topics/{name}.md", name, kind="topic",
                           sources=sources, body=body)
        result = RAGPipeline(
            retriever=Part5Retriever(self._kb(root, SPEC_RESULTS))
        ).ask("服务器诊断", top_k=6)
        matches = [item for item in result.retrieved if item["id"] == "source:6.3.1:12-12"]
        self.assertEqual(1, len(matches), "shared original sources must be deduplicated")
        self.assertEqual(SOURCE_LINES[11], matches[0]["snippet"])
        self.assertEqual("12-12", matches[0]["provenance"]["lines"])
        self.assertEqual("1.05.06", matches[0]["provenance"]["version"])

    def _root(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="wiki-rag-"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        source = root / "source"
        source.mkdir()
        source_text = "\n".join(SOURCE_LINES) + "\n"
        source_path = source / SOURCE_NAME
        source_path.write_text(source_text, encoding="utf-8")
        # Hash the bytes actually written; text-mode writes use CRLF on Windows.
        digest = sha256(source_path.read_bytes()).hexdigest()
        (source / "source_manifest.json").write_text(
            json.dumps(
                {
                    "doc": "OPC-10000-5",
                    "version": "1.05.06",
                    "sha256": digest,
                    "local_source_path": f"C:\\old-machine\\{SOURCE_NAME}",
                }
            ),
            encoding="utf-8",
        )
        kb_dir = root / "kb"
        kb_dir.mkdir()
        (kb_dir / "chapters.jsonl").write_text(
            json.dumps(
                {
                    "id": "sec-6.3.1",
                    "section": "6.3.1",
                    "title": "ServerType",
                    "start_line": 1,
                    "end_line": 12,
                    "text": "\n".join(SOURCE_LINES),
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (kb_dir / "tables.jsonl").write_text(
            json.dumps(
                {
                    "id": "table-9",
                    "number": "9",
                    "section": "6.3.1",
                    "caption": "ServerType definition",
                    "start_line": 6,
                    "end_line": 10,
                    "raw_lines": SOURCE_LINES[5:10],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        return root

    def _add_page(self, root: Path, relative: str, page_id: str, **kwargs) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self._page(root, page_id, **kwargs), encoding="utf-8")
        return path

    def _page(
        self,
        root: Path,
        page_id: str,
        *,
        kind: str = "entity",
        title: str = "# ServerType",
        body_extra: str = "服务器诊断 and ServerType definitions.",
        source_doc: str = "OPC-10000-5",
        version: str = "1.05.06",
        source_sha256: str | None = None,
        status: str = "draft",
        sources: list[dict[str, str]] | None = None,
        body: str | None = None,
    ) -> str:
        if source_sha256 is None:
            source_sha256 = sha256(
                (root / "source" / SOURCE_NAME).read_bytes()
            ).hexdigest()
        if sources is None:
            sources = (
                [{"section": "6.3.1", "table": "9", "lines": "7-9"}]
                if kind == "entity"
                else [{"section": "6.3.1", "lines": "12-12"}]
            )
        if body is None:
            body = (
                f"{title}\n\n{body_extra}\n\n"
                f"[§6.3.1 Table 9 L7-L9](../../source/{SOURCE_NAME}#L7-L9)\n\n"
                "> draft tail marker\n"
            )
        frontmatter = [
            "---",
            f"page_id: {page_id}",
            f"kind: {kind}",
        ]
        if kind == "entity":
            frontmatter.append("entity_id: ObjectType:ServerType")
        frontmatter.extend(
            [
                f"source_doc: {source_doc}",
                f"source_version: {version}",
                f"source_sha256: {source_sha256}",
                f"status: {status}",
                "updated: 2026-11-18",
                f"sources: {json.dumps(sources, ensure_ascii=False)}",
                "---",
                "",
            ]
        )
        return "\n".join(frontmatter) + body

    def _kb(self, root: Path, results: list[dict[str, str]]) -> KnowledgeBase:
        kb = KnowledgeBase(root)
        kb.search = lambda question, top_k=10: [dict(item) for item in results][:top_k]
        return kb

    def test_default_mix_keeps_specification_first_and_wiki_bounded(self):
        root = self._root()
        self._add_page(root, "wiki/entities/servertype.md", "servertype")
        self._add_page(
            root,
            "wiki/topics/diagnostics.md",
            "diagnostics",
            kind="topic",
            title="# 服务器诊断",
        )
        records = Part5Retriever(self._kb(root, SPEC_RESULTS)).retrieve(
            "ServerType 服务器诊断", top_k=6
        )

        self.assertLessEqual(len(records), 6)
        self.assertEqual(records[0].id, "chunk-1")
        wiki_records = [record for record in records if record.type == "wiki"]
        self.assertTrue(wiki_records)
        self.assertLessEqual(len(wiki_records), 2)
        spec_ids = [record.id for record in records if record.type != "wiki"]
        self.assertEqual(spec_ids, ["chunk-1", "chunk-2", "chunk-3"])

        wiki = next(record for record in wiki_records if record.id == "wiki:servertype")
        self.assertEqual(wiki.doc, "OPC-10000-5")
        self.assertEqual(wiki.snippet, wiki.evidence)
        self.assertIn("](../../source/", wiki.evidence)
        self.assertTrue(wiki.evidence.rstrip().endswith("draft tail marker"))
        self.assertEqual(
            set(wiki.provenance),
            {
                "page_id",
                "path",
                "source_doc",
                "source_version",
                "source_sha256",
                "status",
                "sources",
            },
        )
        self.assertEqual(wiki.provenance["path"], "wiki/entities/servertype.md")
        self.assertEqual(wiki.provenance["page_id"], "servertype")
        self.assertEqual(wiki.provenance["status"], "draft")
        self.assertEqual(
            wiki.provenance["sources"],
            [{"section": "6.3.1", "table": "9", "lines": "7-9"}],
        )

    def test_top_k_one_prefers_specification_and_top_k_two_adds_one_wiki(self):
        root = self._root()
        self._add_page(root, "wiki/entities/servertype.md", "servertype")
        retriever = Part5Retriever(self._kb(root, SPEC_RESULTS))

        one = retriever.retrieve("ServerType", top_k=1)
        self.assertEqual([record.id for record in one], ["chunk-1"])

        two = retriever.retrieve("ServerType", top_k=2)
        self.assertEqual(len(two), 2)
        self.assertEqual(two[0].id, "chunk-1")
        self.assertEqual(two[1].type, "wiki")

    def test_chinese_question_with_no_spec_hit_adds_wiki_and_real_source_chunk(self):
        root = self._root()
        self._add_page(
            root,
            "wiki/topics/diagnostics.md",
            "diagnostics",
            kind="topic",
            title="# 服务器诊断",
        )
        records = Part5Retriever(self._kb(root, [])).retrieve("服务器诊断", top_k=2)

        self.assertEqual(len(records), 2)
        companion, wiki = records
        self.assertEqual(companion.type, "chunk")
        self.assertEqual(companion.id, "source:6.3.1:12-12")
        self.assertEqual(companion.evidence, SOURCE_LINES[11])
        self.assertEqual(companion.section, "6.3.1")
        self.assertIsNone(companion.table_number)
        self.assertEqual(companion.provenance["lines"], "12-12")
        self.assertEqual(companion.provenance["version"], "1.05.06")
        self.assertEqual(companion.provenance["path"], f"source/{SOURCE_NAME}")
        self.assertEqual(companion.provenance["hash"], wiki.provenance["source_sha256"])
        self.assertEqual(wiki.type, "wiki")
        self.assertEqual(wiki.id, "wiki:diagnostics")

    def test_missing_wiki_keeps_original_behavior(self):
        root = self._root()
        records = Part5Retriever(self._kb(root, SPEC_RESULTS)).retrieve(
            "ServerType", top_k=2
        )
        self.assertEqual([record.id for record in records], ["chunk-1", "chunk-2"])

    def test_mock_root_is_never_scanned_for_wiki(self):
        kb = Mock()
        kb.search.return_value = [dict(SPEC_RESULTS[0])]
        records = Part5Retriever(kb).retrieve("ServerType", top_k=1)
        self.assertEqual([record.id for record in records], ["chunk-1"])

    def test_invalid_cross_part_stale_hash_and_bad_ranges_are_skipped(self):
        root = self._root()
        self._add_page(root, "wiki/entities/servertype.md", "servertype")
        invalid = {
            "wiki/entities/crosspart.md": self._page(
                root, "crosspart", source_doc="OPC-10000-4"
            ),
            "wiki/entities/stalehash.md": self._page(
                root, "stalehash", source_sha256="0" * 64
            ),
            "wiki/entities/staleversion.md": self._page(
                root, "staleversion", version="0.0.0"
            ),
            "wiki/entities/badsection.md": self._page(
                root, "badsection", sources=[{"section": "99.9", "lines": "1-2"}]
            ),
            "wiki/entities/badtable.md": self._page(
                root, "badtable",
                sources=[{"section": "6.3.1", "table": "99", "lines": "7-9"}],
            ),
            "wiki/entities/outofrange.md": self._page(
                root, "outofrange",
                sources=[{"section": "6.3.1", "table": "9", "lines": "100-200"}],
            ),
            "wiki/entities/malformed.md": "---\npage_id: malformed\n---\n# Bad\n",
        }
        for relative, content in invalid.items():
            (root / relative).write_text(content, encoding="utf-8")

        records = Part5Retriever(self._kb(root, [])).retrieve(
            "ServerType 服务器诊断", top_k=6
        )
        wiki_ids = [record.id for record in records if record.type == "wiki"]
        self.assertEqual(wiki_ids, ["wiki:servertype"])

    def test_search_wiki_exposes_internal_companion_and_full_body(self):
        root = self._root()
        self._add_page(root, "wiki/entities/servertype.md", "servertype")
        hits = search_wiki(self._kb(root, []), "ServerType", top_k=1)

        self.assertEqual(len(hits), 1)
        hit = hits[0]
        self.assertEqual(hit["type"], "wiki")
        self.assertEqual(hit["id"], "wiki:servertype")
        self.assertEqual(hit["provenance"]["path"], "wiki/entities/servertype.md")
        self.assertIn("companion_source", hit)
        self.assertEqual(hit["companion_source"]["type"], "chunk")
        self.assertEqual(hit["evidence"], hit["snippet"])

    def test_long_body_trailing_link_is_not_truncated(self):
        root = self._root()
        long_body = (
            "# 服务器诊断\n\n"
            + ("ServerType 服务器诊断 body.\n" * 200)
            + "[§6.3.1 Table 9 L7-L9](../../source/"
            + SOURCE_NAME
            + "#L7-L9)\n\nTAIL-MARKER\n"
        )
        self._add_page(
            root,
            "wiki/topics/diagnostics.md",
            "diagnostics",
            kind="topic",
            title="# 服务器诊断",
            body=long_body,
        )
        records = Part5Retriever(self._kb(root, [])).retrieve("服务器诊断", top_k=2)
        wiki = next(record for record in records if record.type == "wiki")
        self.assertGreater(len(wiki.evidence), 3000)
        self.assertTrue(wiki.evidence.endswith("TAIL-MARKER\n"))

    def test_manifest_stale_hash_disables_wiki(self):
        root = self._root()
        self._add_page(root, "wiki/entities/servertype.md", "servertype")
        manifest_path = root / "source" / "source_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["sha256"] = "0" * 64
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        records = Part5Retriever(self._kb(root, SPEC_RESULTS)).retrieve(
            "ServerType", top_k=2
        )
        self.assertEqual([record.id for record in records], ["chunk-1", "chunk-2"])

    def test_retrieved_record_provenance_defaults_and_keeps_positional_order(self):
        record = RetrievedRecord("id", "wiki", "Title", "snippet")
        self.assertIsNone(record.provenance)

        with_provenance = RetrievedRecord(
            "id",
            "wiki",
            "Title",
            "snippet",
            "6.3.1",
            None,
            "OPC-10000-5",
            "evidence",
            {"page_id": "p"},
        )
        self.assertEqual(with_provenance.provenance, {"page_id": "p"})


if __name__ == "__main__":
    unittest.main()
