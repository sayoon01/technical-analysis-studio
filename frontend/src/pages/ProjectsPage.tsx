import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Project, Source } from "../types";
import { useWorkspace } from "../workspace";

export default function ProjectsPage() {
  const { projectId, setProjectId, setEditionId } = useWorkspace();
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [sourceCounts, setSourceCounts] = useState<Record<string, number>>({});

  async function refresh() {
    const list = await api.listProjects();
    setProjects(list);
    const counts: Record<string, number> = {};
    await Promise.all(
      list.map(async (p) => {
        try {
          const srcs: Source[] = await api.listSources(p.project_id);
          counts[p.project_id] = srcs.length;
        } catch {
          counts[p.project_id] = 0;
        }
      }),
    );
    setSourceCounts(counts);
  }

  useEffect(() => {
    refresh().catch((e) => setErr(String(e.message || e)));
  }, []);

  async function create() {
    if (!name.trim()) return;
    setBusy(true);
    setErr("");
    try {
      const p = await api.createProject(name.trim(), desc.trim() || undefined);
      setName("");
      setDesc("");
      setProjectId(p.project_id);
      setEditionId(p.current_edition_id || "");
      await refresh();
    } catch (e) {
      setErr(String((e as Error).message || e));
    } finally {
      setBusy(false);
    }
  }

  function select(p: Project) {
    setProjectId(p.project_id);
    setEditionId(p.current_edition_id || "");
  }

  return (
    <div>
      <h1 className="page-title">프로젝트</h1>
      <p className="page-desc">기술분석서 프로젝트를 만들고 선택합니다.</p>

      <div className="card stack" style={{ marginBottom: "1rem" }}>
        <div className="row">
          <div className="field" style={{ flex: 1, minWidth: 180 }}>
            <label>프로젝트명</label>
            <input value={name} onChange={(e) => setName(e.target.value)} placeholder="예: 공정 개선 분석" />
          </div>
          <div className="field" style={{ flex: 2, minWidth: 220 }}>
            <label>설명</label>
            <input value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="선택" />
          </div>
          <button type="button" disabled={busy} onClick={create} style={{ alignSelf: "end" }}>
            생성
          </button>
        </div>
        {err && <div className="err">{err}</div>}
      </div>

      <div className="card">
        <table className="data">
          <thead>
            <tr>
              <th>이름</th>
              <th>Stage</th>
              <th>자료</th>
              <th>Edition</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {projects.map((p) => (
              <tr key={p.project_id}>
                <td>
                  <div>{p.name}</div>
                  <div className="mono muted">{p.project_id}</div>
                </td>
                <td>
                  <span className="badge">{p.stage}</span>
                </td>
                <td>{sourceCounts[p.project_id] ?? "—"}</td>
                <td className="mono muted">{p.current_edition_id || "—"}</td>
                <td>
                  <div className="row">
                    <button
                      type="button"
                      className={projectId === p.project_id ? undefined : "secondary"}
                      onClick={() => select(p)}
                    >
                      {projectId === p.project_id ? "선택됨" : "선택"}
                    </button>
                    <Link to="/sources" onClick={() => select(p)}>
                      <button type="button" className="secondary">
                        자료 →
                      </button>
                    </Link>
                  </div>
                </td>
              </tr>
            ))}
            {!projects.length && (
              <tr>
                <td colSpan={5} className="muted">
                  프로젝트가 없습니다.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
