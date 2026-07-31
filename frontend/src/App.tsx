import { NavLink, Route, Routes } from "react-router-dom";
import { WorkspaceProvider, useWorkspace } from "./workspace";
import ProjectsPage from "./pages/ProjectsPage";
import SourcesPage from "./pages/SourcesPage";
import AnalysisPage from "./pages/AnalysisPage";
import OutlineEditorPage from "./pages/OutlineEditorPage";
import ProductionPage from "./pages/ProductionPage";
import EditionComparePage from "./pages/EditionComparePage";
import ExportPage from "./pages/ExportPage";

function Shell() {
  const { projectId, editionId } = useWorkspace();
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">Technical Analysis Studio</div>
        <div className="brand-sub">전문가 기술분석서</div>
        <nav className="nav">
          <NavLink to="/" end>
            프로젝트
          </NavLink>
          <NavLink to="/sources">자료</NavLink>
          <NavLink to="/analysis">자료 분석</NavLink>
          <NavLink to="/outline">목차</NavLink>
          <NavLink to="/production">작성·검토</NavLink>
          <NavLink to="/compare">Edition 비교</NavLink>
          <NavLink to="/export">출력</NavLink>
        </nav>
        <div className="stack" style={{ marginTop: "1.5rem" }}>
          <div className="muted" style={{ fontSize: "0.75rem" }}>
            선택 중
          </div>
          <div className="mono muted" style={{ wordBreak: "break-all" }}>
            {projectId || "—"}
          </div>
          <div className="mono muted" style={{ wordBreak: "break-all" }}>
            {editionId || "—"}
          </div>
        </div>
      </aside>
      <main className="main">
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/sources" element={<SourcesPage />} />
          <Route path="/analysis" element={<AnalysisPage />} />
          <Route path="/outline" element={<OutlineEditorPage />} />
          <Route path="/production" element={<ProductionPage />} />
          <Route path="/compare" element={<EditionComparePage />} />
          <Route path="/export" element={<ExportPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default function App() {
  return (
    <WorkspaceProvider>
      <Shell />
    </WorkspaceProvider>
  );
}
