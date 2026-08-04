"""Build visual specs, validate them, and render assets."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

from backend.domain.enums import VisualType
from backend.domain.visual import VisualRequest
from backend.skills.visuals.chart_renderer import render_bar_chart, render_line_chart
from backend.skills.visuals.graphviz_renderer import render_architecture_png, to_dot, write_dot
from backend.skills.visuals.mermaid_renderer import (
    render_process_png,
    to_mermaid_flowchart,
    write_mermaid,
)
from backend.skills.visuals.table_renderer import render_markdown_table, write_csv
from backend.skills.visuals.visual_validator import count_unrendered
from backend.storage.edition_repository import EvidencePackRepository, SectionRepository
from backend.storage.plan_repository import PlanRepository


class VisualSpecService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.sections = SectionRepository(conn)
        self.packs = EvidencePackRepository(conn)
        self.plans = PlanRepository(conn)

    def collect_requests(self, edition_id: str, project_id: str) -> list[VisualRequest]:
        requests: list[VisualRequest] = []
        sections = self.sections.list_for_edition(edition_id)

        # Metrics → bar chart / comparison table
        metric_rows = []
        for section in sections:
            pack_row = (
                self.packs.get(section["evidence_pack_id"])
                if section.get("evidence_pack_id")
                else self.packs.get_for_section(section["section_id"])
            )
            if not pack_row:
                continue
            for m in pack_row["pack"].get("metrics") or []:
                metric_rows.append({**m, "section_id": section["section_id"]})

        if metric_rows:
            dedup: dict[str, dict] = {}
            for m in metric_rows:
                mid = m.get("metric_id") or f"M-{len(dedup)+1}"
                if m.get("change_value") is None:
                    continue
                dedup[mid] = m
            metric_rows = list(dedup.values())
        if metric_rows:
            sid = metric_rows[0]["section_id"]
            pages = sorted({int(m.get("page_number") or 0) for m in metric_rows if m.get("page_number")})
            requests.append(
                VisualRequest(
                    visual_id=f"VIS-{uuid.uuid4().hex[:8].upper()}",
                    section_id=sid,
                    visual_type=VisualType.BAR_CHART,
                    title="정량 성과 지표",
                    purpose="업로드 자료의 정량 변화 시각화",
                    evidence_ids=[m.get("metric_id") or "" for m in metric_rows],
                    source_pages=pages,
                    render_spec={
                        "labels": [m.get("name", "지표")[:20] for m in metric_rows],
                        "values": [
                            float(m["change_value"])
                            * (-1 if m.get("direction") == "DECREASE" and float(m.get("change_value") or 0) > 0 else 1)
                            for m in metric_rows
                        ],
                        "source_note": f"근거 페이지: {', '.join(str(p) for p in pages)}",
                    },
                )
            )
            requests.append(
                VisualRequest(
                    visual_id=f"VIS-{uuid.uuid4().hex[:8].upper()}",
                    section_id=sid,
                    visual_type=VisualType.COMPARISON_TABLE,
                    title="정량 성과 표",
                    purpose="지표·변화·측정방법 정리",
                    source_pages=pages,
                    render_spec={
                        "headers": ["지표", "변화", "단위", "방향", "측정방법", "페이지"],
                        "rows": [
                            [
                                m.get("name") or "",
                                str(m.get("change_value") or ""),
                                m.get("change_unit") or "",
                                m.get("direction") or "",
                                (m.get("measurement_method") or "")[:80],
                                str(m.get("page_number") or ""),
                            ]
                            for m in metric_rows
                        ],
                    },
                )
            )

        # Process / architecture from stored structure_facts (no fake label-chaining)
        process_spec = self._load_process_from_facts(project_id)
        if process_spec:
            sec = sections[0]["section_id"] if sections else "SEC-NA"
            for s in sections:
                if any(k in (s.get("title") or "") for k in ("프로세스", "흐름", "업무", "절차")):
                    sec = s["section_id"]
                    break
            requests.append(
                VisualRequest(
                    visual_id=f"VIS-{uuid.uuid4().hex[:8].upper()}",
                    section_id=sec,
                    visual_type=VisualType.PROCESS_FLOW,
                    title=process_spec.get("title") or "업무/기술 프로세스 흐름",
                    purpose="structure_facts 기반 흐름 재구성",
                    source_pages=process_spec.get("pages", []),
                    render_spec={"steps": process_spec["steps"]},
                )
            )

        arch = self._load_architecture_from_facts(project_id)
        if arch.get("nodes"):
            sec = sections[0]["section_id"] if sections else "SEC-NA"
            for s in sections:
                if any(k in (s.get("title") or "") for k in ("구성", "아키텍처", "시스템")):
                    sec = s["section_id"]
                    break
            # Only draw edges that were geometrically/LLM verified — never invent chains
            requests.append(
                VisualRequest(
                    visual_id=f"VIS-{uuid.uuid4().hex[:8].upper()}",
                    section_id=sec,
                    visual_type=VisualType.ARCHITECTURE_DIAGRAM,
                    title=arch.get("title") or "시스템 구성도",
                    purpose="structure_facts 기반 노드·연결 (미검증 간선 없음)",
                    source_pages=arch.get("pages", []),
                    render_spec={"nodes": arch["nodes"], "edges": arch.get("edges") or []},
                )
            )
        return requests

    def _load_process_from_facts(self, project_id: str) -> dict:
        rows = self._structure_rows(project_id, "PROCESS")
        for r in rows:
            try:
                payload = json.loads(r["payload_json"] or "{}")
            except json.JSONDecodeError:
                continue
            steps = [
                str(n.get("label") or "").strip()
                for n in (payload.get("nodes") or [])
                if n.get("label")
            ]
            steps = [s for s in steps if 1 < len(s) <= 36][:12]
            if len(steps) >= 2:
                return {
                    "title": r["title"],
                    "steps": steps,
                    "pages": [int(r["page_number"])],
                }
        return {}

    def _load_architecture_from_facts(self, project_id: str) -> dict:
        rows = self._structure_rows(project_id, "ARCHITECTURE")
        for r in rows:
            try:
                payload = json.loads(r["payload_json"] or "{}")
            except json.JSONDecodeError:
                continue
            nodes = []
            for n in payload.get("nodes") or []:
                label = str(n.get("label") or "").strip()
                if not label:
                    continue
                nodes.append(
                    {
                        "id": str(n.get("node_id") or f"N{len(nodes)}"),
                        "label": label[:40],
                        "group": n.get("group"),
                    }
                )
            if len(nodes) < 2:
                continue
            id_set = {n["id"] for n in nodes}
            edges = []
            for e in payload.get("edges") or []:
                frm = str(e.get("from_node_id") or e.get("from") or "")
                to = str(e.get("to_node_id") or e.get("to") or "")
                if frm in id_set and to in id_set and frm != to:
                    edges.append(
                        {
                            "from": frm,
                            "to": to,
                            "label": e.get("label") or e.get("medium"),
                        }
                    )
            return {
                "title": r["title"],
                "nodes": nodes[:16],
                "edges": edges[:24],
                "pages": [int(r["page_number"])],
            }
        return {"nodes": [], "edges": [], "pages": []}

    def _structure_rows(self, project_id: str, kind: str) -> list:
        try:
            return self.conn.execute(
                """
                SELECT sf.*
                FROM structure_facts sf
                JOIN sources s ON s.source_id = sf.source_id
                WHERE s.project_id = ? AND sf.fact_kind = ?
                ORDER BY sf.confidence DESC, sf.page_number
                """,
                (project_id, kind),
            ).fetchall()
        except sqlite3.OperationalError:
            return []


class VisualValidationService:
    FORBIDDEN_TOKENS = {"component", "시작", "처리", "종료", "김기헌", "감사합니다"}

    def validate(self, req: VisualRequest) -> tuple[bool, str | None]:
        spec = req.render_spec or {}
        blob = json.dumps(spec, ensure_ascii=False).lower()
        if any(tok in blob for tok in self.FORBIDDEN_TOKENS):
            return False, "forbidden placeholder token"
        if req.visual_type in {VisualType.BAR_CHART, VisualType.LINE_CHART}:
            labels = list(spec.get("labels") or [])
            values = list(spec.get("values") or [])
            if not labels or not values or len(labels) != len(values):
                return False, "invalid chart series"
        if req.visual_type in {VisualType.PROCESS_FLOW, VisualType.TIMELINE}:
            steps = [s for s in (spec.get("steps") or []) if str(s).strip()]
            if len(steps) < 2:
                return False, "insufficient process steps"
        if req.visual_type == VisualType.ARCHITECTURE_DIAGRAM:
            nodes = list(spec.get("nodes") or [])
            if len(nodes) < 2:
                return False, "insufficient architecture nodes"
        if req.visual_type in {VisualType.COMPARISON_TABLE, VisualType.TABLE, VisualType.MATRIX}:
            rows = list(spec.get("rows") or [])
            if not rows:
                return False, "empty table rows"
        return True, None


class VisualRenderService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def render_all(self, requests: list[VisualRequest], out_dir: Path) -> dict:
        out_dir.mkdir(parents=True, exist_ok=True)
        rendered: dict[str, Path] = {}
        embeds: dict[str, str] = {}
        validator = VisualValidationService()
        validated: list[VisualRequest] = []

        for req in requests:
            ok, _reason = validator.validate(req)
            if not ok:
                continue
            validated.append(req)
            paths, embed = self._render_one(req, out_dir)
            if paths:
                rendered[req.visual_id] = paths[0]
                for p in paths[1:]:
                    rendered[f"{req.visual_id}:{p.suffix}"] = p
                self._save_asset(req, paths[0])
            if embed:
                embeds[req.visual_id] = embed
        self.conn.commit()
        return {
            "rendered": {k: str(v) for k, v in rendered.items()},
            "embeds": embeds,
            "unrendered": count_unrendered(
                [r.model_dump(mode="json") for r in validated],
                {r.visual_id: rendered[r.visual_id] for r in validated if r.visual_id in rendered},
            ),
            "requests": [r.model_dump(mode="json") for r in validated],
        }

    def _save_asset(self, req: VisualRequest, path: Path) -> None:
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(visual_assets)").fetchall()}
        if {"asset_id", "source_id", "edition_id", "visual_type", "title", "storage_path", "render_spec_json", "evidence_ids_json"}.issubset(cols):
            self.conn.execute(
                """
                INSERT OR REPLACE INTO visual_assets (
                    asset_id, source_id, edition_id, visual_type, title, storage_path, render_spec_json, evidence_ids_json
                ) VALUES (?, NULL, NULL, ?, ?, ?, ?, ?)
                """,
                (
                    req.visual_id,
                    req.visual_type.value,
                    req.title,
                    str(path),
                    json.dumps(req.render_spec, ensure_ascii=False),
                    json.dumps(req.evidence_ids, ensure_ascii=False),
                ),
            )
            return
        if {"asset_id", "visual_id", "asset_kind", "file_path", "created_at"}.issubset(cols):
            from datetime import datetime, timezone
            self.conn.execute(
                """
                INSERT OR REPLACE INTO visual_assets (asset_id, visual_id, asset_kind, file_path, created_at)
                VALUES (?, ?, 'primary', ?, ?)
                """,
                (
                    f"VAS-{uuid.uuid4().hex[:8].upper()}",
                    req.visual_id,
                    str(path),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def _render_one(self, req: VisualRequest, out_dir: Path) -> tuple[list[Path], str]:
        spec = req.render_spec or {}
        base = out_dir / req.visual_id
        paths: list[Path] = []
        embed = ""
        if req.visual_type in {VisualType.BAR_CHART, VisualType.LINE_CHART}:
            labels = list(spec.get("labels") or [])
            values = [float(v) for v in (spec.get("values") or [])]
            png = Path(str(base) + ".png")
            note = spec.get("source_note")
            if req.visual_type == VisualType.LINE_CHART:
                render_line_chart(png, title=req.title, labels=labels, values=values, source_note=note)
            else:
                render_bar_chart(png, title=req.title, labels=labels, values=values, source_note=note)
            paths.append(png)
            embed = f"![{req.title}](visuals/{png.name})\n\n*{note or req.purpose}*"
        elif req.visual_type in {VisualType.TABLE, VisualType.COMPARISON_TABLE, VisualType.MATRIX}:
            headers = list(spec.get("headers") or [])
            rows = list(spec.get("rows") or [])
            md = render_markdown_table(headers, rows, title=req.title)
            csv_path = write_csv(Path(str(base) + ".csv"), headers, rows)
            paths.append(csv_path)
            embed = md
        elif req.visual_type in {VisualType.PROCESS_FLOW, VisualType.TIMELINE}:
            steps = list(spec.get("steps") or [])
            mmd = to_mermaid_flowchart(steps, title=req.title)
            mmd_path = write_mermaid(Path(str(base) + ".mmd"), mmd)
            png = render_process_png(
                Path(str(base) + ".png"),
                steps,
                title=req.title,
                source_note=f"pages: {req.source_pages}" if req.source_pages else None,
            )
            paths.extend([png, mmd_path])
            embed = f"![{req.title}](visuals/{png.name})\n\n```mermaid\n{mmd}```\n"
        elif req.visual_type == VisualType.ARCHITECTURE_DIAGRAM:
            nodes = list(spec.get("nodes") or [])
            edges = list(spec.get("edges") or [])
            dot = to_dot(nodes, edges, title=req.title)
            dot_path = write_dot(Path(str(base) + ".dot"), dot)
            png = render_architecture_png(
                Path(str(base) + ".png"),
                nodes,
                edges,
                title=req.title,
                source_note=f"pages: {req.source_pages}" if req.source_pages else None,
            )
            paths.extend([png, dot_path])
            embed = f"![{req.title}](visuals/{png.name})\n"
        return paths, embed


class VisualService:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.specs = VisualSpecService(conn)
        self.renderer = VisualRenderService(conn)

    def collect_requests(self, edition_id: str, project_id: str) -> list[VisualRequest]:
        return self.specs.collect_requests(edition_id, project_id)

    def render_all(self, requests: list[VisualRequest], out_dir: Path) -> dict:
        return self.renderer.render_all(requests, out_dir)
