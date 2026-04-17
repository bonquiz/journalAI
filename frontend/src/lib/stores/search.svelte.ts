import {
  searchEntries,
  getSearchStatus,
  type RerankedResult,
  type SearchStatus,
  type SemanticSearchResponse,
} from "$lib/search";

type Mode = "keyword" | "semantic";

class SearchStore {
  query = $state("");
  mode: Mode = $state("keyword");
  loading = $state(false);
  results: RerankedResult[] | null = $state(null);
  lastResponse: SemanticSearchResponse | null = $state(null);
  status: SearchStatus | null = $state(null);
  error: string | null = $state(null);

  setMode(m: Mode) {
    this.mode = m;
    this.results = null;
    this.lastResponse = null;
    this.error = null;
  }

  setQuery(q: string) {
    this.query = q;
  }

  async runSearch(q: string, topK = 10) {
    this.error = null;
    this.loading = true;
    try {
      const resp = await searchEntries(q, topK);
      this.results = resp.results;
      this.lastResponse = resp;
    } catch (e: any) {
      this.error = e?.message ?? "Suche fehlgeschlagen";
      this.results = null;
      this.lastResponse = null;
    } finally {
      this.loading = false;
    }
  }

  async refreshStatus() {
    try {
      this.status = await getSearchStatus();
    } catch {
      // ignore
    }
  }

  reset() {
    this.query = "";
    this.mode = "keyword";
    this.loading = false;
    this.results = null;
    this.lastResponse = null;
    this.status = null;
    this.error = null;
  }
}

export const searchStore = new SearchStore();
