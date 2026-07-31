import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { Edition } from "../types";
import { useWorkspace } from "../workspace";

export default function EditionComparePage() {
  const { projectId, editionId, setEditionId } = useWorkspace();
  const [editions, setEditions] = useState<Edition[]>([]);
  const [left, setLeft] = useState("");
  const [right, setRight] = useState("");
  const [diff, setDiff] = useState<Record<string, unknown> | null>(null);
  const [impact, setImpact] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    api
      .listEditions(projectId)
      .then((list) => {
        setEditions(list);
        const sorted = [...list].sort(
          (a, b) => (a.edition_number || 0) - (b.edition_number || 0),
        );
        if (sorted.length >= 2) {
          setLeft(sorted[sorted.length - 2].edition_id);
          setRight(sorted[sorted.length - 1].edition_id);
        } else if (sorted[0]) {
          setLeft(sorted[0].edition_id);
          setRight(sorted[0].edition_id);
        } else if (editionId) {
          setLeft(editionId);
          setRight(editionId);
        }
      })
      .catch((e) => setErr(String(e.message || e)));
  }, [projectId]);

  async function runDiff() {
    if (!left || !right) return;
    setBusy(true);
    setErr("");
    try {
      setDiff(await api.diffEditions(left, right));
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  }

  async function previewImpact() {
    if (!projectId || !left) return;
    setBusy(true);
    setErr("");
    try {
      setImpact(await api.previewImpact(projectId, left));
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  }

  async function improve() {
    if (!projectId || !left) return;
    setBusy(true);
    setErr("");
    try {
      const res = await api.produce(projectId, left);
      const id = String(
        (res as { edition_id?: string }).edition_id ||
          (res as { edition?: { edition_id?: string } }).edition?.edition_id ||
          "",
      );
      if (id) {
        setEditionId(id);
        setRight(id);
        const list = await api.listEditions(projectId);
        setEditions(list);
      }
      setDiff(null);
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  }

  if (!projectId) {
    return (
      <div>
        <h1 className="page-title">Edition 비교</h1>
        <p className="page-desc">먼저 프로젝트를 선택하세요.</p>
      </div>
    );
  }

  const outline = (diff?.outline || {}) as {
    added_sections?: string[];
    removed_sections?: string[];
    common_sections?: string[];
  };
  const claims = (diff?.claims || {}) as { added?: string[]; removed?: string[] };
  const metrics = (diff?.metrics_mentioned || {}) as {
    added?: string[];
    removed?: string[];
  };
  const sections = (diff?.sections || []) as Array<Record<string, unknown>>;

  return (
    <div>
      <h1 className="page-title">Edition 비교</h1>
      <p className="page-desc">V1↔V2 목차·문단·주장·수치 diff</p>

      <div className="card stack" style={{ marginBottom: "1rem" }}>
        <div className="row">
          <div className="field">
            <label>Left (기준)</label>
            <select value={left} onChange={(e) => setLeft(e.target.value)}>
              {editions.map((e) => (
                <option key={e.edition_id} value={e.edition_id}>
                  E{e.edition_number} · {e.edition_id}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label>Right (비교)</label>
            <select value={right} onChange={(e) => setRight(e.target.value)}>
              {editions.map((e) => (
                <option key={e.edition_id} value={e.edition_id}>
                  E{e.edition_number} · {e.edition_id}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="row">
          <button type="button" disabled={busy} onClick={runDiff}>
            Diff
          </button>
          <button type="button" className="secondary" disabled={busy} onClick={previewImpact}>
            Impact 미리보기
          </button>
          <button type="button" className="secondary" disabled={busy} onClick={improve}>
            V2 개선 작성
          </button>
          {err && <span className="err">{err}</span>}
        </div>
      </div>

      {impact && (
        <div className="card" style={{ marginBottom: "1rem" }}>
          <h2 className="pane-title">Impact</h2>
          <pre className="body">{JSON.stringify(impact, null, 2)}</pre>
        </div>
      )}

      {diff && (
        <div className="grid cols-2">
          <div className="card stack">
            <h2 className="pane-title">목차</h2>
            <div>
              <span className="muted">추가</span>
              <div className="row">
                {(outline.added_sections || []).map((t) => (
                  <span key={t} className="badge ok">
                    {t}
                  </span>
                ))}
                {!outline.added_sections?.length && <span className="muted">—</span>}
              </div>
            </div>
            <div>
              <span className="muted">제거</span>
              <div className="row">
                {(outline.removed_sections || []).map((t) => (
                  <span key={t} className="badge bad">
                    {t}
                  </span>
                ))}
                {!outline.removed_sections?.length && <span className="muted">—</span>}
              </div>
            </div>
            <div>
              <span className="muted">주장 추가 {claims.added?.length ?? 0}</span>
              <ul className="extract-list">
                {(claims.added || []).slice(0, 10).map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
            <div>
              <span className="muted">수치 변화</span>
              <div className="mono" style={{ fontSize: "0.85rem" }}>
                +{(metrics.added || []).join(", ") || "—"} / −
                {(metrics.removed || []).join(", ") || "—"}
              </div>
            </div>
          </div>
          <div className="card">
            <h2 className="pane-title">섹션 변경</h2>
            <table className="data">
              <thead>
                <tr>
                  <th>제목</th>
                  <th>상태</th>
                  <th>길이</th>
                </tr>
              </thead>
              <tbody>
                {sections.map((s) => (
                  <tr key={String(s.title)}>
                    <td>{String(s.title)}</td>
                    <td>
                      <span
                        className={`badge ${s.change === "MODIFIED" ? "warn" : "ok"}`}
                      >
                        {String(s.change)}
                      </span>
                    </td>
                    <td className="mono">
                      {String(s.left_len)} → {String(s.right_len)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
