"""Executable smoke coverage for every supported public Python API workflow."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from opcua_kb import KnowledgeBase, write_graph_html, write_graph_json


def main() -> None:
    """Run all API checks and write disposable graph exports."""

    configure_console_encoding()

    parser = argparse.ArgumentParser(
        description="Exercise the OPC UA 10000-5 knowledge-base Python API."
    )
    parser.add_argument(
        "--root",
        default=str(ROOT),
        help="Project root that contains kb/ and indexes/. Default: repository root.",
    )
    parser.add_argument(
        "--output-dir",
        default="exports",
        help="Directory for generated graph files. Relative paths are resolved under --root.",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = root / output_dir

    kb = KnowledgeBase(root)

    check_entity_lookup(kb)
    check_search(kb)
    check_chapter_and_table(kb)
    check_relationships(kb)
    check_graph(kb, output_dir)

    print("\nAll Python API checks passed.")


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def check_entity_lookup(kb: KnowledgeBase) -> None:
    print("\n== Entity lookup ==")

    entity = require(kb.get_entity("ServerType"), "ServerType should exist")
    assert_equal(entity["id"], "ObjectType:ServerType")
    assert_equal(entity["kind"], "ObjectType")
    assert_equal(entity["section"], "6.3.1")
    assert_true(entity.get("components"), "ServerType should expose components")

    by_id = require(kb.get_entity("ObjectType:ServerType"), "Lookup by entity id should work")
    assert_equal(by_id["name"], "ServerType")

    print_entity_summary(entity)
    print(f"components: {len(entity.get('components', []))}")


def check_search(kb: KnowledgeBase) -> None:
    print("\n== Search ==")

    entity_results = kb.search("ServerType", top_k=5)
    assert_true(entity_results, "Entity search should return results")
    assert_equal(entity_results[0]["type"], "entity")
    print_results("ServerType", entity_results)

    table_results = kb.search("Table 9", top_k=3)
    assert_true(any(item["type"] == "table" and item["id"] == "table-9" for item in table_results),
                "Table search should find table-9")
    print_results("Table 9", table_results)

    chapter_results = kb.search("6.3.1", top_k=3)
    assert_true(any(item["type"] == "chapter" and item["section"] == "6.3.1" for item in chapter_results),
                "Section search should find chapter 6.3.1")
    print_results("6.3.1", chapter_results)

    natural_results = kb.search("BuildInfo fields", top_k=5)
    assert_true(natural_results, "Full-text search should return natural-language results")
    print_results("BuildInfo fields", natural_results)


def check_chapter_and_table(kb: KnowledgeBase) -> None:
    print("\n== Chapter and table ==")

    chapter = require(kb.chapter("6.3.1"), "Chapter 6.3.1 should exist")
    assert_equal(chapter["title"], "ServerType")
    assert_true("ServerType" in chapter.get("text", ""), "Chapter text should mention ServerType")
    print(f"chapter 6.3.1: {chapter['title']}")

    table = require(kb.table(9), "Table 9 should exist")
    assert_equal(table["id"], "table-9")
    assert_equal(table["caption"], "ServerType definition")
    assert_true(table.get("raw_lines"), "Table 9 should contain raw lines")
    print(f"table 9: {table['caption']} ({len(table.get('raw_lines', []))} raw lines)")


def check_relationships(kb: KnowledgeBase) -> None:
    print("\n== Relationships ==")

    component_edges = kb.relationships("ServerType", relation="HAS_COMPONENT", depth=1)
    assert_true(component_edges, "ServerType should have HAS_COMPONENT edges")
    print_edges("HAS_COMPONENT depth=1", component_edges)

    property_edges = kb.relationships("ServerType", relation="HAS_PROPERTY", depth=1)
    assert_true(property_edges, "ServerType should have HAS_PROPERTY edges")
    print_edges("HAS_PROPERTY depth=1", property_edges)

    all_edges = kb.relationships("ServerType", depth=2)
    assert_true(len(all_edges) >= len(component_edges), "Depth 2 should include at least direct component edges")
    print(f"all relations depth=2: {len(all_edges)} edges")


def check_graph(kb: KnowledgeBase, output_dir: Path) -> None:
    print("\n== Knowledge graph ==")

    graph = kb.graph(
        focus="ServerType",
        relation="HAS_COMPONENT,USES_DATATYPE,HAS_PROPERTY",
        depth=2,
        min_weight=1,
        include_defined=False,
        limit=12,
    )
    metadata = graph["metadata"]
    assert_true(metadata["node_count"] > 0, "Graph should contain nodes")
    assert_true(metadata["edge_count"] > 0, "Graph should contain edges")

    json_path = output_dir / "python_api_smoke_graph.json"
    html_path = output_dir / "python_api_smoke_graph.html"
    write_graph_json(graph, json_path)
    write_graph_html(graph, html_path)

    assert_true(json_path.exists(), "Graph JSON should be written")
    assert_true(html_path.exists(), "Graph HTML should be written")
    check_embedded_graph_json(html_path)

    print(json.dumps(metadata, ensure_ascii=False, indent=2))
    print(f"graph json: {json_path}")
    print(f"graph html: {html_path}")


def check_embedded_graph_json(html_path: Path) -> None:
    """Verify that browser-consumed script payloads remain valid JSON."""

    page = html_path.read_text(encoding="utf-8")
    for element_id in ("graph-data", "graph-positions"):
        match = re.search(
            rf'id="{element_id}">(.*?)</script>',
            page,
            flags=re.DOTALL,
        )
        assert_true(match, f"Graph HTML should embed {element_id}")
        payload = match.group(1)
        assert_true("&quot;" not in payload, f"{element_id} should not contain HTML entities")
        json.loads(payload)


def print_entity_summary(entity: dict[str, Any]) -> None:
    print(f"id: {entity['id']}")
    print(f"name: {entity['name']}")
    print(f"kind: {entity['kind']}")
    print(f"section: {entity.get('section')}")
    print(f"tables: {', '.join(entity.get('related_tables', []))}")


def print_results(query: str, results: list[dict[str, Any]]) -> None:
    print(f"\nquery: {query}")
    for index, item in enumerate(results[:3], start=1):
        snippet = (item.get("snippet") or "").replace("\n", " ")
        if len(snippet) > 120:
            snippet = snippet[:117] + "..."
        print(
            f"  {index}. {item.get('type')} {item.get('title')} "
            f"[id={item.get('id')}, section={item.get('section')}, table={item.get('table_number')}]"
        )
        if snippet:
            print(f"     {snippet}")


def print_edges(label: str, edges: list[dict[str, Any]]) -> None:
    print(f"{label}: {len(edges)} edges")
    for edge in edges[:5]:
        ref = edge.get("source_ref", {})
        print(
            f"  {edge.get('source')} --{edge.get('relation')}--> {edge.get('target')} "
            f"[section={ref.get('section')}, table={ref.get('table')}]"
        )


def require(value: Any, message: str) -> Any:
    assert_true(value is not None, message)
    return value


def assert_true(condition: Any, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def assert_equal(actual: Any, expected: Any) -> None:
    if actual != expected:
        raise AssertionError(f"Expected {expected!r}, got {actual!r}")


if __name__ == "__main__":
    main()
