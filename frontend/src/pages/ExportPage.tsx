import { useEffect, useState } from "react";
import { api, downloadExportUrl } from "../api/client";
import type { Edition } from "../types";
import { useWorkspace } from "../workspace";

type ExportRow = {
  export_id: string;
  format?: string;
  status?: string;
  created_at?: string;
  path?: string;
};

export default function ExportPage() {
  const { projectId, editionId, setEditionId } = useWorkspace();
  const [editions, setEditions] = useState<Edition[]>([]);
  const [exports, setExports] = useState<ExportRow[]>([]);
  const [err, setErr] = useState("");
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function refreshExports(id: string) {
    setExports((await api.listExports(id)) as ExportRow[]);
  }

  useEffect(() => {
    if (!projectId) return;
    api
      .listEditions(projectId)
      .then((list) => {
        setEditions(list);
        if (!editionId && list[0]) setEditionId(list[0].edition_id);
      })
      .catch((e) => setErr(String(e.message || e)));
  }, [projectId]);

  useEffect(() => {
    if (!editionId) return;
    refreshExports(editionId).catch(() => setExports([]));
  }, [editionId]);

  async function runExport() {
    if (!editionId) return;
    setBusy(true);
    setErr("");
    setMsg("");
    try {
      const res = await api.exportEdition(editionId);
      setMsg(`Export 완료: ${JSON.stringify(res).slice(0, 120)}…`);
      await refreshExports(editionId);
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  }

  if (!projectId) {
    return (
      <div>
        <h1 className="page-title">출력</h1>
        <p className="page-desc">먼저 프로젝트를 선택하세요.</p>
      </div>
    );
  }

  return (
    <div>
      <h1 className="page-title">출력</h1>
      <p className="page-desc">MD / DOCX / PDF / ZIP 내보내기</p>

      <div className="card stack" style={{ marginBottom: "1rem" }}>
        <div className="field">
          <label>Edition</label>
          <select
            value={editionId}
            onChange={(e) => setEditionId(e.target.value)}
          >
            {!editions.length && <option value="">Edition 없음</option>}
            {editions.map((e) => (
              <option key={e.edition_id} value={e.edition_id}>
                E{e.edition_number} · {e.status} · {e.edition_id}
              </option>
            ))}
          </select>
        </div>
        <div className="row">
          <button type="button" disabled={busy || !editionId} onClick={runExport}>
            Export 생성
          </button>
          {msg && <span className="okmsg">{msg}</span>}
          {err && <span className="err">{err}</span>}
        </div>
        <div className="muted" style={{ fontSize: "0.85rem" }}>
          표지 메타·인용 형식은 서버 export 파이프라인 기본값을 사용합니다.
        </div>
      </div>

      <div className="card">
        <table className="data">
          <thead>
            <tr>
              <th>Export ID</th>
              <th>Format</th>
              <th>Status</th>
              <th>다운로드</th>
            </tr>
          </thead>
          <tbody>
            {exports.map((x) => (
              <tr key={x.export_id}>
                <td className="mono">{x.export_id}</td>
                <td>{x.format || "—"}</td>
                <td>
                  <span className="badge">{x.status || "—"}</span>
                </td>
                <td>
                  <a href={downloadExportUrl(x.export_id)} target="_blank" rel="noreferrer">
                    다운로드
                  </a>
                </td>
              </tr>
            ))}
            {!exports.length && (
              <tr>
                <td colSpan={4} className="muted">
                  export 기록 없음
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
