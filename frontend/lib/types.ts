export type Jurisdiction = 'IN' | 'US' | 'AU';
export type SupportStatus = 'SUPPORTED' | 'PARTIALLY_SUPPORTED' | 'UNSUPPORTED' | 'CONFLICTING' | 'INSUFFICIENT';
export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export interface User {
  id: string;
  name: string;
  email: string;
  role: 'ADMIN' | 'USER';
  workspaces: { id: string; name: string; role: string; confidential_mode: boolean }[];
}

export interface InnovationCard {
  id: string;
  name: string;
  description: string;
  status: string;
  confidentiality_level: string;
  jurisdictions: Jurisdiction[];
  is_demo: boolean;
  updated_at: string;
  counts: { evidence: number; patent_matches: number; evidence_gaps: number; open_escalations: number };
  completion: { percent: number; checks: Record<string, boolean> };
}

export interface Feature {
  id: string;
  feature_type: string;
  name: string;
  description?: string;
  normalized_term?: string;
  importance: number;
  source: string;
}

export interface InnovationDetail extends InnovationCard {
  innovation_type?: string;
  wizard_input: any;
  profile: any | null;
  features: Feature[];
  analysis: { last_run_at?: string; last_run_steps?: any[]; last_run_ms?: number };
  confidential_warning: string | null;
}

export interface Evidence {
  n: number;
  chunk_id: string;
  document_id: string;
  title: string;
  source_name?: string;
  authority: string;
  tier: number;
  jurisdiction: string;
  domain: string;
  document_type: string;
  section?: string;
  subsection?: string;
  url?: string;
  publication_date?: string;
  effective_date?: string;
  last_checked?: string;
  version?: string;
  freshness: string;
  is_demo: boolean;
  review_status: string;
  injection_flag: boolean;
  why_retrieved: string;
  rerank_score: number;
  relevance: number;
  methods: string[];
  passage: string;
}

export interface KeyPoint {
  id: number;
  text: string;
  text_en?: string | null;
  type: 'FACT' | 'INFERENCE' | 'USER_PROVIDED' | 'UNCERTAINTY';
  citations: number[];
  invalid_citations: number[];
  status: SupportStatus;
  score: number;
  checks: Record<string, any>;
  notes: string[];
}

export interface ResearchPayload {
  type: 'answer' | 'abstention' | 'clarification' | 'answer_with_boundary';
  language: 'en' | 'hi';
  answer: string;
  key_points: KeyPoint[];
  evidence: Evidence[];
  evidence_status: SupportStatus;
  confidence: { score: number; label: string; heuristic?: boolean; signals?: any[]; penalties?: string[]; explanation?: string };
  response_language?: string;
  source_languages?: string[];
  tkdl_access?: { status: string; label: string; meaning: string } | null;
  search_query?: string;
  conflicts: any[];
  limitations: string[];
  next_step: string;
  abstention: null | { searched: string; found: string; missing: string; why: string; next_step: string };
  suggested_replies?: string[];
  analysis: any;
  terminology: any[];
  trace: any;
  generation: { mode: string; provider: string; latency_ms?: number; usage?: { calls: number; prompt_tokens: number; completion_tokens: number; estimated_cost_usd: number } };
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  payload: any;
  feedback?: string | null;
  flagged?: boolean;
  created_at: string;
}
