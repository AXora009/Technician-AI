export interface Source {
  index: number;
  id: number;
  kind: "manual_chunk" | "knowledge_entry";
  metadata: Record<string, unknown>;
  preview: string;
}

export interface AskResponse {
  answer: string;
  sources: Source[];
  conversation_id: number;
}

export interface KnowledgeEntry {
  id: number;
  kind: string;
  text: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Topic {
  path: string | string[];
  count?: number;
  manual_count?: number;
  knowledge_count?: number;
  documents?: KnowledgeEntry[];
}

export interface IngestResponse {
  filename: string;
  chunks: number;
}

export interface FeedbackResponse {
  id?: number;
  question?: string;
  answer?: string;
  message?: string;
}

export interface Resolution {
  likely_cause: string;
  next_steps: string[];
  confirmed_condition: string;
  confidence_level: "high" | "medium" | "low";
  confidence_justification: string;
}

export interface DiagnoseResponse {
  message: string;
  is_resolved: boolean;
  resolution?: Resolution | null;
  sources: Source[];
  conversation_id: number | null;
  session_id: string;
  step: number;
  is_safety_critical?: boolean;
  hazard_type?: string | null;
}
