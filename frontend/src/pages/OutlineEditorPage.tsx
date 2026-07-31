import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { Outline, OutlineNode } from "../types";
import { useWorkspace } from "../workspace";

type GenPhase = "analyzing" | "planning" | null;

export default function OutlineEditorPage() {
  const { projectId } = useWorkspace();
  const [outline, setOutline] = useState<Outline | null>(null);
  const [selectedId, setSelectedId] = useState("");
  const [nodes, setNodes] = useState<OutlineNode[]>([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [genPhase, setGenPhase] = useState<GenPhase>(null);
  const [genLabel, setGenLabel] = useState("");
  const localRun = useRef(false);

  const selected = nodes.find((n) => n.node_id === selectedId) || null;
  const generating = busy || !!genPhase;

  async function load() {
    if (!projectId) return;
    const o = await api.getOutline(projectId);
    setOutline(o);
    setNodes(o.nodes || []);
    if (o.nodes?.[0]) setSelectedId(o.nodes[0].node_id);
  }

  useEffect(() => {
    if (!projectId) return;
    load().catch(() => {
      setOutline(null);
      setNodes([]);
    });
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return;
    let cancelled = false;
    let timer: number | undefined;
    let sawBusy = false;

    async function poll() {
      try {
        const st = await api.getStatus(projectId!);
        if (cancelled) return;
        if (st.busy && st.phase) {
          sawBusy = true;
          setGenPhase(st.phase as GenPhase);
          setGenLabel(st.label || "");
        } else if (!localRun.current) {
          setGenPhase(null);
          setGenLabel("");
          if (sawBusy) {
            sawBusy = false;
            await load().catch(() => null);
            setMsg("목차 생성 완료");
          }
        }
      } catch {
        /* ignore poll errors */
      }
      if (!cancelled) timer = window.setTimeout(poll, 2000);
    }

    poll();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [projectId]);

  function updateSelected(patch: Partial<OutlineNode>) {
    if (!selected) return;
    setNodes((prev) =>
      prev.map((n) => (n.node_id === selected.node_id ? { ...n, ...patch } : n)),
    );
  }

  async function save() {
    if (!projectId) return;
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const o = await api.patchOutline(projectId, nodes);
      setOutline(o);
      setNodes(o.nodes || []);
      setMsg("저장됨");
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  }

  async function generate() {
    if (!projectId || generating) return;
    localRun.current = true;
    setBusy(true);
    setErr("");
    setMsg("");
    setGenPhase("analyzing");
    setGenLabel("자료 분석 중 (Ollama) — 수 분 걸릴 수 있습니다");
    try {
      try {
        await api.analyze(projectId);
      } catch (e) {
        const text = String((e as Error).message || e);
        if (/already running/i.test(text)) {
          setMsg("이미 생성 중입니다. 완료될 때까지 기다려 주세요.");
          return;
        }
        /* may already be analyzed — continue to plan */
      }
      setGenPhase("planning");
      setGenLabel("목차 생성 중 (Ollama) — 수 분 걸릴 수 있습니다");
      await api.generatePlan(projectId);
      await load();
      setMsg("목차 생성 완료");
      setGenPhase(null);
      setGenLabel("");
    } catch (e) {
      const text = String((e as Error).message || e);
      if (/already running/i.test(text)) {
        setMsg("이미 생성 중입니다. 완료될 때까지 기다려 주세요.");
      } else {
        setErr(text);
        setGenPhase(null);
        setGenLabel("");
      }
    } finally {
      localRun.current = false;
      setBusy(false);
    }
  }

  async function recommend() {
    if (!projectId || !selected) return;
    setBusy(true);
    setErr("");
    try {
      const res = await fetch(
        `/api/projects/${projectId}/outline/nodes/${selected.node_id}/recommend`,
        { method: "POST" },
      );
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      if (data.objective) updateSelected({ objective: data.objective });
      if (data.analysis_questions)
        updateSelected({ analysis_questions: data.analysis_questions });
      if (data.title) updateSelected({ title: data.title });
      setMsg("목표 재추천 반영 (저장 필요)");
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!projectId) return;
    setBusy(true);
    setErr("");
    try {
      await save();
      await api.approveOutline(projectId);
      await load();
      setMsg("목차 승인 → PRODUCING");
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  }

  function move(dir: -1 | 1) {
    if (!selected) return;
    const idx = nodes.findIndex((n) => n.node_id === selected.node_id);
    const j = idx + dir;
    if (j < 0 || j >= nodes.length) return;
    const next = [...nodes];
    [next[idx], next[j]] = [next[j], next[idx]];
    setNodes(next.map((n, i) => ({ ...n, order: i + 1 })));
  }

  function removeSelected() {
    if (!selected || outline?.approved) return;
    const title = selected.title || "이 장";
    if (!window.confirm(`「${title}」을(를) 삭제할까요? 하위 장도 함께 제거됩니다.`)) {
      return;
    }
    const removeIds = new Set<string>([selected.node_id]);
    let grew = true;
    while (grew) {
      grew = false;
      for (const n of nodes) {
        if (n.parent_id && removeIds.has(n.parent_id) && !removeIds.has(n.node_id)) {
          removeIds.add(n.node_id);
          grew = true;
        }
      }
    }
    const next = nodes
      .filter((n) => !removeIds.has(n.node_id))
      .map((n, i) => ({ ...n, order: i + 1 }));
    setNodes(next);
    setSelectedId(next[0]?.node_id || "");
    setMsg("장 삭제됨 (저장 필요)");
    setErr("");
  }

  if (!projectId) {
    return (
      <div>
        <h1 className="page-title">목차</h1>
        <p className="page-desc">먼저 프로젝트를 선택하세요.</p>
      </div>
    );
  }

  const statusText =
    genLabel ||
    (genPhase === "analyzing"
      ? "자료 분석 중 (Ollama) — 수 분 걸릴 수 있습니다"
      : genPhase === "planning"
        ? "목차 생성 중 (Ollama) — 수 분 걸릴 수 있습니다"
        : "");

  return (
    <div>
      <h1 className="page-title">목차</h1>
      <p className="page-desc">
        {outline?.title || "계획 제목 없음"}
        {outline?.approved ? " · 승인됨" : ""}
      </p>

      <div className="row" style={{ marginBottom: "0.9rem" }}>
        <button type="button" disabled={generating} onClick={generate}>
          {generating
            ? genPhase === "analyzing"
              ? "분석 중…"
              : "목차 생성 중…"
            : "분석→목차 생성"}
        </button>
        <button type="button" className="secondary" disabled={generating} onClick={save}>
          저장
        </button>
        <button
          type="button"
          disabled={generating || !!outline?.approved}
          onClick={approve}
        >
          승인
        </button>
        {msg && !generating && <span className="okmsg">{msg}</span>}
        {err && <span className="err">{err}</span>}
      </div>

      {generating && (
        <div className="progress-banner" role="status" aria-live="polite">
          <span className="progress-dot" aria-hidden />
          <div>
            <strong>{genPhase === "analyzing" ? "자료 분석 중" : "목차 생성 중"}</strong>
            <div className="muted" style={{ marginTop: "0.15rem" }}>
              {statusText}. 다른 메뉴로 이동해도 백엔드에서 계속 실행됩니다.
            </div>
          </div>
        </div>
      )}

      <div className="panes-2">
        <section className="pane">
          <h2 className="pane-title">트리</h2>
          <div className="stack">
            {nodes.map((n) => (
              <div
                key={n.node_id}
                className={`tree-item lvl${n.level} ${selectedId === n.node_id ? "active" : ""}`}
                onClick={() => setSelectedId(n.node_id)}
              >
                {n.title}
              </div>
            ))}
            {!nodes.length && <div className="muted">목차 없음 — 생성하세요</div>}
          </div>
          {selected && (
            <div className="row" style={{ marginTop: "0.75rem" }}>
              <button type="button" className="secondary" onClick={() => move(-1)}>
                ↑
              </button>
              <button type="button" className="secondary" onClick={() => move(1)}>
                ↓
              </button>
            </div>
          )}
        </section>

        <section className="pane">
          <h2 className="pane-title">장 상세</h2>
          {!selected && <div className="muted">노드를 선택하세요</div>}
          {selected && (
            <div className="stack">
              <div className="field">
                <label>제목</label>
                <input
                  value={selected.title}
                  onChange={(e) => updateSelected({ title: e.target.value })}
                />
              </div>
              <div className="field">
                <label>작성 목표</label>
                <textarea
                  rows={4}
                  value={selected.objective || ""}
                  onChange={(e) => updateSelected({ objective: e.target.value })}
                />
              </div>
              <div className="field">
                <label>분석 질문 (줄바꿈)</label>
                <textarea
                  rows={4}
                  value={(selected.analysis_questions || []).join("\n")}
                  onChange={(e) =>
                    updateSelected({
                      analysis_questions: e.target.value
                        .split("\n")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </div>
              <div className="field">
                <label>예상 분량</label>
                <input
                  type="number"
                  value={selected.expected_length ?? 0}
                  onChange={(e) =>
                    updateSelected({ expected_length: Number(e.target.value) || 0 })
                  }
                />
              </div>
              <div className="field">
                <label>시각자료 (쉼표)</label>
                <input
                  value={(selected.planned_visuals || []).join(", ")}
                  onChange={(e) =>
                    updateSelected({
                      planned_visuals: e.target.value
                        .split(",")
                        .map((s) => s.trim())
                        .filter(Boolean),
                    })
                  }
                />
              </div>
              <button
                type="button"
                className="secondary"
                disabled={generating}
                onClick={recommend}
              >
                목표 재추천
              </button>
              <button
                type="button"
                className="danger"
                disabled={generating || !!outline?.approved || nodes.length <= 1}
                onClick={removeSelected}
              >
                이 장 삭제
              </button>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
