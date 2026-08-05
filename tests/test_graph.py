"""Graph construction and HTML payload contract tests."""

from __future__ import annotations

import unittest
import subprocess
import sys

from opcua_kb.graph import build_knowledge_graph, render_graph_html
from opcua_kb.graph_render import render_interactive_graph_html


class GraphTests(unittest.TestCase):
    """Protect graph aggregation and offline viewer contract behavior."""

    def test_graph_collapses_components_aggregates_edges_and_respects_limit(self) -> None:
        entities = [
            {
                "id": "ObjectType:ServerType",
                "name": "ServerType",
                "kind": "ObjectType",
                "section": "6.3",
            },
            {
                "id": "DataType:BuildInfo",
                "name": "BuildInfo",
                "kind": "DataType",
                "section": "12.1",
            },
        ]
        relationships = [
            {
                "source": "ObjectType:ServerType.BuildInfo",
                "target": "DataType:BuildInfo",
                "relation": "HAS_COMPONENT",
            },
            {
                "source": "ObjectType:ServerType",
                "target": "DataType:BuildInfo",
                "relation": "HAS_COMPONENT",
            },
        ]

        graph = build_knowledge_graph(
            entities, relationships, focus="ServerType", depth=1, limit=2
        )

        self.assertEqual(2, graph["metadata"]["node_count"])
        self.assertEqual(10, graph["edges"][0]["weight"])

    def test_html_embeds_safe_graph_payload_and_interaction_controls(self) -> None:
        page = render_graph_html({"nodes": [], "edges": [], "metadata": {}})

        self.assertIn('id="graph-data"', page)
        self.assertIn('id="fit-view"', page)

    def test_renderer_module_matches_public_html_renderer_for_empty_graph(self) -> None:
        graph = {"nodes": [], "edges": [], "metadata": {}}

        self.assertEqual(render_graph_html(graph), render_interactive_graph_html(graph))

    def test_graph_model_import_does_not_load_renderer(self) -> None:
        command = [sys.executable, "-c", "import opcua_kb.graph; import sys; assert 'opcua_kb.graph_render' not in sys.modules"]

        self.assertEqual(0, subprocess.run(command, check=False).returncode)

    def test_graph_filters_relations_weights_and_defined_edges(self) -> None:
        entities = [
            {"id": "ObjectType:A", "name": "A", "kind": "ObjectType"},
            {"id": "ObjectType:B", "name": "B", "kind": "ObjectType"},
            {"id": "ObjectType:C", "name": "C", "kind": "ObjectType"},
        ]
        relationships = [
            {"source": "ObjectType:A", "target": "ObjectType:B", "relation": "HAS_COMPONENT"},
            {"source": "ObjectType:A", "target": "ObjectType:C", "relation": "DEFINED_BY_TABLE"},
        ]

        graph = build_knowledge_graph(
            entities,
            relationships,
            relation="has_component,defined_by_table",
            min_weight=5,
            limit=0,
        )

        self.assertEqual(1, graph["metadata"]["edge_count"])
        self.assertEqual("HAS_COMPONENT", next(iter(graph["edges"][0]["relations"])))

    def test_graph_aggregates_reciprocal_relations_between_entities(self) -> None:
        entities = [
            {"id": "ObjectType:A", "name": "A", "kind": "ObjectType"},
            {"id": "ObjectType:B", "name": "B", "kind": "ObjectType"},
        ]
        relationships = [
            {"source": "ObjectType:A", "target": "ObjectType:B", "relation": "HAS_COMPONENT"},
            {"source": "ObjectType:B", "target": "ObjectType:A", "relation": "USES_DATATYPE"},
        ]

        graph = build_knowledge_graph(
            entities, relationships, include_defined=True, limit=0
        )

        self.assertEqual(1, graph["metadata"]["edge_count"])
        self.assertEqual(
            {"HAS_COMPONENT": 5, "USES_DATATYPE": 3},
            graph["edges"][0]["relations"],
        )

    def test_focus_depth_one_excludes_second_hop_edges(self) -> None:
        entities = [
            {"id": "ObjectType:A", "name": "A", "kind": "ObjectType"},
            {"id": "ObjectType:B", "name": "B", "kind": "ObjectType"},
            {"id": "ObjectType:C", "name": "C", "kind": "ObjectType"},
        ]
        relationships = [
            {"source": "ObjectType:A", "target": "ObjectType:B", "relation": "HAS_COMPONENT"},
            {"source": "ObjectType:B", "target": "ObjectType:C", "relation": "HAS_COMPONENT"},
        ]

        graph = build_knowledge_graph(entities, relationships, focus="A", depth=1, limit=0)

        self.assertEqual(1, graph["metadata"]["edge_count"])
        self.assertEqual({"ObjectType:A", "ObjectType:B"}, {node["id"] for node in graph["nodes"]})
