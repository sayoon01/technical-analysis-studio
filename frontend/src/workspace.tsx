import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

type Ctx = {
  projectId: string;
  setProjectId: (id: string) => void;
  editionId: string;
  setEditionId: (id: string) => void;
};

const WorkspaceContext = createContext<Ctx | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [projectId, setProjectId] = useState(
    () => localStorage.getItem("tas.projectId") || "",
  );
  const [editionId, setEditionId] = useState(
    () => localStorage.getItem("tas.editionId") || "",
  );

  const value = useMemo(
    () => ({
      projectId,
      setProjectId: (id: string) => {
        localStorage.setItem("tas.projectId", id);
        setProjectId(id);
      },
      editionId,
      setEditionId: (id: string) => {
        localStorage.setItem("tas.editionId", id);
        setEditionId(id);
      },
    }),
    [projectId, editionId],
  );

  return (
    <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error("WorkspaceProvider missing");
  return ctx;
}
