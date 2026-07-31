import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Claim, Edition, Section } from "../types";
import { useWorkspace } from "../workspace";

export default function ProductionPage() {
  const { projectId, editionId, setEditionId } = useWorkspace();
  const [edition, setEdition] = useState<Edition | null>(null);
  const [sectionId, setSectionId] = useState("");
  const [section, setSection] = useState<Section | null>(null);
  const [issues, setIssues] = useState<Array<Record<string, string>>>([]);
  const [claimLoc, setClaimLoc] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function loadEdition(id: string) {
    const ed = await api.getEdition(id);
    setEdition(ed);
    setEditionId(ed.edition_id);
    const first = ed.sections?.[0];
    if (first) setSectionId(first.section_id);
  }

  useEffect(() => {
    if (!editionId) {
      setEdition(null);
      return;
    }
    loadEdition(editionId).catch((e) => setErr(String(e.message || e)));
  }, [editionId]);

  useEffect(() => {
    if (!sectionId) {
      setSection(null);
      setIssues([]);
      return;
    }
    api
      .getSection(sectionId)
      .then(setSection)
      .catch(() => setSection(null));
    api
      .sectionIssues(sectionId)
      .then(setIssues)
      .catch(() => setIssues([]));
    setClaimLoc(null);
  }, [sectionId]);

  async function produce() {
    if (!projectId) return;
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const res = await api.produce(projectId);
      const id = String(
        (res as { edition_id?: string }).edition_id ||
          (res as { edition?: { edition_id?: string } }).edition?.edition_id ||
          "",
      );
      if (id) {
        await loadEdition(id);
        setMsg(`작성 완료: ${id}`);
      } else {
        setMsg("작성 완료");
      }
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  }

  async function review() {
    if (!editionId) return;
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const res = await api.reviewEdition(editionId);
      setMsg(
        `검토 완료 · all_passed=${String((res as { all_passed?: boolean }).all_passed)}`,
      );
      await loadEdition(editionId);
      if (sectionId) {
        setIssues(await api.sectionIssues(sectionId));
        setSection(await api.getSection(sectionId));
      }
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  }

  async function showClaim(c: Claim) {
    try {
      const loc = await api.claimLocations(c.claim_id);
      setClaimLoc(loc);
    } catch (e) {
      setErr(String((e as Error).message || e));
    }
  }

  if (!projectId) {
    return (
      <div>
        <h1 className="page-title">작성·검토</h1>
        <p className="page-desc">먼저 프로젝트를 선택하세요.</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="page-title">작성·검토</h1>
      <p className="page-desc">
        Edition {edition?.edition_number ?? "—"} · {editionId || "없음"} ·{" "}
        <span className="badge">{edition?.status || "—"}</span>
      </p>

      <div className="row" style={{ marginBottom: "0.9rem" }}>
        <button type="button" disabled={busy} onClick={produce}>
          작성 실행
        </button>
        <button type="button" className="secondary" disabled={busy || !editionId} onClick={review}>
          검토 실행
        </button>
        {msg && <span className="okmsg">{msg}</span>}
        {err && <span className="err">{err}</span>}
      </div>

      <div className="panes-3">
        <section className="pane">
          <h2 className="pane-title">목차 진행</h2>
          <div className="stack">
            {(edition?.sections || []).map((s) => (
              <div
                key={s.section_id}
                className={`tree-item ${sectionId === s.section_id ? "active" : ""}`}
                onClick={() => setSectionId(s.section_id)}
              >
                <div>{s.title}</div>
                <div className="muted" style={{ fontSize: "0.78rem" }}>
                  <span className="badge">{s.status || "—"}</span>
                </div>
              </div>
            ))}
            {!edition?.sections?.length && (
              <div className="muted">작성을 실행하세요</div>
            )}
          </div>
        </section>

        <section className="pane">
          <h2 className="pane-title">본문</h2>
          {section ? (
            <>
              <div className="muted" style={{ marginBottom: "0.5rem" }}>
                {section.objective}
              </div>
              <pre className="body">{section.content_markdown || "(비어 있음)"}</pre>
            </>
          ) : (
            <div className="muted">섹션을 선택하세요</div>
          )}
        </section>

        <section className="pane">
          <h2 className="pane-title">근거·검토</h2>
          <div className="stack">
            <div>
              <div className="muted" style={{ fontSize: "0.8rem" }}>
                Claims
              </div>
              <ul className="extract-list">
                {(section?.claims || []).map((c) => (
                  <li key={c.claim_id}>
                    <button
                      type="button"
                      className="secondary"
                      style={{ marginRight: "0.35rem", padding: "0.2rem 0.45rem" }}
                      onClick={() => showClaim(c)}
                    >
                      원문
                    </button>
                    {c.statement}
                    <div className="muted mono" style={{ fontSize: "0.75rem" }}>
                      {c.verification_status || ""} · {(c.evidence || []).length} evidence
                    </div>
                  </li>
                ))}
                {!section?.claims?.length && <li className="muted">없음</li>}
              </ul>
            </div>
            <div>
              <div className="muted" style={{ fontSize: "0.8rem" }}>
                Issues
              </div>
              <ul className="extract-list">
                {issues.map((iss, i) => (
                  <li key={i}>
                    <span className="badge bad">{iss.severity || iss.code || "issue"}</span>{" "}
                    {iss.message || iss.detail || JSON.stringify(iss)}
                  </li>
                ))}
                {!issues.length && <li className="muted">이슈 없음</li>}
              </ul>
            </div>
            {claimLoc && (
              <div>
                <div className="muted" style={{ fontSize: "0.8rem" }}>
                  Claim 원문 위치
                </div>
                <pre className="body" style={{ maxHeight: "24vh" }}>
                  {JSON.stringify(claimLoc, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
