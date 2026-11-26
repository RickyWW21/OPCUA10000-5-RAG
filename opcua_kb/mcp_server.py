"""Private stdio tools for the existing Part 5 RAG and source viewer."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import secrets
from collections import OrderedDict
from pathlib import Path

from fastapi import HTTPException
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server
from pydantic import AnyUrl

from .api import load_source_manifest
from .http_api import QueryRequest, _execute_query, create_app
from .source_view import SourceViewError

WIDGET = "ui://opcua/part5-citations.html"
MIME = "text/html;profile=mcp-app"
ANSWER_SCHEMA = {
    "type": "object",
    "required": ["answer", "mode", "citations"],
    "properties": {
        "answer": {"type": "string"},
        "mode": {"type": "string"},
        "citations": {"type": "array", "items": {"type": "object"}},
    },
}


def _tool(name, title, description, field, min_length, max_length, meta, output=None):
    return types.Tool(
        name=name, title=title, description=description,
        inputSchema={
            "type": "object", "additionalProperties": False, "required": [field],
            "properties": {field: {
                "type": "string", "minLength": min_length, "maxLength": max_length,
            }},
        },
        outputSchema=output,
        annotations=types.ToolAnnotations(readOnlyHint=True, destructiveHint=False, openWorldHint=False),
        _meta=meta,
    )


def _error(message: str) -> types.CallToolResult:
    return types.CallToolResult(isError=True, content=[types.TextContent(type="text", text=message)])


def create_server(root: Path, *, online: bool = False) -> Server:
    # Reuse the API's execution and source validation without binding an HTTP socket.
    app = create_app(root)
    server = Server("OPC UA Part 5", instructions=(
        "Use ask_part5 for OPC UA Part 5 questions. Preserve its citation labels. "
        "The answer card lets the user open exact source lines."
    ))
    # ponytail: process-local bounded references; ask again after restart or eviction.
    references: OrderedDict[str, tuple[str, int, int, str]] = OrderedDict()

    @server.list_tools()
    async def list_tools():
        return [
            _tool("ask_part5", "Ask OPC UA Part 5", "Answer from the Part 5 knowledge base with citations.",
                  "question", 1, 2000, {
                      "ui": {"resourceUri": WIDGET}, "openai/outputTemplate": WIDGET,
                  }, ANSWER_SCHEMA),
            _tool("open_part5_citation", "Open cited specification lines",
                  "Open only a reference issued by the answer card.",
                  "reference", 43, 43, {
                      "ui": {"visibility": ["app"]}, "openai/visibility": "private",
                      "openai/widgetAccessible": True,
                  }),
        ]

    @server.list_resources()
    async def list_resources():
        return [types.Resource(uri=AnyUrl(WIDGET), name="Part 5 answer and citations", mimeType=MIME)]

    @server.read_resource()
    async def read_resource(uri):
        if str(uri) != WIDGET:
            raise ValueError("Unknown resource")
        return [ReadResourceContents(
            content=Path(__file__).with_name("mcp_citations.html").read_text(encoding="utf-8"),
            mime_type=MIME,
            meta={
                "ui": {"prefersBorder": True, "csp": {"connectDomains": [], "resourceDomains": []}},
                "openai/widgetDescription": "Displays the Part 5 answer and expands verified source excerpts on click.",
            },
        )]

    @server.call_tool()
    async def call_tool(name, arguments):
        if name == "open_part5_citation":
            target = references.get(arguments["reference"])
            if target is None:
                return _error("Citation expired or invalid. Ask the question again.")
            path, start, end, digest = target
            try:
                excerpt = await asyncio.to_thread(
                    app.state.source_view.content, path, start_line=start, end_line=end, sha256=digest,
                )
            except SourceViewError as exc:
                return _error(exc.detail)
            return types.CallToolResult(content=[], _meta=excerpt)

        question = arguments["question"].strip()
        if not question:
            return _error("Enter a Part 5 question.")
        try:
            result = await asyncio.to_thread(_execute_query, app, QueryRequest(question=question, online=online))
        except HTTPException:
            return _error("The local Part 5 index is unavailable.")
        try:
            manifest = load_source_manifest(root)
        except (OSError, ValueError):
            manifest = {}
        citations, refs = [], {}
        for citation in result["citations"]:
            source = citation.get("source") or {}
            legacy = source.get("kind") == "legacy_wiki"
            path = source.get("spec_path" if legacy else "path")
            digest = source.get("spec_sha256") if legacy else manifest.get("sha256")
            version = source.get("version")
            for location in source.get("locations") or [{}]:
                start, end = location.get("start_line"), location.get("end_line")
                idx = len(citations)
                if (
                    source.get("kind") in {"spec", "legacy_wiki"}
                    and version == manifest.get("version")
                    and path and isinstance(digest, str) and re.fullmatch(r"[0-9a-fA-F]{64}", digest)
                    and isinstance(start, int) and isinstance(end, int) and 1 <= start <= end
                ):
                    ref = secrets.token_urlsafe(32)
                    references[ref] = (path, start, end, digest)
                    refs[str(idx)] = ref
                    if len(references) > 2048:
                        references.popitem(last=False)
                citations.append({
                    "id": idx, "label": citation["label"], "title": citation.get("title"),
                    "version": version, "kind": source.get("kind"),
                    "section": location.get("section"), "start_line": start, "end_line": end,
                })
        return types.CallToolResult(
            content=[],
            structuredContent={"answer": result["answer"], "mode": result["mode"], "citations": citations},
            _meta={"citation_refs": refs},
        )

    return server


async def _run(server: Server) -> None:
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(os.getenv("KB_ROOT") or Path(__file__).resolve().parents[1]))
    parser.add_argument("--online", action="store_true", help="Enable the existing environment-configured RAG model.")
    args = parser.parse_args()
    asyncio.run(_run(create_server(args.root.resolve(), online=args.online)))
