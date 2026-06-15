import type {
  AskResponse,
  DiagnoseResponse,
  FeedbackResponse,
  IngestResponse,
  KnowledgeEntry,
  Topic,
} from "@/types/api";

async function post<T>(url: string, body: FormData | Record<string, string>): Promise<T> {
  const isFormData = body instanceof FormData;
  const res = await fetch(url, {
    method: "POST",
    body: isFormData ? body : new URLSearchParams(body),
    headers: isFormData ? undefined : { "Content-Type": "application/x-www-form-urlencoded" },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function httpDelete<T>(url: string): Promise<T> {
  const res = await fetch(url, { method: "DELETE" });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export const api = {
  ask: (question: string) => post<AskResponse>("/api/ask", { question }),

  feedback: (conversationId: number, kind: string, note?: string) =>
    post<FeedbackResponse>(`/api/feedback/${conversationId}`, {
      kind,
      ...(note ? { note } : {}),
    }),

  ingest: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return post<IngestResponse>("/api/ingest", fd);
  },

  knowledge: () => get<{ entries: KnowledgeEntry[] }>("/api/knowledge"),

  topics: () => get<{ topics: Topic[] }>("/api/topics"),

  manuals: () => get<{ manuals: { title: string; chunks: number; source_path: string }[] }>("/api/manuals"),

  manualFiles: () => get<{ files: { name: string; size: number; url: string }[] }>("/api/manuals/files"),

  deleteManual: (title: string) => httpDelete<{ deleted_chunks: number }>(`/api/manuals/${encodeURIComponent(title)}`),

  diagnoseStart: (question: string) =>
    post<DiagnoseResponse>("/api/diagnose", { question }),

  diagnoseStep: (sessionId: string, answer: string) =>
    post<DiagnoseResponse>("/api/diagnose/step", { session_id: sessionId, answer }),
};
