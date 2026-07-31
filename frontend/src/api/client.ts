const API_BASE = import.meta.env.VITE_API_BASE || "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers || {}),
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<{ status: string }>("/health"),
  listProjects: () => request<import("../types").Project[]>("/api/projects"),
  createProject: (name: string, description?: string) =>
    request<import("../types").Project>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ name, description }),
    }),
  getProject: (id: string) =>
    request<import("../types").Project>(`/api/projects/${id}`),
  getStatus: (id: string) =>
    request<{
      project_id: string;
      stage: string;
      busy?: boolean;
      phase?: string | null;
      label?: string | null;
      started_at?: string | null;
      current_edition_id?: string;
    }>(`/api/projects/${id}/status`),
  listSources: (projectId: string) =>
    request<import("../types").Source[]>(`/api/projects/${projectId}/sources`),
  uploadSource: async (
    projectId: string,
    file: File,
    role: "EVIDENCE_SOURCE" | "PREVIOUS_EDITION" | "FORMAT_REFERENCE" = "EVIDENCE_SOURCE",
  ) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("role", role);
    return request<import("../types").Source>(`/api/projects/${projectId}/sources`, {
      method: "POST",
      body: fd,
    });
  },
  processSource: (sourceId: string) =>
    request<Record<string, unknown>>(`/api/sources/${sourceId}/process`, {
      method: "POST",
    }),
  getPage: (sourceId: string, page: number) =>
    request<Record<string, unknown>>(`/api/sources/${sourceId}/pages/${page}`),
  analyze: (projectId: string) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/analyze`, {
      method: "POST",
    }),
  getAnalysis: (projectId: string) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/analysis`),
  generatePlan: (projectId: string) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/plans/generate`, {
      method: "POST",
    }),
  getOutline: (projectId: string) =>
    request<import("../types").Outline>(`/api/projects/${projectId}/outline`),
  patchOutline: (projectId: string, nodes: unknown[]) =>
    request<import("../types").Outline>(`/api/projects/${projectId}/outline`, {
      method: "PATCH",
      body: JSON.stringify({ nodes }),
    }),
  patchPlan: (projectId: string, fields: Record<string, string>) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/plan`, {
      method: "PATCH",
      body: JSON.stringify(fields),
    }),
  approveOutline: (projectId: string) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/outline/approve`, {
      method: "POST",
    }),
  produce: (projectId: string, parentEditionId?: string) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/editions`, {
      method: "POST",
      body: JSON.stringify({ parent_edition_id: parentEditionId ?? null }),
    }),
  listEditions: (projectId: string) =>
    request<import("../types").Edition[]>(`/api/projects/${projectId}/editions`),
  getEdition: (editionId: string) =>
    request<import("../types").Edition>(`/api/editions/${editionId}`),
  getSection: (sectionId: string) =>
    request<import("../types").Section>(`/api/sections/${sectionId}`),
  reviewEdition: (editionId: string) =>
    request<Record<string, unknown>>(`/api/editions/${editionId}/review`, {
      method: "POST",
    }),
  sectionIssues: (sectionId: string) =>
    request<Array<Record<string, string>>>(`/api/sections/${sectionId}/issues`),
  claimLocations: (claimId: string) =>
    request<Record<string, unknown>>(`/api/claims/${claimId}/locations`),
  exportEdition: (editionId: string) =>
    request<Record<string, unknown>>(`/api/editions/${editionId}/exports`, {
      method: "POST",
    }),
  listExports: (editionId: string) =>
    request<Array<Record<string, string>>>(`/api/editions/${editionId}/exports`),
  diffEditions: (a: string, b: string) =>
    request<Record<string, unknown>>(`/api/editions/${a}/diff/${b}`),
  previewImpact: (projectId: string, parentEditionId: string) =>
    request<Record<string, unknown>>(`/api/projects/${projectId}/impact/preview`, {
      method: "POST",
      body: JSON.stringify({ parent_edition_id: parentEditionId }),
    }),
};

export function downloadExportUrl(exportId: string) {
  return `${API_BASE}/api/exports/${exportId}/download`;
}
