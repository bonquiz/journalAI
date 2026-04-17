import { api } from "$lib/api";

export interface RerankedResult {
  entry_id: string;
  title: string;
  excerpt: string;
  score: number;
  reason: string | null;
}

export interface SemanticSearchResponse {
  results: RerankedResult[];
  status: "ok" | "indexing" | "not_configured" | "error";
  progress?: { embedded: number; total: number; corrupted?: number };
}

export interface SearchStatus {
  total: number;
  embedded: number;
  pending: number;
  current_model: string | null;
  configured: boolean;
  indexing: boolean;
}

export function searchEntries(query: string, topK = 10): Promise<SemanticSearchResponse> {
  return api<SemanticSearchResponse>("/api/search", {
    method: "POST",
    body: { query, top_k: topK },
  });
}

export function getSearchStatus(): Promise<SearchStatus> {
  return api<SearchStatus>("/api/search/status", { method: "GET" });
}

export function reindexEmbeddings(): Promise<void> {
  return api<void>("/api/search/reindex", { method: "POST" });
}
