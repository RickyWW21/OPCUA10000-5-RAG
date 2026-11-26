import hashlib
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.helpers import write_jsonl, write_knowledge_base


@unittest.skipUnless(importlib.util.find_spec("mcp"), "install requirements-mcp.txt")
class McpServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_answer_opens_only_issued_hash_bound_excerpt(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        with TemporaryDirectory() as directory:
            root = Path(directory)
            write_knowledge_base(root)
            path = root / "source" / "part5.md"
            path.parent.mkdir()
            path.write_bytes(b"Header\nFirst original line\nSecond original line\n")
            (path.parent / "source_manifest.json").write_text(json.dumps({
                "doc": "OPC-10000-5", "version": "1.05.06",
                "local_source_path": "source/part5.md",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }), encoding="utf-8")
            write_jsonl(root / "kb" / "entities.jsonl", [{
                "id": "ObjectType:ServerType", "name": "ServerType", "kind": "ObjectType",
                "section": "6.3", "summary_en": "ServerType describes the OPC UA Server.",
                "source_ref": {"start_line": 2, "end_line": 3, "section": "6.3"},
            }])
            params = StdioServerParameters(command=sys.executable, args=[
                "-m", "opcua_kb.mcp_server", "--root", directory,
            ], cwd=Path(__file__).resolve().parents[1])
            async with stdio_client(params) as (read, write), ClientSession(read, write) as client:
                await client.initialize()
                tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                self.assertEqual({"ask_part5", "open_part5_citation"}, set(tools))
                uri = tools["ask_part5"].meta["ui"]["resourceUri"]
                widget = (await client.read_resource(uri)).contents[0]
                self.assertEqual("text/html;profile=mcp-app", widget.mimeType)
                answer = await client.call_tool("ask_part5", {"question": "ServerType"})
                self.assertFalse(answer.isError, answer)
                self.assertIn("[E", answer.structuredContent["answer"])
                self.assertTrue(answer.structuredContent["citations"], answer)
                citation = answer.structuredContent["citations"][0]
                self.assertEqual(("6.3", 2, 3), (
                    citation["section"], citation["start_line"], citation["end_line"],
                ))
                ref = answer.meta["citation_refs"][str(citation["id"])]
                request = {"reference": ref}
                excerpt = await client.call_tool("open_part5_citation", request)
                self.assertFalse(excerpt.isError, excerpt)
                self.assertEqual("First original line\nSecond original line", excerpt.meta["content"])
                self.assertEqual("1.05.06", excerpt.meta["version"])
                self.assertIsNone(excerpt.structuredContent)
                forged = await client.call_tool("open_part5_citation", {"reference": "A" * 43})
                self.assertTrue(forged.isError)
                path.write_bytes(b"Header\nChanged original line\nSecond original line\n")
                stale = await client.call_tool("open_part5_citation", request)
                self.assertTrue(stale.isError)
                self.assertIn("fingerprint", stale.content[0].text)
