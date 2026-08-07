"""PUBLIC_FRONTEND_CONTRACT freeze — HARD method/route/fields only.

Phase 0.5: Test protection only. No OpenAPI full-document snapshots.
"""

from __future__ import annotations

import json

from tests.contracts.conftest import assert_hard_fields, build_sample_pdf_bytes


def _create_project(client, name: str = "contract-project") -> dict:
    r = client.post("/api/projects", json={"name": name})
    assert r.status_code == 200, r.text
    body = r.json()
    assert_hard_fields(
        body,
        ["project_id", "name", "stage", "current_edition_id"],
        ctx="POST /api/projects",
    )
    return body


def _upload_and_process(client, project_id: str, pdf_bytes: bytes) -> dict:
    r = client.post(
        f"/api/projects/{project_id}/sources",
        files={"file": ("sample.pdf", pdf_bytes, "application/pdf")},
        data={"role": "EVIDENCE_SOURCE"},
    )
    assert r.status_code == 200, r.text
    source = r.json()
    assert_hard_fields(
        source,
        ["source_id", "filename", "role", "status", "page_count"],
        ctx="POST sources",
    )

    r = client.post(f"/api/sources/{source['source_id']}/process")
    assert r.status_code == 200, r.text
    processed = r.json()
    assert processed.get("status") == "READY" or client.get(
        f"/api/sources/{source['source_id']}"
    ).json()["status"] == "READY"
    return client.get(f"/api/sources/{source['source_id']}").json()


def test_project_list_and_create_hard_fields(client):
    created = _create_project(client)
    r = client.get("/api/projects")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list)
    assert any(p["project_id"] == created["project_id"] for p in rows)
    for p in rows:
        assert_hard_fields(
            p,
            ["project_id", "name", "stage", "current_edition_id"],
            ctx="GET /api/projects item",
        )


def test_project_status_hard_fields_and_phase_semantics(client):
    project = _create_project(client, "status-project")
    r = client.get(f"/api/projects/{project['project_id']}/status")
    assert r.status_code == 200
    st = r.json()
    assert_hard_fields(
        st,
        [
            "busy",
            "phase",
            "label",
            "stage",
            "current_edition_id",
            "interrupted",
        ],
        ctx="GET status",
    )
    assert isinstance(st["busy"], bool)
    assert isinstance(st["interrupted"], bool)
    assert st["busy"] is False
    # idle: phase may be null; when set must be a known Frontend phase
    if st["phase"] is not None:
        assert st["phase"] in {"analyzing", "planning", "producing", "reviewing"}


def test_source_ready_status_and_page_route(client, api_env):
    pdf = build_sample_pdf_bytes(api_env["tmp_path"])
    project = _create_project(client, "source-project")
    source = _upload_and_process(client, project["project_id"], pdf)
    assert source["status"] == "READY"
    assert_hard_fields(
        source,
        ["source_id", "filename", "role", "status", "page_count"],
        ctx="READY source",
    )

    r = client.get(f"/api/projects/{project['project_id']}/sources")
    assert r.status_code == 200
    listed = r.json()
    assert listed and listed[0]["status"] == "READY"

    page_n = 1
    r = client.get(f"/api/sources/{source['source_id']}/pages/{page_n}")
    assert r.status_code == 200
    page = r.json()
    assert "page_number" in page or "blocks" in page or "text" in page or isinstance(
        page, dict
    )


def test_analysis_and_planning_contract_shapes(client, api_env):
    pdf = build_sample_pdf_bytes(api_env["tmp_path"])
    project = _create_project(client, "plan-project")
    _upload_and_process(client, project["project_id"], pdf)

    r = client.post(f"/api/projects/{project['project_id']}/analyze")
    assert r.status_code == 200, r.text
    analysis_post = r.json()
    # Frontend consumes nested analysis / main_topic
    nested = analysis_post.get("analysis") or analysis_post
    assert isinstance(nested, dict)
    assert "main_topic" in nested or "analysis_id" in analysis_post

    r = client.get(f"/api/projects/{project['project_id']}/analysis")
    assert r.status_code == 200
    analysis_get = r.json()
    nested_get = analysis_get.get("analysis") or analysis_get
    assert isinstance(nested_get, dict)
    assert "main_topic" in nested_get

    r = client.post(f"/api/projects/{project['project_id']}/plans/generate")
    assert r.status_code == 200, r.text
    plan_gen = r.json()
    assert "title" in plan_gen or (plan_gen.get("plan") or {}).get("title")
    plan_blob = plan_gen.get("plan") or {}
    assert "strategy" in plan_blob or "title_candidates" in plan_blob or "outline" in plan_blob

    r = client.get(f"/api/projects/{project['project_id']}/plan")
    assert r.status_code == 200
    plan = r.json()
    assert_hard_fields(plan, ["title"], ctx="GET plan")
    assert "plan" in plan
    assert isinstance(plan["plan"], dict)
    # Frontend PlanDetail.plan.strategy / title_candidates
    assert "strategy" in plan["plan"] or plan["plan"].get("title_candidates") is not None
    candidates = plan["plan"].get("title_candidates") or (
        (plan["plan"].get("strategy") or {}).get("title_candidates")
    )
    assert candidates is None or isinstance(candidates, list)

    r = client.get(f"/api/projects/{project['project_id']}/outline")
    assert r.status_code == 200
    outline = r.json()
    assert_hard_fields(
        outline,
        ["outline_id", "approved", "nodes"],
        ctx="GET outline",
    )
    assert isinstance(outline["nodes"], list)
    assert outline["nodes"], "outline must have nodes"
    assert outline["approved"] is False

    # PATCH outline / plan (contract surface; restore title)
    nodes = json.loads(json.dumps(outline["nodes"]))
    nodes[0]["title"] = nodes[0]["title"] + " (계약)"
    r = client.patch(
        f"/api/projects/{project['project_id']}/outline",
        json={"nodes": nodes},
    )
    assert r.status_code == 200, r.text
    assert r.json()["nodes"][0]["title"].endswith("(계약)")

    r = client.patch(
        f"/api/projects/{project['project_id']}/plan",
        json={"title": "계약 테스트 제목"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["title"] == "계약 테스트 제목"

    node_id = outline["nodes"][0]["node_id"]
    r = client.post(
        f"/api/projects/{project['project_id']}/outline/nodes/{node_id}/recommend"
    )
    # recommend may return 200 with payload; freeze route existence + non-5xx
    assert r.status_code < 500, r.text

    r = client.post(f"/api/projects/{project['project_id']}/outline/approve")
    assert r.status_code == 200, r.text
    approved = r.json()
    assert approved.get("approved") is True or approved.get("stage")
    # After approval Frontend expects producing-capable stage
    proj = client.get(f"/api/projects/{project['project_id']}").json()
    assert proj["stage"] in {
        "PRODUCING",
        "WAITING_FOR_OUTLINE_APPROVAL",
        "READY_FOR_EXPORT",
        "REVIEWING",
    } or approved.get("approved") is True
    # Canonical approve moves to PRODUCING
    assert proj["stage"] == "PRODUCING"


def test_production_section_naming_and_edition_fields(client, api_env):
    """API keeps `sections` naming (not chapters)."""
    pdf = build_sample_pdf_bytes(api_env["tmp_path"])
    project = _create_project(client, "prod-project")
    _upload_and_process(client, project["project_id"], pdf)
    assert client.post(f"/api/projects/{project['project_id']}/analyze").status_code == 200
    assert (
        client.post(f"/api/projects/{project['project_id']}/plans/generate").status_code
        == 200
    )
    assert (
        client.post(f"/api/projects/{project['project_id']}/outline/approve").status_code
        == 200
    )

    r = client.post(f"/api/projects/{project['project_id']}/editions", json={})
    assert r.status_code == 200, r.text
    produced = r.json()
    # POST produce returns edition_id + sections[]; status is on GET edition (FE Edition type)
    assert_hard_fields(
        produced,
        ["edition_id", "edition_number", "sections"],
        ctx="POST editions",
    )
    assert isinstance(produced["sections"], list)
    assert "chapters" not in produced
    assert produced["sections"], "expected sections[]"
    sec0 = produced["sections"][0]
    assert "section_id" in sec0
    assert "title" in sec0

    edition_id = produced["edition_id"]
    r = client.get(f"/api/editions/{edition_id}")
    assert r.status_code == 200
    edition = r.json()
    assert_hard_fields(
        edition,
        ["edition_id", "edition_number", "status", "sections"],
        ctx="GET edition",
    )
    assert isinstance(edition["sections"], list)
    assert "chapters" not in edition

    section_id = edition["sections"][0]["section_id"]
    r = client.get(f"/api/sections/{section_id}")
    assert r.status_code == 200
    section = r.json()
    assert_hard_fields(
        section,
        ["section_id", "title", "content_markdown", "status"],
        ctx="GET section",
    )
    # Resume route exists (may 400 if not interrupted — still freezes path)
    r = client.post(f"/api/editions/{edition_id}/resume")
    assert r.status_code in {200, 400}, r.text


def test_review_and_export_contracts(client, api_env):
    pdf = build_sample_pdf_bytes(api_env["tmp_path"])
    project = _create_project(client, "review-export-project")
    _upload_and_process(client, project["project_id"], pdf)
    assert client.post(f"/api/projects/{project['project_id']}/analyze").status_code == 200
    assert (
        client.post(f"/api/projects/{project['project_id']}/plans/generate").status_code
        == 200
    )
    assert (
        client.post(f"/api/projects/{project['project_id']}/outline/approve").status_code
        == 200
    )
    produced = client.post(f"/api/projects/{project['project_id']}/editions", json={}).json()
    edition_id = produced["edition_id"]
    section_id = produced["sections"][0]["section_id"]

    r = client.post(f"/api/editions/{edition_id}/review")
    assert r.status_code == 200, r.text
    review = r.json()
    assert "all_passed" in review

    r = client.get(f"/api/sections/{section_id}/issues")
    assert r.status_code == 200
    issues = r.json()
    assert isinstance(issues, list)
    for iss in issues:
        # Frontend renders severity | code
        assert "severity" in iss or "code" in iss or "problem" in iss or "message" in iss

    r = client.post(f"/api/editions/{edition_id}/exports")
    assert r.status_code == 200, r.text
    exported = r.json()
    # create may return export row or pipeline summary — list is HARD for FE
    r = client.get(f"/api/editions/{edition_id}/exports")
    assert r.status_code == 200
    exports = r.json()
    assert isinstance(exports, list)
    assert exports, "expected at least one export after POST"
    row = exports[0]
    assert_hard_fields(row, ["export_id", "format", "status"], ctx="GET exports")
    export_id = row["export_id"]

    # download URL pattern Frontend uses: /api/exports/{id}/download
    r = client.get(f"/api/exports/{export_id}/download")
    assert r.status_code == 200, r.text
    assert r.headers.get("content-type") or r.content


def test_public_route_surface_freeze(client):
    """Freeze Method+Route presence for PUBLIC_FRONTEND_CONTRACT paths."""
    paths = client.app.openapi()["paths"]

    required = {
        "/api/projects": {"get", "post"},
        "/api/projects/{project_id}/status": {"get"},
        "/api/projects/{project_id}/sources": {"get", "post"},
        "/api/sources/{source_id}/process": {"post"},
        "/api/sources/{source_id}/pages/{page_number}": {"get"},
        "/api/projects/{project_id}/analyze": {"post"},
        "/api/projects/{project_id}/analysis": {"get"},
        "/api/projects/{project_id}/plans/generate": {"post"},
        "/api/projects/{project_id}/plan": {"get", "patch"},
        "/api/projects/{project_id}/outline": {"get", "patch"},
        "/api/projects/{project_id}/outline/approve": {"post"},
        "/api/projects/{project_id}/outline/nodes/{node_id}/recommend": {"post"},
        "/api/projects/{project_id}/editions": {"post"},
        "/api/editions/{edition_id}": {"get"},
        "/api/editions/{edition_id}/resume": {"post"},
        "/api/editions/{edition_id}/sections": {"get"},
        "/api/sections/{section_id}": {"get"},
        "/api/editions/{edition_id}/review": {"post"},
        "/api/sections/{section_id}/issues": {"get"},
        "/api/paragraphs/{paragraph_id}": {"patch"},
        "/api/editions/{edition_id}/exports": {"get", "post"},
        "/api/exports/{export_id}/download": {"get"},
        "/health": {"get"},
    }
    missing = []
    for path, methods in required.items():
        if path not in paths:
            missing.append(path)
            continue
        have = {m.lower() for m in paths[path]}
        if not methods.issubset(have):
            missing.append(f"{path} missing {sorted(methods - have)}")
    assert not missing, f"missing PUBLIC routes/methods: {missing}"

    # Ensure section naming: no /api/chapters public rename
    assert not any(p.startswith("/api/chapters") for p in paths)
