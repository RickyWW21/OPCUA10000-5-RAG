"""Render offline OPC UA knowledge-graph HTML exports."""

from __future__ import annotations

import html
import json
import math
from collections import Counter, defaultdict
from typing import Any


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

def render_interactive_graph_html(graph: dict[str, Any]) -> str:
    """Render SVG markup and browser-side pan, zoom, drag, and detail behavior."""

    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    width = 2400
    height = 1600
    cx = width / 2
    cy = height / 2
    radius = min(width, height) * 0.46
    positions = _layout(nodes, edges, cx, cy, radius)

    max_weight = max([edge.get("weight", 1) for edge in edges] or [1])
    max_score = max([node.get("score", 1) for node in nodes] or [1])

    # Geometry is rendered server-side; JavaScript only mutates transforms and edge
    # endpoints during interaction, so the file remains useful without a web server.
    edge_svg = []
    for edge in edges:
        if edge["source"] not in positions or edge["target"] not in positions:
            continue
        sx, sy = positions[edge["source"]]
        tx, ty = positions[edge["target"]]
        stroke = 1.2 + 5.0 * edge.get("weight", 1) / max_weight
        relations = ", ".join(edge.get("relations", {}).keys())
        title = f"{edge['source']} -> {edge['target']} | weight={edge.get('weight')} | {relations}"
        edge_svg.append(
            f'<line class="edge" data-source="{html.escape(edge["source"])}" '
            f'data-target="{html.escape(edge["target"])}" data-title="{html.escape(title)}" '
            f'data-relations="{html.escape(relations)}" data-weight="{edge.get("weight", 1)}" '
            f'x1="{sx:.1f}" y1="{sy:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" '
            f'stroke="#94a3b8" stroke-width="{stroke:.2f}" opacity="0.34">'
            f"<title>{html.escape(title)}</title></line>"
        )

    node_svg = []
    for node in nodes:
        x, y = positions[node["id"]]
        kind = node.get("kind", "External")
        color = KIND_COLORS.get(kind, KIND_COLORS["External"])
        size = 7 + 17 * math.sqrt(max(node.get("score", 1), 1) / max_score)
        label = node.get("label", node["id"])
        details = f"{node['id']} | {kind} | score={node.get('score', 0)} | section={node.get('section', '')}"
        summary = node.get("summary_zh") or node.get("summary_en") or ""
        node_svg.append(
            f'<g class="node" data-id="{html.escape(node["id"])}" data-label="{html.escape(label)}" '
            f'data-kind="{html.escape(kind)}" data-section="{html.escape(str(node.get("section") or ""))}" '
            f'data-score="{html.escape(str(node.get("score", 0)))}" data-summary="{html.escape(summary)}" '
            f'transform="translate({x:.1f} {y:.1f})">'
            f'<circle r="{size:.1f}" fill="{color}" opacity="0.90">'
            f"<title>{html.escape(details)}</title></circle>"
            f'<text x="{size + 4:.1f}" y="4">{html.escape(label)}</text>'
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

    graph_json = _json_for_html_script(graph)
    positions_json = _json_for_html_script(
        {key: {"x": value[0], "y": value[1]} for key, value in positions.items()}
    )
    metadata = graph.get("metadata", {})
    selection = html.escape(str(metadata.get("selection", "")))
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>OPC UA 10000-5 Knowledge Graph</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: Segoe UI, Arial, sans-serif; color: #172033; background: #f8fafc; overflow: hidden; }}
    header {{ height: 52px; padding: 7px 14px 6px; border-bottom: 1px solid #d8dee8; background: #ffffff; }}
    h1 {{ margin: 0 0 2px; font-size: 16px; font-weight: 650; }}
    p {{ margin: 2px 0; color: #475569; }}
    header p {{ font-size: 12px; }}
    .wrap {{ display: grid; grid-template-columns: minmax(0, 1fr) 260px; height: calc(100vh - 52px); }}
    .stage {{ position: relative; min-width: 0; background: #f8fafc; }}
    svg {{ width: 100%; height: 100%; display: block; cursor: grab; touch-action: none; background: #f8fafc; }}
    svg.dragging {{ cursor: grabbing; }}
    .toolbar {{ position: absolute; left: 10px; top: 10px; display: flex; gap: 6px; align-items: center; z-index: 2; }}
    button {{ height: 30px; min-width: 30px; border: 1px solid #cbd5e1; background: #fff; color: #172033; border-radius: 6px; font-size: 14px; cursor: pointer; }}
    button:hover {{ background: #f1f5f9; }}
    aside {{ border-left: 1px solid #d8dee8; padding: 10px; background: #fff; overflow: auto; }}
    aside h2 {{ margin: 0 0 7px; font-size: 14px; }}
    aside h3 {{ margin: 12px 0 6px; font-size: 12px; }}
    aside ul {{ padding-left: 17px; margin: 6px 0; }}
    text {{ font-size: 12px; fill: #172033; paint-order: stroke; stroke: #f8fafc; stroke-width: 3px; pointer-events: none; }}
    .node {{ cursor: move; }}
    .node circle {{ stroke: #ffffff; stroke-width: 1.5; }}
    .node.active circle {{ stroke: #0f172a; stroke-width: 3; }}
    .edge.active {{ stroke: #0f172a; opacity: 0.82; }}
    .legend li {{ display: flex; align-items: center; justify-content: space-between; gap: 6px; margin: 5px 0; color: #334155; }}
    .legend b {{ display: inline-block; width: 12px; height: 12px; border-radius: 50%; flex: 0 0 auto; }}
    code {{ background: #eef2f7; padding: 2px 4px; border-radius: 4px; }}
    .hint {{ font-size: 11px; line-height: 1.3; }}
    .detail {{ border-top: 1px solid #e2e8f0; margin-top: 10px; padding-top: 10px; }}
    .detail-title {{ font-weight: 650; color: #0f172a; overflow-wrap: anywhere; }}
    .detail-row {{ margin-top: 5px; font-size: 12px; color: #475569; overflow-wrap: anywhere; }}
  </style>
</head>
<body>
  <header>
    <h1>OPC UA 10000-5 Knowledge Graph</h1>
    <p>Drag the canvas to pan, use the mouse wheel to zoom, drag nodes to rearrange, and click nodes or edges for details.</p>
  </header>
  <main class="wrap">
    <section class="stage">
      <div class="toolbar">
        <button type="button" id="zoom-in" title="Zoom in">+</button>
        <button type="button" id="zoom-out" title="Zoom out">-</button>
        <button type="button" id="reset-view" title="Reset view">1:1</button>
        <button type="button" id="fit-view" title="Fit graph">Fit</button>
      </div>
      <svg id="graph" viewBox="0 0 {width} {height}" role="img" aria-label="Knowledge graph">
        <g id="viewport">
          <g id="edges">{''.join(edge_svg)}</g>
          <g id="nodes">{''.join(node_svg)}</g>
        </g>
      </svg>
    </section>
    <aside>
      <h2>Graph</h2>
      <p class="hint">Node count: <code>{len(nodes)}</code></p>
      <p class="hint">Edge count: <code>{len(edges)}</code></p>
      <p class="hint">Selection: <code>{selection}</code></p>
      <h3>Node kinds</h3>
      <ul class="legend">{legend}</ul>
      <h3>Top relations</h3>
      <ul>{top_relations}</ul>
      <section class="detail" id="details">
        <div class="detail-title">No selection</div>
        <div class="detail-row">Click a node or edge to inspect it.</div>
      </section>
      <h3>Raw graph data</h3>
      <p class="hint">The same data is embedded in the page for debugging or reuse.</p>
      <script type="application/json" id="graph-data">{graph_json}</script>
      <script type="application/json" id="graph-positions">{positions_json}</script>
    </aside>
  </main>
  <script>
    const svg = document.getElementById("graph");
    const viewport = document.getElementById("viewport");
    const details = document.getElementById("details");
    const positions = JSON.parse(document.getElementById("graph-positions").textContent);
    const nodes = Array.from(document.querySelectorAll(".node"));
    const edges = Array.from(document.querySelectorAll(".edge"));
    // View translation and scale are independent from model-space node positions.
    const view = {{ x: 0, y: 0, scale: 1 }};
    let interaction = null;

    function applyView() {{
      viewport.setAttribute("transform", `translate(${{view.x}} ${{view.y}}) scale(${{view.scale}})`);
    }}

    function eventPoint(event) {{
      const point = svg.createSVGPoint();
      point.x = event.clientX;
      point.y = event.clientY;
      const transformed = point.matrixTransform(svg.getScreenCTM().inverse());
      return {{
        x: (transformed.x - view.x) / view.scale,
        y: (transformed.y - view.y) / view.scale,
      }};
    }}

    function setNodePosition(id, x, y) {{
      // A dragged node owns both its transform and every connected edge endpoint.
      positions[id] = {{ x, y }};
      const node = document.querySelector(`.node[data-id="${{CSS.escape(id)}}"]`);
      if (node) node.setAttribute("transform", `translate(${{x}} ${{y}})`);
      for (const edge of edges) {{
        if (edge.dataset.source === id) {{
          edge.setAttribute("x1", x);
          edge.setAttribute("y1", y);
        }}
        if (edge.dataset.target === id) {{
          edge.setAttribute("x2", x);
          edge.setAttribute("y2", y);
        }}
      }}
    }}

    function clearActive() {{
      for (const node of nodes) node.classList.remove("active");
      for (const edge of edges) edge.classList.remove("active");
    }}

    function escapeHtml(value) {{
      return String(value).replace(/[&<>"']/g, char => ({{
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      }}[char]));
    }}

    function showNode(node) {{
      clearActive();
      node.classList.add("active");
      const connected = edges.filter(edge => edge.dataset.source === node.dataset.id || edge.dataset.target === node.dataset.id);
      for (const edge of connected) edge.classList.add("active");
      details.innerHTML = `
        <div class="detail-title">${{escapeHtml(node.dataset.label || node.dataset.id)}}</div>
        <div class="detail-row"><b>ID:</b> ${{escapeHtml(node.dataset.id || "")}}</div>
        <div class="detail-row"><b>Kind:</b> ${{escapeHtml(node.dataset.kind || "")}}</div>
        <div class="detail-row"><b>Section:</b> ${{escapeHtml(node.dataset.section || "-")}}</div>
        <div class="detail-row"><b>Score:</b> ${{escapeHtml(node.dataset.score || "0")}}</div>
        <div class="detail-row"><b>Links:</b> ${{connected.length}}</div>
        <div class="detail-row">${{escapeHtml(node.dataset.summary || "")}}</div>
      `;
    }}

    function showEdge(edge) {{
      clearActive();
      edge.classList.add("active");
      details.innerHTML = `
        <div class="detail-title">${{escapeHtml(edge.dataset.source)}} to ${{escapeHtml(edge.dataset.target)}}</div>
        <div class="detail-row"><b>Weight:</b> ${{escapeHtml(edge.dataset.weight || "")}}</div>
        <div class="detail-row"><b>Relations:</b> ${{escapeHtml(edge.dataset.relations || "")}}</div>
      `;
    }}

    function zoomAt(clientX, clientY, factor) {{
      // Recalculate translation so the graph point under the pointer stays fixed.
      const before = eventPoint({{ clientX, clientY }});
      view.scale = Math.max(0.12, Math.min(8, view.scale * factor));
      const after = eventPoint({{ clientX, clientY }});
      view.x += (after.x - before.x) * view.scale;
      view.y += (after.y - before.y) * view.scale;
      applyView();
    }}

    function fitView() {{
      // Fit model-space bounds into the fixed SVG viewBox with label padding.
      const values = Object.values(positions);
      if (!values.length) return;
      const xs = values.map(item => item.x);
      const ys = values.map(item => item.y);
      const minX = Math.min(...xs) - 120;
      const maxX = Math.max(...xs) + 220;
      const minY = Math.min(...ys) - 120;
      const maxY = Math.max(...ys) + 120;
      const width = svg.viewBox.baseVal.width;
      const height = svg.viewBox.baseVal.height;
      view.scale = Math.max(0.12, Math.min(width / (maxX - minX), height / (maxY - minY)));
      view.x = (width - (maxX + minX) * view.scale) / 2;
      view.y = (height - (maxY + minY) * view.scale) / 2;
      applyView();
    }}

    svg.addEventListener("pointerdown", event => {{
      const node = event.target.closest(".node");
      if (node) {{
        const current = positions[node.dataset.id];
        const point = eventPoint(event);
        interaction = {{ type: "node", id: node.dataset.id, dx: current.x - point.x, dy: current.y - point.y }};
        node.setPointerCapture(event.pointerId);
        showNode(node);
        return;
      }}
      interaction = {{ type: "pan", x: event.clientX, y: event.clientY, startX: view.x, startY: view.y }};
      svg.classList.add("dragging");
      svg.setPointerCapture(event.pointerId);
    }});

    svg.addEventListener("pointermove", event => {{
      if (!interaction) return;
      if (interaction.type === "node") {{
        const point = eventPoint(event);
        setNodePosition(interaction.id, point.x + interaction.dx, point.y + interaction.dy);
      }} else {{
        view.x = interaction.startX + (event.clientX - interaction.x);
        view.y = interaction.startY + (event.clientY - interaction.y);
        applyView();
      }}
    }});

    svg.addEventListener("pointerup", () => {{
      interaction = null;
      svg.classList.remove("dragging");
    }});

    svg.addEventListener("pointercancel", () => {{
      interaction = null;
      svg.classList.remove("dragging");
    }});

    svg.addEventListener("wheel", event => {{
      event.preventDefault();
      zoomAt(event.clientX, event.clientY, event.deltaY < 0 ? 1.12 : 0.88);
    }}, {{ passive: false }});

    for (const node of nodes) {{
      node.addEventListener("click", event => {{
        event.stopPropagation();
        showNode(node);
      }});
    }}
    for (const edge of edges) {{
      edge.addEventListener("click", event => {{
        event.stopPropagation();
        showEdge(edge);
      }});
    }}

    document.getElementById("zoom-in").addEventListener("click", () => zoomAt(window.innerWidth / 2, window.innerHeight / 2, 1.2));
    document.getElementById("zoom-out").addEventListener("click", () => zoomAt(window.innerWidth / 2, window.innerHeight / 2, 0.8));
    document.getElementById("reset-view").addEventListener("click", () => {{
      view.x = 0;
      view.y = 0;
      view.scale = 1;
      applyView();
    }});
    document.getElementById("fit-view").addEventListener("click", fitView);
    fitView();
  </script>
</body>
</html>
"""


def _render_static_graph_html(graph: dict[str, Any]) -> str:
    """Retain the non-interactive renderer for simple or legacy consumers."""

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

    graph_json = _json_for_html_script(graph)
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



def _layout(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], cx: float, cy: float, radius: float) -> dict[str, tuple[float, float]]:
    """Create a deterministic radial layout grouped by OPC UA node kind."""

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
        current = positions[node["id"]]
        positions[node["id"]] = (current[0] * 0.82 + cx * 0.18, current[1] * 0.82 + cy * 0.18)
    return positions


def _json_for_html_script(value: Any) -> str:
    """Serialize JSON for a raw-text script element without ending the element early."""

    # HTML entities are not decoded inside script raw text. Unicode escapes keep the
    # payload valid JSON and neutralize values containing a literal ``</script>``.
    return (
        json.dumps(value, ensure_ascii=False)
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
