"""Diagram structure extraction from text bboxes + PDF vector drawings.

Replaces label-chaining heuristics. Emits Process/Architecture style graphs
only from geometry (containment, line endpoints, column order) — no domain keywords.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass, field

from backend.skills.ingestion.pdf_parser import DrawingPrim, RawTextBlock


@dataclass
class GraphNode:
    node_id: str
    label: str
    bbox: tuple[float, float, float, float]
    group: str | None = None
    node_type: str | None = None


@dataclass
class GraphEdge:
    from_node_id: str
    to_node_id: str
    label: str | None = None
    medium: str | None = None
    confidence: float = 0.5


@dataclass
class StructureGraph:
    kind: str  # PROCESS | ARCHITECTURE
    title: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    groups: list[str] = field(default_factory=list)
    confidence: float = 0.5
    verification_status: str = "REQUIRES_VISUAL_CHECK"

    def to_payload(self) -> dict:
        return {
            "kind": self.kind,
            "title": self.title,
            "nodes": [asdict(n) for n in self.nodes],
            "edges": [asdict(e) for e in self.edges],
            "groups": list(self.groups),
        }


_SKIP_LABELS = {
    "manufacturing on naver cloud platform",
    "contents",
}


def extract_structure_graph(
    blocks: list[RawTextBlock],
    drawings: list[DrawingPrim],
    *,
    page_width: float,
    page_height: float,
    page_title_hint: str | None = None,
) -> StructureGraph | None:
    """Build a structure graph for DIAGRAM/MIXED pages."""
    nodes = _nodes_from_blocks(blocks, page_width, page_height)
    if len(nodes) < 2:
        return None

    rects = [d for d in drawings if d.kind == "rect"]
    lines = [d for d in drawings if d.kind == "line"]

    groups = _assign_groups(nodes, rects, page_width, page_height)
    group_names = sorted({n.group for n in nodes if n.group})

    line_edges = _edges_from_lines(nodes, lines, page_width)
    kind = _infer_kind(
        nodes, groups=group_names, edge_count=len(line_edges), rect_count=len(rects)
    )
    if len(line_edges) >= 2:
        edges = line_edges
    else:
        # Raster flowcharts: column stacks are the only geometric signal
        edges = _dedupe_edges(line_edges + _edges_from_columns(nodes, page_width))
        if len(edges) >= 3 and not group_names:
            kind = "PROCESS"
    edges = _dedupe_edges(edges)
    title = (page_title_hint or "").strip() or (
        "시스템 구성" if kind == "ARCHITECTURE" else "업무 절차"
    )

    conf = 0.55
    if lines and edges:
        conf = 0.78
    if groups and kind == "ARCHITECTURE":
        conf = max(conf, 0.72)
    if edges and kind == "PROCESS":
        conf = max(conf, 0.7)
    status = "VERIFIED" if conf >= 0.75 and edges else "REQUIRES_VISUAL_CHECK"

    return StructureGraph(
        kind=kind,
        title=title[:80],
        nodes=nodes,
        edges=edges,
        groups=group_names,
        confidence=conf,
        verification_status=status,
    )


def to_structure_row(
    graph: StructureGraph,
    *,
    source_id: str,
    page_number: int,
) -> dict:
    return {
        "fact_id": f"SF-{uuid.uuid4().hex[:10].upper()}",
        "source_id": source_id,
        "page_number": page_number,
        "fact_kind": graph.kind,
        "title": graph.title,
        "payload_json": json.dumps(graph.to_payload(), ensure_ascii=False),
        "confidence": graph.confidence,
        "verification_status": graph.verification_status,
    }


def _nodes_from_blocks(
    blocks: list[RawTextBlock], page_width: float, page_height: float
) -> list[GraphNode]:
    nodes: list[GraphNode] = []
    seen: set[str] = set()
    for b in blocks:
        if b.block_type in {"IMAGE", "STRUCTURE"}:
            continue
        raw = (b.text or "").strip()
        if not raw or raw == "[IMAGE]" or "|" in raw and len(raw) > 40:
            continue
        # Prefer first line for multiline; skip footer-ish wide lines
        label = raw.splitlines()[0].strip()
        label = re.sub(r"^§\s*", "", label)
        if " · " in label:
            # repeated icons — expand as separate nodes sharing band
            for part in label.split(" · "):
                _add_node(nodes, seen, part.strip(), b.bbox, page_width, page_height)
            continue
        _add_node(nodes, seen, label, b.bbox, page_width, page_height)
    return nodes


def _add_node(
    nodes: list[GraphNode],
    seen: set[str],
    label: str,
    bbox: tuple[float, float, float, float],
    page_width: float,
    page_height: float,
) -> None:
    label = label.strip()
    if not label or len(label) > 36:
        return
    if label.lower() in _SKIP_LABELS:
        return
    if "|" in label:
        return
    if label.isdigit() and len(label) == 4:
        return
    key = re.sub(r"\s+", "", label.lower())
    if key in seen or len(key) < 2:
        return
    # skip full-width titles as graph nodes (keep as page title separately)
    w = bbox[2] - bbox[0]
    if w > page_width * 0.55 and bbox[1] < page_height * 0.2:
        return
    seen.add(key)
    nodes.append(
        GraphNode(
            node_id=f"N{len(nodes)}",
            label=label,
            bbox=bbox,
        )
    )


def _assign_groups(
    nodes: list[GraphNode],
    rects: list[DrawingPrim],
    page_width: float,
    page_height: float,
) -> list[str]:
    """Large rectangles that contain ≥2 node centers become groups."""
    page_area = max(page_width * page_height, 1.0)
    containers: list[tuple[float, DrawingPrim]] = []
    for r in rects:
        area = max(0.0, (r.bbox[2] - r.bbox[0]) * (r.bbox[3] - r.bbox[1]))
        if area < page_area * 0.04 or area > page_area * 0.85:
            continue
        containers.append((area, r))
    containers.sort(key=lambda t: t[0])  # small first for tightest fit

    # Also treat wide short text labels above clusters as group names via proximity
    group_labels: dict[str, str] = {}
    for n in nodes:
        cx = (n.bbox[0] + n.bbox[2]) / 2.0
        cy = (n.bbox[1] + n.bbox[3]) / 2.0
        best = None
        best_area = None
        for area, r in containers:
            x0, y0, x1, y1 = r.bbox
            if x0 <= cx <= x1 and y0 <= cy <= y1:
                if best_area is None or area < best_area:
                    best_area = area
                    best = r
        if best is None:
            continue
        # Name group by nearest node above rect top, else rect id
        gname = _group_name_for_rect(nodes, best.bbox) or f"구역{len(group_labels)+1}"
        n.group = gname
        group_labels[gname] = gname

    # Fallback: x-band groups when no rect containers
    if not group_labels and len(nodes) >= 4:
        from backend.skills.ingestion.layout_rebuild import _cluster_columns

        fake_blocks = [
            RawTextBlock(text=n.label, bbox=n.bbox, block_type="TEXT") for n in nodes
        ]
        cols = _cluster_columns(fake_blocks, page_width)
        if len(cols) >= 2:
            for i, col in enumerate(cols):
                if len(col) < 2:
                    continue
                head = sorted(col, key=lambda b: b.bbox[1])[0].text.strip()
                gname = head[:20] if len(head) <= 20 else f"열{i+1}"
                labels = {b.text.strip() for b in col}
                for n in nodes:
                    if n.label in labels:
                        # head itself is group name; members get group
                        if n.label == head and len(col) >= 2:
                            n.node_type = "group_header"
                        n.group = gname
                group_labels[gname] = gname

    return list(group_labels.keys())


def _group_name_for_rect(
    nodes: list[GraphNode], rect: tuple[float, float, float, float]
) -> str | None:
    x0, y0, x1, y1 = rect
    # Prefer a label near the top-inside of the rect
    candidates = []
    for n in nodes:
        cx = (n.bbox[0] + n.bbox[2]) / 2.0
        cy = (n.bbox[1] + n.bbox[3]) / 2.0
        if x0 <= cx <= x1 and y0 <= cy <= y0 + max(40.0, (y1 - y0) * 0.25):
            candidates.append((cy, n.label))
    if candidates:
        candidates.sort()
        return candidates[0][1][:24]
    return None


def _edges_from_lines(
    nodes: list[GraphNode], lines: list[DrawingPrim], page_width: float
) -> list[GraphEdge]:
    if not lines or len(nodes) < 2:
        return []
    tol = max(28.0, page_width * 0.035)
    edges: list[GraphEdge] = []
    for line in lines:
        if len(line.points) < 2:
            continue
        p0, p1 = line.points[0], line.points[-1]
        a = _nearest_node(nodes, p0, tol)
        b = _nearest_node(nodes, p1, tol)
        if a is None or b is None or a.node_id == b.node_id:
            continue
        # Edge label if a short node sits mid-line (VPN, Internet)
        mid = ((p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0)
        mid_n = _nearest_node(nodes, mid, tol * 0.8)
        label = None
        medium = None
        if mid_n and mid_n.node_id not in {a.node_id, b.node_id}:
            label = mid_n.label
            if len(mid_n.label) <= 12:
                medium = mid_n.label
        edges.append(
            GraphEdge(
                from_node_id=a.node_id,
                to_node_id=b.node_id,
                label=label,
                medium=medium,
                confidence=0.82,
            )
        )
    return edges


def _edges_from_columns(nodes: list[GraphNode], page_width: float) -> list[GraphEdge]:
    """Within each vertical band, connect top→bottom neighbors (flowchart columns)."""
    from backend.skills.ingestion.layout_rebuild import _cluster_columns

    fake = [RawTextBlock(text=n.label, bbox=n.bbox, block_type="TEXT") for n in nodes]
    cols = _cluster_columns(fake, page_width)
    by_label = {n.label: n for n in nodes}
    edges: list[GraphEdge] = []
    for col in cols:
        if len(col) < 2:
            continue
        ordered = sorted(col, key=lambda b: (b.bbox[1] + b.bbox[3]) / 2.0)
        for a, b in zip(ordered, ordered[1:]):
            na, nb = by_label.get(a.text.strip()), by_label.get(b.text.strip())
            if not na or not nb or na.node_id == nb.node_id:
                continue
            # only if vertically stacked with small gap
            gap = nb.bbox[1] - na.bbox[3]
            if gap > page_width * 0.15:
                continue
            edges.append(
                GraphEdge(
                    from_node_id=na.node_id,
                    to_node_id=nb.node_id,
                    confidence=0.62,
                )
            )
    return edges


def _nearest_node(
    nodes: list[GraphNode],
    point: tuple[float, float],
    tol: float,
) -> GraphNode | None:
    px, py = point
    best = None
    best_d = tol
    for n in nodes:
        # distance to bbox edge / center
        x0, y0, x1, y1 = n.bbox
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        # clamp to bbox then distance
        qx = min(max(px, x0), x1)
        qy = min(max(py, y0), y1)
        d = ((px - qx) ** 2 + (py - qy) ** 2) ** 0.5
        d_center = ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5
        d = min(d, d_center * 0.85)
        if d <= best_d:
            best_d = d
            best = n
    return best


def _dedupe_edges(edges: list[GraphEdge]) -> list[GraphEdge]:
    seen: set[tuple[str, str]] = set()
    out: list[GraphEdge] = []
    for e in edges:
        key = (e.from_node_id, e.to_node_id)
        rev = (e.to_node_id, e.from_node_id)
        if key in seen or rev in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _infer_kind(
    nodes: list[GraphNode],
    *,
    groups: list[str],
    edge_count: int,
    rect_count: int,
) -> str:
    # Contained groups / larger rects → architecture; skinny column flows → process
    if len(groups) >= 2 and rect_count >= 2:
        return "ARCHITECTURE"
    avg_label = sum(len(n.label) for n in nodes) / max(len(nodes), 1)
    if avg_label <= 14 and len(nodes) >= 6 and edge_count >= 3:
        return "PROCESS"
    if len(groups) >= 2:
        return "ARCHITECTURE"
    return "PROCESS" if len(nodes) >= 8 else "ARCHITECTURE"


def refine_structure_with_llm(
    graph: StructureGraph,
    *,
    image_path: str | None,
    page_text: str,
) -> StructureGraph:
    """Optional vision/text refine. No-op when offline or on failure."""
    import base64
    import os
    from pathlib import Path

    from backend.config import settings

    if settings.llm_mode == "offline":
        return graph
    if os.getenv("TAS_DIAGRAM_LLM", "0").lower() in ("0", "false", "no"):
        return graph
    # Skip when already strong vector-backed graph
    if graph.confidence >= 0.78 and graph.edges:
        return graph

    try:
        from backend.model_providers.base import call_ollama_json
    except Exception:
        return graph

    payload = graph.to_payload()
    prompt = (
        "You refine a diagram structure extracted from a document page.\n"
        "Return JSON with keys: nodes (list of {id,label,group}), "
        "edges (list of {from,to,label}), groups (list of strings).\n"
        "Only use labels visible on the page. Do not invent systems.\n"
        f"Candidate graph:\n{json.dumps(payload, ensure_ascii=False)[:3500]}\n"
        f"Page text:\n{(page_text or '')[:1200]}"
    )
    images = None
    if image_path and Path(image_path).is_file():
        try:
            images = [base64.b64encode(Path(image_path).read_bytes()).decode("ascii")]
        except OSError:
            images = None
    try:
        data = call_ollama_json(
            "Extract diagram nodes/edges/groups as JSON only.",
            prompt,
            temperature=0.1,
            timeout=90.0,
            images_b64=images,
        )
    except Exception:
        return graph

    return _merge_llm_refine(graph, data)


def _merge_llm_refine(graph: StructureGraph, data: dict) -> StructureGraph:
    raw_nodes = data.get("nodes") or []
    raw_edges = data.get("edges") or []
    raw_groups = data.get("groups") or graph.groups
    if not isinstance(raw_nodes, list) or len(raw_nodes) < 2:
        return graph

    id_map: dict[str, str] = {}
    nodes: list[GraphNode] = []
    by_old = {n.node_id: n for n in graph.nodes}
    by_label = {n.label: n for n in graph.nodes}

    for i, rn in enumerate(raw_nodes):
        if not isinstance(rn, dict):
            continue
        label = str(rn.get("label") or "").strip()
        if not label:
            continue
        old = by_label.get(label)
        nid = f"N{i}"
        old_id = str(rn.get("id") or "")
        if old_id:
            id_map[old_id] = nid
        bbox = old.bbox if old else (0.0, 0.0, 0.0, 0.0)
        group = rn.get("group") or (old.group if old else None)
        nodes.append(
            GraphNode(node_id=nid, label=label, bbox=bbox, group=str(group) if group else None)
        )
        id_map[label] = nid

    if len(nodes) < 2:
        return graph

    label_to_id = {n.label: n.node_id for n in nodes}
    edges: list[GraphEdge] = []
    for re_ in raw_edges:
        if not isinstance(re_, dict):
            continue
        frm = str(re_.get("from") or re_.get("from_node_id") or "")
        to = str(re_.get("to") or re_.get("to_node_id") or "")
        frm_id = id_map.get(frm) or label_to_id.get(frm)
        to_id = id_map.get(to) or label_to_id.get(to)
        # also map via old node ids
        if not frm_id and frm in by_old:
            frm_id = label_to_id.get(by_old[frm].label)
        if not to_id and to in by_old:
            to_id = label_to_id.get(by_old[to].label)
        if not frm_id or not to_id or frm_id == to_id:
            continue
        edges.append(
            GraphEdge(
                from_node_id=frm_id,
                to_node_id=to_id,
                label=(str(re_.get("label")) if re_.get("label") else None),
                confidence=0.8,
            )
        )

    groups = [str(g) for g in raw_groups if g] if isinstance(raw_groups, list) else graph.groups
    return StructureGraph(
        kind=graph.kind,
        title=graph.title,
        nodes=nodes,
        edges=_dedupe_edges(edges) if edges else graph.edges,
        groups=groups or graph.groups,
        confidence=min(0.9, graph.confidence + 0.1),
        verification_status="VERIFIED" if edges else graph.verification_status,
    )
