from __future__ import annotations

import html
import json
import math
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

KIND_COLORS = {
    "ObjectType": "#2563eb",
    "EventType": "#7c3aed",
    "VariableType": "#059669",
    "ReferenceType": "#dc2626",
    "DataType": "#d97706",
    "Method": "#0891b2",
    "Object": "#4f46e5",
    "ModellingRule": "#9333ea",
    "Section": "#64748b",
    "Table": "#475569",
    "External": "#94a3b8",
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
    entity_by_id = {entity["id"]: entity for entity in entities}
    allowed_relations = None if relation is None else {item.strip().upper() for item in relation.split(",") if item.strip()}
    excluded = set() if include_defined else {"DEFINED_BY_TABLE", "DEFINED_IN_SECTION"}
    edge_counter: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    evidence: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for edge in relationships:
        rel = edge.get("relation", "")
        if allowed_relations and rel not in allowed_relations:
            continue
        if rel in excluded:
            continue
        source = edge.get("source")
        target = edge.get("target")
        source = _collapse_node(source, entity_by_id)
        target = _collapse_node(target, entity_by_id)
        if not source or not target or source == target:
            continue
        if _is_low_value_external(source) or _is_low_value_external(target):
            continue
        key = tuple(sorted((source, target)))
        weight = RELATION_WEIGHTS.get(rel, 1)
        edge_counter[key][rel] += weight
        evidence[key].append(
            {
                "source": edge.get("source"),
                "target": edge.get("target"),
                "relation": rel,
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

    seed_ids = _resolve_focus_ids(focus, entities) if focus else set(entity_by_id)
    scoped_nodes = _scope_collapsed_nodes(seed_ids, ranked_edges, depth) if focus else set(entity_by_id)
    scoped_edges = [
        edge for edge in ranked_edges if edge["source"] in scoped_nodes and edge["target"] in scoped_nodes
    ]
    if focus and depth <= 1:
        scoped_edges = [
            edge for edge in scoped_edges if edge["source"] in seed_ids or edge["target"] in seed_ids
        ]

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

    def node_rank(node_id: str) -> tuple[int, int, str]:
        is_seed = 1 if node_id in seed_ids else 0
        return (is_seed, direct_scores[node_id], degrees[node_id], node_id)

    ranked_nodes = sorted(node_ids, key=node_rank, reverse=True)[:limit]
    allowed_nodes = set(ranked_nodes)
    filtered_edges = [
        edge for edge in scoped_edges if edge["source"] in allowed_nodes and edge["target"] in allowed_nodes
    ][: max(limit + 2, limit)]

    nodes = [_node_payload(node_id, entity_by_id, degrees[node_id]) for node_id in ranked_nodes]
    return {
        "metadata": {
            "focus": focus,
            "relation": sorted(allowed_relations) if allowed_relations else None,
            "depth": depth,
            "min_weight": min_weight,
            "include_defined": include_defined,
            "limit": limit,
            "node_count": len(nodes),
            "edge_count": len(filtered_edges),
            "selection": "top-related",
        },
        "nodes": nodes,
        "edges": filtered_edges,
    }


def write_graph_json(graph: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding="utf-8")


def write_graph_html(graph: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_graph_html(graph), encoding="utf-8")


def render_graph_html(graph: dict[str, Any]) -> str:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    width = 1920
    height = 1200
    cx = width / 2
    cy = height / 2
    radius = min(width, height) * 0.50
    positions = _layout(nodes, edges, cx, cy, radius)

    max_weight = max([edge.get("weight", 1) for edge in edges] or [1])
    max_score = max([node.get("score", 1) for node in nodes] or [1])

    edge_svg = []
    for edge in edges:
        sx, sy = positions[edge["source"]]
        tx, ty = positions[edge["target"]]
        stroke = 1.2 + 5.0 * edge.get("weight", 1) / max_weight
        title = f"{edge['source']} -> {edge['target']} | weight={edge.get('weight')} | {', '.join(edge.get('relations', {}).keys())}"
        edge_svg.append(
            f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" '
            f'stroke="#94a3b8" stroke-width="{stroke:.2f}" opacity="0.34">'
            f"<title>{html.escape(title)}</title></line>"
        )

    node_svg = []
    for node in nodes:
        x, y = positions[node["id"]]
        kind = node.get("kind", "External")
        color = KIND_COLORS.get(kind, KIND_COLORS["External"])
        size = 8 + 18 * math.sqrt(max(node.get("score", 1), 1) / max_score)
        label = node.get("label", node["id"])
        details = f"{node['id']} | {kind} | score={node.get('score', 0)} | section={node.get('section', '')}"
        node_svg.append(
            f'<g class="node" data-kind="{html.escape(kind)}">'
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{size:.1f}" fill="{color}" opacity="0.88">'
            f"<title>{html.escape(details)}</title></circle>"
            f'<text x="{x + size + 4:.1f}" y="{y + 4:.1f}">{html.escape(label)}</text>'
            "</g>"
        )

    relation_counts = Counter()
    for edge in edges:
        relation_counts.update(edge.get("relations", {}))
    legend = "\n".join(
        f"<li><span>{html.escape(kind)}</span><b style='background:{color}'></b></li>"
        for kind, color in KIND_COLORS.items()
    )
    top_relations = "\n".join(
        f"<li>{html.escape(name)}: {value}</li>" for name, value in relation_counts.most_common(12)
    )

    graph_json = html.escape(json.dumps(graph, ensure_ascii=False))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>OPC UA 10000-5 Knowledge Graph</title>
  <style>
    body {{ margin: 0; font-family: Segoe UI, Arial, sans-serif; color: #172033; background: #f8fafc; }}
    header {{ padding: 6px 14px 5px; border-bottom: 1px solid #d8dee8; background: #ffffff; }}
    h1 {{ margin: 0 0 1px; font-size: 16px; }}
    p {{ margin: 2px 0; color: #475569; }}
    header p {{ font-size: 12px; }}
    .wrap {{ display: grid; grid-template-columns: minmax(0, 1fr) 160px; min-height: calc(100vh - 42px); }}
    svg {{ width: 100%; height: calc(100vh - 42px); background: #f8fafc; }}
    aside {{ border-left: 1px solid #d8dee8; padding: 8px; background: #fff; overflow: auto; }}
    aside h2 {{ margin: 0 0 6px; font-size: 14px; }}
    aside h3 {{ margin: 10px 0 5px; font-size: 12px; }}
    text {{ font-size: 13px; fill: #172033; paint-order: stroke; stroke: #f8fafc; stroke-width: 3px; }}
    .legend li {{ display: flex; align-items: center; gap: 6px; margin: 5px 0; color: #334155; }}
    .legend b {{ display: inline-block; width: 12px; height: 12px; border-radius: 50%; }}
    code {{ background: #eef2f7; padding: 2px 4px; border-radius: 4px; }}
    .hint {{ font-size: 11px; line-height: 1.25; }}
  </style>
</head>
<body>
  <header>
    <h1>OPC UA 10000-5 Knowledge Graph / 知识图谱</h1>
    <p>Nodes are entities; weighted edges aggregate relationship strength. 节点为实体，边权重表示关联强度。</p>
  </header>
  <main class="wrap">
    <svg viewBox="0 0 {width} {height}" role="img" aria-label="Knowledge graph">
      <g>{''.join(edge_svg)}</g>
      <g>{''.join(node_svg)}</g>
    </svg>
    <aside>
      <h2>Graph</h2>
      <p class="hint">Node count: <code>{len(nodes)}</code></p>
      <p class="hint">Edge count: <code>{len(edges)}</code></p>
      <p class="hint">Hover any node or edge to inspect details. 鼠标悬停可查看节点或关系详情。</p>
      <h3>Node kinds</h3>
      <ul class="legend">{legend}</ul>
      <h3>Top relations</h3>
      <ul>{top_relations}</ul>
      <h3>Raw graph data</h3>
      <p class="hint">The same data is embedded below for debugging or reuse.</p>
      <script type="application/json" id="graph-data">{graph_json}</script>
    </aside>
  </main>
</body>
</html>
"""


def _resolve_focus_ids(focus: str | None, entities: list[dict[str, Any]]) -> set[str]:
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
    value = node_id.lower().replace(" ", "")
    return value in {"-", "--"} or value.startswith("datatype:definedin") or value.startswith("definedin")


def _node_payload(node_id: str, entity_by_id: dict[str, dict[str, Any]], score: int) -> dict[str, Any]:
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


def _layout(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], cx: float, cy: float, radius: float) -> dict[str, tuple[float, float]]:
    if not nodes:
        return {}
    by_kind: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        by_kind[node.get("kind", "External")].append(node)

    positions: dict[str, tuple[float, float]] = {}
    kinds = sorted(by_kind, key=lambda kind: (-len(by_kind[kind]), kind))
    angle_cursor = -math.pi / 2
    for index, kind in enumerate(kinds):
        group = sorted(by_kind[kind], key=lambda item: item.get("score", 0), reverse=True)
        group_radius = radius * (0.66 + 0.30 * (index + 1) / max(len(kinds), 1))
        spread = 2 * math.pi / max(len(kinds), 1)
        start = angle_cursor + index * spread
        for item_index, node in enumerate(group):
            angle = start + spread * item_index / max(len(group), 1)
            jitter = 52 * math.sin((item_index + 1) * 1.7)
            positions[node["id"]] = (
                cx + (group_radius + jitter) * math.cos(angle),
                cy + (group_radius + jitter) * math.sin(angle),
            )

    degree = Counter()
    for edge in edges:
        degree[edge["source"]] += edge.get("weight", 1)
        degree[edge["target"]] += edge.get("weight", 1)
    for node in sorted(nodes, key=lambda item: degree[item["id"]], reverse=True)[:12]:
        angle = 2 * math.pi * len([p for p in positions if p]) / max(len(nodes), 1)
        current = positions[node["id"]]
        positions[node["id"]] = (current[0] * 0.82 + cx * 0.18, current[1] * 0.82 + cy * 0.18)
    return positions


def _norm(value: str) -> str:
    return "".join(value.lower().split())
