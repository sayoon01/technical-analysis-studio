export type Project = {
  project_id: string;
  name: string;
  description?: string | null;
  stage: string;
  current_edition_id?: string | null;
};

export type Source = {
  source_id: string;
  project_id: string;
  filename: string;
  role: string;
  status: string;
  page_count?: number | null;
};

export type OutlineNode = {
  node_id: string;
  parent_id?: string | null;
  level: number;
  order: number;
  title: string;
  objective?: string;
  analysis_questions?: string[];
  expected_length?: number;
  source_scope?: string[];
  required_evidence_types?: string[];
  planned_visuals?: string[];
};

export type Outline = {
  outline_id: string;
  plan_id: string;
  approved: boolean;
  title?: string;
  subtitle?: string | null;
  nodes: OutlineNode[];
};

export type TitleCandidate = {
  title: string;
  style: "SOURCE_PRESERVING" | "ANALYTICAL" | "CONCISE" | string;
  rationale?: string | null;
};

export type ReportStrategy = {
  source_title?: string | null;
  title_candidates?: TitleCandidate[];
  recommended_title?: string;
  subtitle?: string | null;
  target_reader?: string;
  purpose?: string;
  central_thesis?: string;
  narrative_arc?: string[];
  included_scope?: string[];
  excluded_scope?: string[];
  evidence_limitations?: string[];
  recommended_pages?: number;
  recommended_chapter_count?: number;
  recommended_visual_count?: number;
};

export type PlanDetail = {
  plan_id: string;
  project_id: string;
  title: string;
  subtitle?: string | null;
  purpose?: string;
  target_reader?: string;
  report_summary?: string;
  plan: {
    title?: string;
    subtitle?: string | null;
    title_candidates?: TitleCandidate[];
    central_thesis?: string | null;
    strategy?: ReportStrategy | null;
    [key: string]: unknown;
  };
};

export type Section = {
  section_id: string;
  edition_id: string;
  title: string;
  objective?: string;
  content_markdown?: string;
  status?: string;
  claims?: Claim[];
  evidence_pack?: Record<string, unknown> | null;
  paragraphs?: Paragraph[];
};

export type Paragraph = {
  paragraph_id: string;
  subsection_key?: string | null;
  paragraph_type?: string | null;
  text: string;
  order_index: number;
  edit_state: "AI_EDITABLE" | "USER_EDITED" | "USER_LOCKED" | string;
};

export type Claim = {
  claim_id: string;
  statement: string;
  claim_type?: string;
  verification_status?: string;
  evidence?: Array<{
    evidence_id: string;
    source_id: string;
    page: number;
    statement: string;
  }>;
};

export type Edition = {
  edition_id: string;
  project_id: string;
  edition_number: number;
  parent_edition_id?: string | null;
  status: string;
  sections?: Section[];
};
