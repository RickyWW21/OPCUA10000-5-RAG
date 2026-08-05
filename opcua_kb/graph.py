"""Aggregate relationships and render offline OPC UA knowledge-graph exports."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

RELATION_WEIGHTS = {
    "HAS_COMPONENT": 5,
    "HAS_PROPERTY": 4,
    "HAS_FIELD": 4,
    "USES_DATATYPE": 3,
    "HAS_TYPE_DEFINITION": 3,
    "HAS_SUBTYPE": 3,
    "HAS_MODELLING_RULE": 2,
    "HAS_CONFORMANCE_UNIT": 1,
    "DEFINED_BY_TABLE": 1,
    "DEFINED_IN_SECTION": 1,
}

def build_knowledge_graph(
    entities: list[dict[str, Any]],
    relationships: list[dict[str, Any]],
    *,
    focus: str | None = None,
    relation: str | None = None,
    depth: int = 1,
    min_weight: int = 1,
    include_defined: bool = False,
    limit: int = 12,
) -> dict[str, Any]:
    """Collapse raw relationship records into a weighted, display-ready graph."""

    entity_by_id = {entity["id"]: entity for entity in entities}
    allowed_relations = _allowed_relations(relation)
    excluded = set() if include_defined else {"DEFINED_BY_TABLE", "DEFINED_IN_SECTION"}
    ranked_edges = _aggregate_collapsed_edges(
        relationships, entity_by_id, allowed_relations, excluded, min_weight
    )
    seed_ids, scoped_edges = _scope_edges(focus, entities, entity_by_id, ranked_edges, depth)
    ranked_nodes, degrees, filtered_edges = _rank_graph_nodes(
        scoped_edges, seed_ids, focus, limit
    )
    nodes = [
        _node_payload(node_id, entity_by_id, degrees[node_id])
        for node_id in ranked_nodes
    ]
    return {
        "metadata": _graph_metadata(
            focus,
            allowed_relations,
            depth,
            min_weight,
            include_defined,
            limit,
            len(nodes),
            len(filtered_edges),
        ),
        "nodes": nodes,
        "edges": filtered_edges,
    }


def _allowed_relations(relation: str | None) -> set[str] | None:
    """Normalize a comma-separated relation filter or retain all relations."""

    if relation is None:
        return None
    return {item.strip().upper() for item in relation.split(",") if item.strip()}


def _aggregate_collapsed_edges(
    relationships: list[dict[str, Any]],
    entity_by_id: dict[str, dict[str, Any]],
    allowed_relations: set[str] | None,
    excluded_relations: set[str],
    min_weight: int,
) -> list[dict[str, Any]]:
    """Filter raw edges, collapse component IDs, and aggregate visible pairs."""

    edge_counter: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    evidence: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    # Multiple raw references between the same pair become one weighted edge while
    # retaining a small evidence sample for inspection.
    for edge in relationships:
        relation = edge.get("relation", "")
        if allowed_relations and relation not in allowed_relations:
            continue
        if relation in excluded_relations:
            continue
        source = _collapse_node(edge.get("source"), entity_by_id)
        target = _collapse_node(edge.get("target"), entity_by_id)
        if not source or not target or source == target:
            continue
        if _is_low_value_external(source) or _is_low_value_external(target):
            continue
        first, second = sorted((source, target))
        key: tuple[str, str] = (first, second)
        edge_counter[key][relation] += RELATION_WEIGHTS.get(relation, 1)
        evidence[key].append(
            {
                "source": edge.get("source"),
                "target": edge.get("target"),
                "relation": relation,
                "source_ref": edge.get("source_ref", {}),
            }
        )

    ranked_edges = []
    for (source, target), relations in edge_counter.items():
        weight = sum(relations.values())
        if weight < min_weight:
            continue
        ranked_edges.append(
            {
                "source": source,
                "target": target,
                "weight": weight,
                "relations": dict(relations),
                "evidence": evidence[(source, target)][:8],
            }
        )
    ranked_edges.sort(key=lambda item: item["weight"], reverse=True)
    return ranked_edges


def _scope_edges(
    focus: str | None,
    entities: list[dict[str, Any]],
    entity_by_id: dict[str, dict[str, Any]],
    ranked_edges: list[dict[str, Any]],
    depth: int,
) -> tuple[set[str], list[dict[str, Any]]]:
    """Limit edges to the requested focus neighborhood after node collapse."""

    # Scope traversal happens after component IDs are collapsed, matching the nodes
    # that users actually see rather than transient field/component identifiers.
    seed_ids = _resolve_focus_ids(focus, entities) if focus else set(entity_by_id)
    scoped_nodes = _scope_collapsed_nodes(seed_ids, ranked_edges, depth) if focus else set(entity_by_id)
    scoped_edges = [
        edge for edge in ranked_edges if edge["source"] in scoped_nodes and edge["target"] in scoped_nodes
    ]
    if focus and depth <= 1:
        scoped_edges = [
            edge for edge in scoped_edges if edge["source"] in seed_ids or edge["target"] in seed_ids
        ]
    return seed_ids, scoped_edges


def _rank_graph_nodes(
    scoped_edges: list[dict[str, Any]], seed_ids: set[str], focus: str | None, limit: int
) -> tuple[list[str], Counter[str], list[dict[str, Any]]]:
    """Rank graph nodes, apply the requested limit, and keep compatible edges."""

    # Ranking keeps focus nodes first, then favors direct and globally strong links.
    degrees: Counter[str] = Counter()
    direct_scores: Counter[str] = Counter()
    for edge in scoped_edges:
        degrees[edge["source"]] += edge["weight"]
        degrees[edge["target"]] += edge["weight"]
        if focus:
            if edge["source"] in seed_ids:
                direct_scores[edge["target"]] += edge["weight"]
            if edge["target"] in seed_ids:
                direct_scores[edge["source"]] += edge["weight"]

    node_ids = set()
    for edge in scoped_edges:
        node_ids.add(edge["source"])
        node_ids.add(edge["target"])
    if focus:
        node_ids.update(seed_ids)

    def node_rank(node_id: str) -> tuple[int, int, int, str]:
        is_seed = 1 if node_id in seed_ids else 0
        return (is_seed, direct_scores[node_id], degrees[node_id], node_id)

    ranked_nodes = sorted(node_ids, key=node_rank, reverse=True)
    if limit > 0:
        ranked_nodes = ranked_nodes[:limit]
    allowed_nodes = set(ranked_nodes)
    filtered_edges = [
        edge for edge in scoped_edges if edge["source"] in allowed_nodes and edge["target"] in allowed_nodes
    ]
    if limit > 0:
        filtered_edges = filtered_edges[: max(limit + 2, limit)]
    return ranked_nodes, degrees, filtered_edges


def _graph_metadata(
    focus: str | None,
    allowed_relations: set[str] | None,
    depth: int,
    min_weight: int,
    include_defined: bool,
    limit: int,
    node_count: int,
    edge_count: int,
) -> dict[str, Any]:
    """Build the stable metadata schema returned with every graph payload."""

    return {
        "focus": focus,
        "relation": sorted(allowed_relations) if allowed_relations else None,
        "depth": depth,
        "min_weight": min_weight,
        "include_defined": include_defined,
        "limit": limit,
        "node_count": node_count,
        "edge_count": edge_count,
        "selection": "all" if limit <= 0 else "top-related",
    }


def write_graph_json(graph: dict[str, Any], path: Path) -> None:
    """Write a graph payload as human-readable UTF-8 JSON."""

    contents = json.dumps(graph, ensure_ascii=False, indent=2)
    _write_graph_export(contents, path)


def write_graph_html(graph: dict[str, Any], path: Path) -> None:
    """Write a self-contained interactive graph page to disk."""

    contents = render_graph_html(graph)
    _write_graph_export(contents, path)


def _write_graph_export(contents: str, path: Path) -> None:
    """Create the export directory and write content with actionable I/O errors."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OSError(f"Unable to create graph export directory for: {path}") from exc
    try:
        path.write_text(contents, encoding="utf-8")
    except OSError as exc:
        raise OSError(f"Unable to write graph export: {path}") from exc


def render_graph_html(graph: dict[str, Any]) -> str:
    """Render the graph as a self-contained interactive HTML document."""

    from .graph_render import render_interactive_graph_html

    return render_interactive_graph_html(graph)


def _resolve_focus_ids(focus: str | None, entities: list[dict[str, Any]]) -> set[str]:
    """Resolve a graph focus by exact ID or normalized entity name."""

    if not focus:
        return set()
    normalized = _norm(focus)
    result = set()
    for entity in entities:
        if entity["id"] == focus or _norm(entity["name"]) == normalized or _norm(entity["id"]) == normalized:
            result.add(entity["id"])
    return result or {focus}


def _scope_collapsed_nodes(
    seeds: set[str],
    edges: list[dict[str, Any]],
    depth: int,
) -> set[str]:
    """Collect nodes reachable from the focus set within the requested depth."""

    scoped = set(seeds)
    frontier = set(seeds)
    for _ in range(max(depth, 1)):
        next_frontier = set()
        for edge in edges:
            source = edge.get("source")
            target = edge.get("target")
            if source in frontier:
                next_frontier.add(target)
            if target in frontier:
                next_frontier.add(source)
        next_frontier -= scoped
        scoped.update(next_frontier)
        frontier = next_frontier
        if not frontier:
            break
    return scoped


def _collapse_node(node_id: str | None, entity_by_id: dict[str, dict[str, Any]]) -> str | None:
    """Map component-like IDs back to their owning top-level graph entity."""

    if not node_id:
        return None
    if node_id in entity_by_id:
        return node_id
    compact_node_id = node_id.replace(" ", "")
    if compact_node_id in entity_by_id:
        return compact_node_id
    if ":" in node_id:
        prefix, value = node_id.split(":", 1)
        compact_candidate = f"{prefix}:{value.replace(' ', '')}"
        if compact_candidate in entity_by_id:
            return compact_candidate
        if prefix == "DataType":
            base_value = value.replace("[]", "").replace("[", "").replace("]", "").replace(" ", "")
            base_candidate = f"DataType:{base_value}"
            if base_candidate in entity_by_id:
                return base_candidate
    if "." in node_id:
        prefix, rest = node_id.split(":", 1) if ":" in node_id else ("", node_id)
        owner = rest.split(".", 1)[0]
        owner = owner.replace(" ", "")
        for candidate in (
            f"ObjectType:{owner}",
            f"EventType:{owner}",
            f"VariableType:{owner}",
            f"DataType:{owner}",
            f"Object:{owner}",
            f"Method:{owner}",
        ):
            if candidate in entity_by_id:
                return candidate
        return f"{prefix}:{owner}" if prefix else owner
    return node_id


def _is_low_value_external(node_id: str) -> bool:
    """Identify parser artifacts that should not become visible graph nodes."""

    value = node_id.lower().replace(" ", "")
    return value in {"-", "--"} or value.startswith("datatype:definedin") or value.startswith("definedin")


def _node_payload(node_id: str, entity_by_id: dict[str, dict[str, Any]], score: int) -> dict[str, Any]:
    """Build display metadata for either a known entity or an external node."""

    entity = entity_by_id.get(node_id)
    if entity:
        return {
            "id": node_id,
            "label": entity.get("name", node_id),
            "kind": entity.get("kind", "External"),
            "section": entity.get("section"),
            "tables": entity.get("related_tables", []),
            "score": score,
            "summary_zh": entity.get("summary_zh", ""),
            "summary_en": entity.get("summary_en", ""),
        }
    kind = "External"
    if node_id.startswith("sec-"):
        kind = "Section"
    elif node_id.startswith("table-"):
        kind = "Table"
    elif ":" in node_id:
        kind = node_id.split(":", 1)[0]
    return {"id": node_id, "label": node_id.split(":")[-1], "kind": kind, "score": score}


def _norm(value: str) -> str:
    return "".join(value.lower().split())
