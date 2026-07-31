import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Source } from "../types";
import { useWorkspace } from "../workspace";

type PageInfo = {
  page_number: number;
  page_type?: string;
  text?: string;
  blocks?: Array<{
    block_id: string;
    block_type?: string;
    text?: string;
    bbox?: number[] | null;
  }>;
  metrics?: Array<Record<string, unknown>>;
  structure?: Array<{
    fact_kind?: string;
    title?: string;
    confidence?: number;
    verification_status?: string;
    payload?: {
      nodes?: Array<{ label?: string; group?: string | null }>;
      edges?: Array<{
        from_node_id?: string;
        to_node_id?: string;
        label?: string | null;
      }>;
      groups?: string[];
    };
  }>;
};

export default function SourcesPage() {
  const { projectId } = useWorkspace();
  const [sources, setSources] = useState<Source[]>([]);
  const [selected, setSelected] = useState<Source | null>(null);
  const [pageNum, setPageNum] = useState(1);
  const [page, setPage] = useState<PageInfo | null>(null);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploadRole, setUploadRole] = useState<
    "EVIDENCE_SOURCE" | "PREVIOUS_EDITION" | "FORMAT_REFERENCE"
  >("EVIDENCE_SOURCE");

  async function loadSources() {
    if (!projectId) return;
    const list = await api.listSources(projectId);
    setSources(list);
    if (selected) {
      const fresh = list.find((s) => s.source_id === selected.source_id);
      setSelected(fresh || list[0] || null);
    } else if (list[0]) {
      setSelected(list[0]);
    }
  }

  useEffect(() => {
    if (!projectId) return;
    loadSources().catch((e) => setErr(String(e.message || e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  useEffect(() => {
    if (!selected) {
      setPage(null);
      return;
    }
    setPageNum(1);
  }, [selected?.source_id]);

  useEffect(() => {
    if (!selected || selected.status !== "READY") {
      setPage(null);
      return;
    }
    api
      .getPage(selected.source_id, pageNum)
      .then((p) => setPage(p as PageInfo))
      .catch(() => setPage(null));
  }, [selected, pageNum]);

  async function onUpload(file: File | null) {
    if (!file || !projectId) return;
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const src = await api.uploadSource(projectId, file, uploadRole);
      setMsg(`업로드: ${src.source_id}`);
      await loadSources();
      setSelected(src);
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  }

  async function process(src: Source) {
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      await api.processSource(src.source_id);
      setMsg(`처리 완료: ${src.filename}`);
      await loadSources();
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  }

  if (!projectId) {
    return (
      <div>
        <h1 className="page-title">자료</h1>
        <p className="page-desc">먼저 프로젝트를 선택하세요.</p>
      </div>
    );
  }

  const maxPage = selected?.page_count || page?.page_number || 1;

  return (
    <div>
      <h1 className="page-title">자료</h1>
      <p className="page-desc">업로드 · 파싱 · 페이지별 추출 결과를 확인합니다.</p>

      <div className="row" style={{ marginBottom: "0.9rem" }}>
        <label className="field" style={{ margin: 0 }}>
          <span className="muted" style={{ fontSize: "0.75rem" }}>
            역할
          </span>
          <select
            value={uploadRole}
            disabled={busy}
            onChange={(e) =>
              setUploadRole(
                e.target.value as
                  | "EVIDENCE_SOURCE"
                  | "PREVIOUS_EDITION"
                  | "FORMAT_REFERENCE",
              )
            }
          >
            <option value="EVIDENCE_SOURCE">사실 근거 (EVIDENCE)</option>
            <option value="PREVIOUS_EDITION">이전판 참고 (스타일만)</option>
            <option value="FORMAT_REFERENCE">형식 참고 (양식만)</option>
          </select>
        </label>
        <label className="badge" style={{ cursor: "pointer" }}>
          파일 업로드
          <input
            type="file"
            hidden
            disabled={busy}
            onChange={(e) => onUpload(e.target.files?.[0] || null)}
          />
        </label>
        {msg && <span className="okmsg">{msg}</span>}
        {err && <span className="err">{err}</span>}
      </div>

      <div className="panes-3">
        <section className="pane">
          <h2 className="pane-title">목록</h2>
          <div className="stack">
            {sources.map((s) => (
              <div
                key={s.source_id}
                className={`tree-item ${selected?.source_id === s.source_id ? "active" : ""}`}
                onClick={() => setSelected(s)}
              >
                <div>{s.filename}</div>
                <div className="muted" style={{ fontSize: "0.8rem" }}>
                  {s.role} · <span className="badge">{s.status}</span>
                  {s.page_count != null ? ` · ${s.page_count}p` : ""}
                </div>
                {s.status !== "READY" && (
                  <button
                    type="button"
                    className="secondary"
                    style={{ marginTop: "0.4rem" }}
                    disabled={busy}
                    onClick={(e) => {
                      e.stopPropagation();
                      process(s);
                    }}
                  >
                    처리
                  </button>
                )}
              </div>
            ))}
            {!sources.length && <div className="muted">자료 없음</div>}
          </div>
        </section>

        <section className="pane">
          <h2 className="pane-title">페이지</h2>
          {!selected && <div className="muted">자료를 선택하세요</div>}
          {selected && selected.status !== "READY" && (
            <div className="muted">처리 후 페이지를 볼 수 있습니다.</div>
          )}
          {selected && selected.status === "READY" && (
            <>
              <div className="row" style={{ marginBottom: "0.6rem" }}>
                <button
                  type="button"
                  className="secondary"
                  disabled={pageNum <= 1}
                  onClick={() => setPageNum((n) => Math.max(1, n - 1))}
                >
                  ←
                </button>
                <span className="mono">
                  {pageNum} / {maxPage}
                </span>
                <button
                  type="button"
                  className="secondary"
                  disabled={pageNum >= maxPage}
                  onClick={() => setPageNum((n) => n + 1)}
                >
                  →
                </button>
                {page?.page_type && <span className="badge">{page.page_type}</span>}
              </div>
              <pre className="body">{page?.text || "(텍스트 없음)"}</pre>
            </>
          )}
        </section>

        <section className="pane">
          <h2 className="pane-title">추출</h2>
          {!page && <div className="muted">페이지를 불러오세요</div>}
          {page && (
            <div className="stack">
              <div>
                <div className="muted" style={{ fontSize: "0.8rem" }}>
                  블록 {page.blocks?.length ?? 0}
                </div>
                <ul className="extract-list">
                  {(page.blocks || []).slice(0, 40).map((b) => (
                    <li key={b.block_id}>
                      <span className="badge">{b.block_type || "TEXT"}</span>{" "}
                      {(b.text || "").slice(0, 120)}
                      {b.bbox ? (
                        <span className="mono muted"> · bbox</span>
                      ) : null}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="muted" style={{ fontSize: "0.8rem" }}>
                  수치 {page.metrics?.length ?? 0}
                </div>
                <ul className="extract-list">
                  {(page.metrics || []).map((m, i) => (
                    <li key={i} className="mono">
                      {String(m.name || "metric")}: {formatMetricDisplay(m)}
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <div className="muted" style={{ fontSize: "0.8rem" }}>
                  구조 {page.structure?.length ?? 0}
                </div>
                <ul className="extract-list">
                  {(page.structure || []).map((s, i) => {
                    const p = s.payload || {};
                    const nodes = (p.nodes || []) as Array<{
                      node_id?: string;
                      label?: string;
                      group?: string | null;
                    }>;
                    const edges = p.edges || [];
                    const groups = p.groups || [];
                    const labelOf = (id?: string) =>
                      nodes.find((n) => n.node_id === id)?.label || id || "?";
                    return (
                      <li key={i}>
                        <span className="badge">{s.fact_kind || "STRUCT"}</span>{" "}
                        {s.title || "diagram"}
                        <span className="mono muted">
                          {" "}
                          · n{nodes.length}/e{edges.length}
                          {s.verification_status
                            ? ` · ${s.verification_status}`
                            : ""}
                        </span>
                        {groups.length > 0 && (
                          <div className="muted" style={{ fontSize: "0.75rem" }}>
                            그룹: {groups.join(", ")}
                          </div>
                        )}
                        <div className="muted" style={{ fontSize: "0.75rem" }}>
                          노드:{" "}
                          {nodes
                            .slice(0, 12)
                            .map((n) =>
                              n.group ? `${n.label}(${n.group})` : n.label
                            )
                            .join(" · ")}
                        </div>
                        {edges.length > 0 && (
                          <div className="muted" style={{ fontSize: "0.75rem" }}>
                            연결:{" "}
                            {edges
                              .slice(0, 10)
                              .map((e) => {
                                const a = labelOf(e.from_node_id);
                                const b = labelOf(e.to_node_id);
                                return e.label
                                  ? `${a} -[${e.label}]→ ${b}`
                                  : `${a} → ${b}`;
                              })
                              .join(" · ")}
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

/** Align with backend metric_facts (change or absolute result_value). */
function formatMetricDisplay(m: Record<string, unknown>): string {
  const unit = String(m.change_unit || "");
  const change = m.change_value;
  if (change != null && change !== "") {
    const dir = String(m.direction || "");
    const sign =
      dir === "DECREASE" ? "−" : dir === "INCREASE" ? "+" : "";
    const label =
      dir === "DECREASE" ? " 감소" : dir === "INCREASE" ? " 증가" : "";
    return `${sign}${change}${unit}${label}`.trim();
  }
  if (m.result_value != null && m.result_value !== "") {
    return `${m.result_value}${unit}`;
  }
  if (m.baseline_value != null && m.baseline_value !== "") {
    return `${m.baseline_value}${unit}`;
  }
  return "—";
}
