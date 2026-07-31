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

export type Section = {
  section_id: string;
  edition_id: string;
  title: string;
  objective?: string;
  content_markdown?: string;
  status?: string;
  claims?: Claim[];
  evidence_pack?: Record<string, unknown> | null;
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
