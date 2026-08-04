import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Claim, Edition, Paragraph, Section } from "../types";
import { useWorkspace } from "../workspace";

type JobPhase = "producing" | "reviewing" | "analyzing" | "planning" | null;

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
  const [jobPhase, setJobPhase] = useState<JobPhase>(null);
  const [jobLabel, setJobLabel] = useState("");
  const [interrupted, setInterrupted] = useState(false);
  const localRun = useRef(false);
  const resumeRun = useRef(false);
  const sectionIdRef = useRef("");

  const working = busy || jobPhase === "producing" || jobPhase === "reviewing";

  const canResume = (() => {
    if (!editionId || !edition) return false;
    const st = (edition.status || "").toUpperCase();
    if (st && !["PRODUCING", "DRAFT", "IN_REVIEW"].includes(st) && !interrupted) {
      return false;
    }
    const secs = edition.sections || [];
    if (!secs.length) return interrupted;
    const incomplete = secs.some((s) => {
      const ss = (s.status || "").toUpperCase();
      if (["RESEARCHING", "WRITING", "REVISING", "PENDING", "FAILED"].includes(ss))
        return true;
      return !(s.content_markdown || "").trim() || (s.content_markdown || "").trim().length < 40;
    });
    // Missing later outline chapters: fewer sections than expected still resumable
    return interrupted || incomplete;
  })();

  useEffect(() => {
    sectionIdRef.current = sectionId;
  }, [sectionId]);

  async function loadEdition(id: string) {
    const ed = await api.getEdition(id);
    setEdition(ed);
    setEditionId(ed.edition_id);
    const prefer = sectionIdRef.current;
    const keep =
      prefer && ed.sections?.some((s) => s.section_id === prefer) ? prefer : "";
    if (keep) {
      setSectionId(keep);
    } else {
      const first = ed.sections?.[0];
      if (first) setSectionId(first.section_id);
    }
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

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    let timer: number | undefined;
    let sawBusy = false;

    async function poll() {
      try {
        const st = await api.getStatus(projectId!);
        if (cancelled) return;
        const phase = (st.phase || null) as JobPhase;
        const running =
          !!(st.busy && (phase === "producing" || phase === "reviewing"));
        setInterrupted(!!st.interrupted && !running);
        if (running) {
          sawBusy = true;
          setJobPhase(phase);
          setJobLabel(st.label || "");
          if (st.current_edition_id && st.current_edition_id !== editionId) {
            setEditionId(st.current_edition_id);
          } else if (st.current_edition_id) {
            await loadEdition(st.current_edition_id).catch(() => null);
          }
        } else if (!localRun.current) {
          setJobPhase(null);
          setJobLabel("");
          if (sawBusy) {
            sawBusy = false;
            const eid = st.current_edition_id || editionId;
            if (eid) await loadEdition(eid).catch(() => null);
            setMsg(
              phase === "reviewing" || st.stage === "READY_FOR_EXPORT"
                ? "작성·검토 완료"
                : "작성 작업 완료",
            );
            setBusy(false);
          }
        }
      } catch {
        /* ignore */
      }
      if (!cancelled) timer = window.setTimeout(poll, 2500);
    }

    poll();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [projectId]);

  async function produce() {
    if (!projectId || working) return;
    localRun.current = true;
    resumeRun.current = false;
    setBusy(true);
    setJobPhase("producing");
    setJobLabel("보고서 작성 중 (Ollama) — 장 수에 따라 오래 걸릴 수 있습니다");
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
      setInterrupted(false);
      setJobPhase(null);
      setJobLabel("");
    } catch (e) {
      const text = String((e as Error).message || e);
      if (/already running/i.test(text)) {
        setMsg("이미 작성/검토 중입니다. 완료되면 자동으로 갱신됩니다.");
      } else {
        setErr(text);
        setJobPhase(null);
        setJobLabel("");
      }
    } finally {
      localRun.current = false;
      setBusy(false);
    }
  }

  async function resumeProduce() {
    if (!editionId || working) return;
    localRun.current = true;
    resumeRun.current = true;
    setBusy(true);
    setJobPhase("producing");
    setJobLabel(
      "이어쓰기 중 — 완성된 장은 유지하고 남은 장만 작성합니다 (Ollama)",
    );
    setErr("");
    setMsg("");
    setInterrupted(false);
    try {
      const res = await api.resumeProduce(editionId);
      const id = String((res as { edition_id?: string }).edition_id || editionId);
      await loadEdition(id);
      const skipped = (res as { skipped?: number }).skipped;
      const rewritten = (res as { rewritten?: number }).rewritten;
      setMsg(
        `이어쓰기 완료: ${id}` +
          (skipped != null || rewritten != null
            ? ` (유지 ${skipped ?? "—"} · 작성 ${rewritten ?? "—"})`
            : ""),
      );
      setJobPhase(null);
      setJobLabel("");
    } catch (e) {
      const text = String((e as Error).message || e);
      if (/already running/i.test(text)) {
        setMsg("이미 작성/검토 중입니다. 완료되면 자동으로 갱신됩니다.");
      } else {
        setErr(text);
        setJobPhase(null);
        setJobLabel("");
        setInterrupted(true);
      }
    } finally {
      localRun.current = false;
      setBusy(false);
    }
  }

  async function review() {
    if (!editionId || working) return;
    localRun.current = true;
    setBusy(true);
    setJobPhase("reviewing");
    setJobLabel("검토 중 (Ollama) — 수 분 걸릴 수 있습니다");
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
      setJobPhase(null);
      setJobLabel("");
    } catch (e) {
      const text = String((e as Error).message || e);
      if (/already running/i.test(text)) {
        setMsg("이미 작업 중입니다. 완료되면 자동으로 갱신됩니다.");
      } else {
        setErr(text);
        setJobPhase(null);
        setJobLabel("");
      }
    } finally {
      localRun.current = false;
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

  async function toggleParagraphLock(p: Paragraph) {
    if (!sectionId) return;
    try {
      const next = p.edit_state === "USER_LOCKED" ? "AI_EDITABLE" : "USER_LOCKED";
      await api.patchParagraph(p.paragraph_id, { edit_state: next });
      const latest = await api.getSection(sectionId);
      setSection(latest);
      setMsg(next === "USER_LOCKED" ? "문단 잠금 적용" : "문단 잠금 해제");
      setErr("");
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

  const bannerTitle =
    jobPhase === "reviewing" ? "검토 중" : jobPhase === "producing" ? "작성 중" : "작업 중";

  return (
    <div>
      <h1 className="page-title">작성·검토</h1>
      <p className="page-desc">
        Edition {edition?.edition_number ?? "—"} · {editionId || "없음"} ·{" "}
        <span className="badge">{edition?.status || "—"}</span>
      </p>

      <div className="row" style={{ marginBottom: "0.9rem" }}>
        <button type="button" disabled={working} onClick={produce}>
          {jobPhase === "producing" && !resumeRun.current
            ? "작성 중…"
            : "작성 실행"}
        </button>
        <button
          type="button"
          disabled={working || !canResume}
          onClick={resumeProduce}
          title="완성된 장은 유지하고 남은 장만 이어서 작성"
        >
          {jobPhase === "producing" && resumeRun.current
            ? "이어쓰는 중…"
            : "이어쓰기"}
        </button>
        <button
          type="button"
          className="secondary"
          disabled={working || !editionId}
          onClick={review}
        >
          {jobPhase === "reviewing" ? "검토 중…" : "검토 실행"}
        </button>
        {msg && !working && <span className="okmsg">{msg}</span>}
        {err && <span className="err">{err}</span>}
      </div>

      {interrupted && !working && (
        <div className="progress-banner" role="status" style={{ opacity: 0.95 }}>
          <span className="progress-dot" aria-hidden />
          <div>
            <strong>이전 작성 중단됨</strong>
            <div className="muted" style={{ marginTop: "0.15rem" }}>
              「이어쓰기」로 완성된 장을 유지한 채 이어서 작성하세요. 「작성 실행」은
              새 Edition을 처음부터 만듭니다.
            </div>
          </div>
        </div>
      )}

      {working && (
        <div className="progress-banner" role="status" aria-live="polite">
          <span className="progress-dot" aria-hidden />
          <div>
            <strong>{bannerTitle}</strong>
            <div className="muted" style={{ marginTop: "0.15rem" }}>
              {jobLabel ||
                "Ollama로 장별 근거 수집·작성·검토 중입니다. 다른 메뉴로 이동해도 계속 실행됩니다."}
            </div>
          </div>
        </div>
      )}

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
              <div className="muted">
                {working ? "작성 시작됨 — 장이 하나씩 채워집니다" : "작성을 실행하세요"}
              </div>
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
              {!!section.paragraphs?.length && (
                <div style={{ marginTop: "0.6rem" }}>
                  <div className="muted" style={{ fontSize: "0.8rem", marginBottom: "0.3rem" }}>
                    문단 잠금
                  </div>
                  <ul className="extract-list">
                    {section.paragraphs.map((p) => (
                      <li key={p.paragraph_id}>
                        <button
                          type="button"
                          className="secondary"
                          style={{ marginRight: "0.35rem", padding: "0.2rem 0.45rem" }}
                          onClick={() => toggleParagraphLock(p)}
                        >
                          {p.edit_state === "USER_LOCKED" ? "잠금해제" : "잠금"}
                        </button>
                        <span className={`badge ${p.edit_state === "USER_LOCKED" ? "warn" : ""}`}>
                          {p.edit_state}
                        </span>{" "}
                        <span className="mono" style={{ fontSize: "0.72rem" }}>
                          {p.paragraph_id}
                        </span>
                        <div className="muted" style={{ fontSize: "0.78rem" }}>
                          {(p.text || "").slice(0, 120)}
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
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
