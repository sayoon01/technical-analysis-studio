import { useEffect, useRef, useState, type ReactNode } from "react";
import { api } from "../api/client";
import { useWorkspace } from "../workspace";

const TABS = [
  { id: "topic", label: "주제" },
  { id: "tech", label: "기술" },
  { id: "problems", label: "문제" },
  { id: "system", label: "시스템" },
  { id: "process", label: "흐름" },
  { id: "quant", label: "정량" },
  { id: "conflicts", label: "충돌" },
  { id: "gaps", label: "근거 부족" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function AnalysisPage() {
  const { projectId } = useWorkspace();
  const [tab, setTab] = useState<TabId>("topic");
  const [analysis, setAnalysis] = useState<Record<string, unknown> | null>(null);
  const [analysisMeta, setAnalysisMeta] = useState<{ id?: string; createdAt?: string }>({});
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [serverBusy, setServerBusy] = useState(false);
  const [phaseLabel, setPhaseLabel] = useState("");
  const localRun = useRef(false);

  const analyzing = busy || serverBusy;

  async function load() {
    if (!projectId) return;
    const row = await api.getAnalysis(projectId);
    setAnalysis((row.analysis as Record<string, unknown>) || row);
    setAnalysisMeta({
      id: typeof row.analysis_id === "string" ? row.analysis_id : undefined,
      createdAt: typeof row.created_at === "string" ? row.created_at : undefined,
    });
  }

  useEffect(() => {
    if (!projectId) return;
    load().catch(() => {
      setAnalysis(null);
      setAnalysisMeta({});
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
        const running = !!(st.busy && st.phase === "analyzing");
        if (running) {
          sawBusy = true;
          setServerBusy(true);
          setPhaseLabel(st.label || "자료 분석 중 (Ollama) — 수 분 걸릴 수 있습니다");
        } else if (!localRun.current) {
          setServerBusy(false);
          setPhaseLabel("");
          if (sawBusy) {
            sawBusy = false;
            await load().catch(() => null);
            setMsg("분석 결과가 갱신되었습니다");
            setBusy(false);
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

  async function runAnalyze() {
    if (!projectId || analyzing) return;
    localRun.current = true;
    setBusy(true);
    setServerBusy(true);
    setErr("");
    setMsg("");
    setPhaseLabel("자료 분석 중 (Ollama) — 수 분 걸릴 수 있습니다");
    try {
      const row = await api.analyze(projectId);
      setAnalysis((row.analysis as Record<string, unknown>) || row);
      setAnalysisMeta({
        id: typeof row.analysis_id === "string" ? row.analysis_id : undefined,
        createdAt: typeof row.created_at === "string" ? row.created_at : undefined,
      });
      setMsg("분석 완료");
      setServerBusy(false);
      setPhaseLabel("");
    } catch (e) {
      const text = String((e as Error).message || e);
      if (/already running/i.test(text)) {
        setMsg("이미 분석 중입니다. 완료되면 아래 결과가 자동으로 갱신됩니다.");
        // keep analyzing=true via serverBusy from poll
      } else {
        setErr(text);
        setServerBusy(false);
        setPhaseLabel("");
      }
    } finally {
      localRun.current = false;
      setBusy(false);
    }
  }

  if (!projectId) {
    return (
      <div>
        <h1 className="page-title">자료 분석</h1>
        <p className="page-desc">먼저 프로젝트를 선택하세요.</p>
      </div>
    );
  }

  const a = analysis || {};

  function list(items: unknown): string[] {
    return Array.isArray(items) ? items.map(String) : [];
  }

  let body: ReactNode = null;
  switch (tab) {
    case "topic":
      body = (
        <div className="stack">
          <Field label="주제" value={String(a.main_topic || "—")} />
          <Field label="도메인" value={String(a.technical_domain || "—")} />
          <Field label="문서 목적" value={String(a.document_purpose || "—")} />
          <Chips label="핵심 엔티티" items={list(a.key_entities)} />
          <Chips label="권장 초점" items={list(a.recommended_report_focus)} />
        </div>
      );
      break;
    case "tech":
      body = <Chips label="핵심 기술" items={list(a.key_technologies)} />;
      break;
    case "problems":
      body = (
        <Chips label="비즈니스/기술 문제" items={list(a.business_or_technical_problems)} />
      );
      break;
    case "system":
      body = <Chips label="시스템 구성" items={list(a.system_components)} />;
      break;
    case "process":
      body = <Chips label="프로세스/흐름" items={list(a.processes)} />;
      break;
    case "quant":
      body = (
        <ul className="extract-list">
          {Array.isArray(a.quantitative_findings) &&
            (a.quantitative_findings as Array<Record<string, unknown>>).map((q, i) => (
              <li key={i}>
                <strong>{String(q.name)}</strong>
                {q.change != null ? ` · ${String(q.change)}` : ""}
                {q.page_number != null ? (
                  <span className="muted"> · p.{String(q.page_number)}</span>
                ) : null}
              </li>
            ))}
          {!(
            Array.isArray(a.quantitative_findings) && a.quantitative_findings.length
          ) && <li className="muted">정량 발견 없음</li>}
          {list(a.qualitative_findings).map((q, i) => (
            <li key={`ql-${i}`}>{q}</li>
          ))}
        </ul>
      );
      break;
    case "conflicts":
      body = <Chips label="충돌/모순" items={list(a.contradictions)} />;
      break;
    case "gaps":
      body = <Chips label="근거 부족" items={list(a.evidence_gaps)} />;
      break;
  }

  const createdLabel = analysisMeta.createdAt
    ? new Date(analysisMeta.createdAt).toLocaleString("ko-KR")
    : null;

  return (
    <div>
      <h1 className="page-title">자료 분석</h1>
      <p className="page-desc">코퍼스 분석 결과를 탭별로 확인합니다.</p>

      <div className="row" style={{ marginBottom: "0.9rem" }}>
        <button type="button" disabled={analyzing} onClick={runAnalyze}>
          {analyzing ? "분석 중…" : "분석 실행"}
        </button>
        <button
          type="button"
          className="secondary"
          disabled={analyzing}
          onClick={() => load().catch(() => null)}
        >
          새로고침
        </button>
        {msg && !analyzing && <span className="okmsg">{msg}</span>}
        {err && <span className="err">{err}</span>}
      </div>

      {analyzing && (
        <div className="progress-banner" role="status" aria-live="polite">
          <span className="progress-dot" aria-hidden />
          <div>
            <strong>자료 분석 중</strong>
            <div className="muted" style={{ marginTop: "0.15rem" }}>
              {phaseLabel || "Ollama 분석 중입니다. 수 분 걸릴 수 있습니다."} 다른 메뉴로
              이동해도 계속 실행되며, 끝나면 아래 결과가 자동 갱신됩니다.
            </div>
          </div>
        </div>
      )}

      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            className={tab === t.id ? "tab active" : "tab"}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="card" style={{ marginTop: "0.9rem" }}>
        {analysis && (
          <div className="muted" style={{ fontSize: "0.8rem", marginBottom: "0.75rem" }}>
            {analyzing
              ? "아래는 이전 분석 결과입니다. 진행 중인 분석이 끝나면 이 내용이 갱신됩니다."
              : createdLabel
                ? `마지막 분석: ${createdLabel}`
                : "저장된 분석 결과"}
          </div>
        )}
        {!analysis ? (
          <div className="muted">
            {analyzing
              ? "분석 중입니다. 완료되면 결과가 여기에 표시됩니다."
              : "분석 결과가 없습니다. 분석을 실행하세요."}
          </div>
        ) : (
          body
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="muted" style={{ fontSize: "0.8rem" }}>
        {label}
      </div>
      <div>{value}</div>
    </div>
  );
}

function Chips({ label, items }: { label: string; items: string[] }) {
  return (
    <div>
      <div className="muted" style={{ fontSize: "0.8rem", marginBottom: "0.4rem" }}>
        {label}
      </div>
      <div className="row">
        {items.length ? (
          items.map((x, i) => (
            <span key={i} className="badge">
              {x}
            </span>
          ))
        ) : (
          <span className="muted">없음</span>
        )}
      </div>
    </div>
  );
}
