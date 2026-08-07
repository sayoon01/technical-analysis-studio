"""Status / polling contract freeze (Frontend strongest dependency).

Protects busy / phase / interrupted / "already running" semantics.
"""

from __future__ import annotations

from tests.contracts.conftest import HARD_PHASES, assert_hard_fields, build_sample_pdf_bytes


def test_idle_status_busy_false_triggers_frontend_reload_semantics(client):
    project = client.post("/api/projects", json={"name": "poll-idle"}).json()
    st = client.get(f"/api/projects/{project['project_id']}/status").json()
    assert_hard_fields(
        st,
        ["busy", "phase", "label", "stage", "current_edition_id", "interrupted"],
        ctx="idle status",
    )
    assert st["busy"] is False
    assert st["interrupted"] is False


def test_busy_true_when_job_phase_set(client):
    from backend.services.job_status import set_job

    project = client.post("/api/projects", json={"name": "poll-busy"}).json()
    pid = project["project_id"]
    set_job(pid, "analyzing")
    try:
        st = client.get(f"/api/projects/{pid}/status").json()
        assert st["busy"] is True
        assert st["phase"] == "analyzing"
        assert st["phase"] in HARD_PHASES
        assert isinstance(st["label"], str) and st["label"]
    finally:
        set_job(pid, None)

    st2 = client.get(f"/api/projects/{pid}/status").json()
    assert st2["busy"] is False


def test_phase_enum_values_for_known_jobs(client):
    from backend.services.job_status import set_job

    project = client.post("/api/projects", json={"name": "poll-phases"}).json()
    pid = project["project_id"]
    for phase in sorted(HARD_PHASES):
        set_job(pid, phase)
        st = client.get(f"/api/projects/{pid}/status").json()
        assert st["busy"] is True
        assert st["phase"] == phase
    set_job(pid, None)


def test_interrupted_when_producing_edition_stale_and_not_busy(client, api_env):
    """interrupted=true only when stage=PRODUCING, edition PRODUCING, busy=false."""
    from backend.storage.database import connect

    pdf = build_sample_pdf_bytes(api_env["tmp_path"])
    project = client.post("/api/projects", json={"name": "poll-interrupted"}).json()
    pid = project["project_id"]
    up = client.post(
        f"/api/projects/{pid}/sources",
        files={"file": ("sample.pdf", pdf, "application/pdf")},
        data={"role": "EVIDENCE_SOURCE"},
    ).json()
    assert client.post(f"/api/sources/{up['source_id']}/process").status_code == 200
    assert client.post(f"/api/projects/{pid}/analyze").status_code == 200
    assert client.post(f"/api/projects/{pid}/plans/generate").status_code == 200
    assert client.post(f"/api/projects/{pid}/outline/approve").status_code == 200

    produced = client.post(f"/api/projects/{pid}/editions", json={})
    assert produced.status_code == 200, produced.text
    edition_id = produced.json()["edition_id"]

    # Simulate crash after restart: edition still PRODUCING, no live in-process job
    conn = connect(api_env["db"])
    try:
        conn.execute(
            "UPDATE report_editions SET status = 'PRODUCING' WHERE edition_id = ?",
            (edition_id,),
        )
        conn.execute(
            "UPDATE projects SET stage = 'PRODUCING', current_edition_id = ? WHERE project_id = ?",
            (edition_id, pid),
        )
        conn.commit()
    finally:
        conn.close()

    from backend.api import deps
    from backend.services.job_status import set_job

    deps._local.conn = None
    set_job(pid, None)

    st = client.get(f"/api/projects/{pid}/status").json()
    assert st["busy"] is False
    assert st["interrupted"] is True
    assert st["current_edition_id"] == edition_id


def test_already_running_string_is_http_400_detail(client, api_env):
    """Frontend treats /already running/i as in-progress, not generic failure."""
    from backend.services.job_status import lock_for

    pdf = build_sample_pdf_bytes(api_env["tmp_path"])
    project = client.post("/api/projects", json={"name": "already-running"}).json()
    pid = project["project_id"]
    up = client.post(
        f"/api/projects/{pid}/sources",
        files={"file": ("sample.pdf", pdf, "application/pdf")},
        data={"role": "EVIDENCE_SOURCE"},
    ).json()
    assert client.post(f"/api/sources/{up['source_id']}/process").status_code == 200

    lock = lock_for(pid)
    assert lock.acquire(blocking=False)
    try:
        r = client.post(f"/api/projects/{pid}/analyze")
        assert r.status_code == 400, r.text
        detail = r.json().get("detail") or r.text
        assert "already running" in str(detail).lower()

        r2 = client.post(f"/api/projects/{pid}/plans/generate")
        assert r2.status_code == 400, r2.text
        assert "already running" in str(r2.json().get("detail") or r2.text).lower()
    finally:
        lock.release()
