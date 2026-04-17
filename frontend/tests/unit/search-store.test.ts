import { describe, expect, test, vi, beforeEach } from "vitest";
import { searchStore } from "../../src/lib/stores/search.svelte";
import * as searchApi from "../../src/lib/search";

describe("search store", () => {
  beforeEach(() => {
    searchStore.reset();
    vi.restoreAllMocks();
  });

  test("toggle between keyword and semantic", () => {
    expect(searchStore.mode).toBe("keyword");
    searchStore.setMode("semantic");
    expect(searchStore.mode).toBe("semantic");
  });

  test("runSearch populates results on success", async () => {
    vi.spyOn(searchApi, "searchEntries").mockResolvedValue({
      results: [{ entry_id: "e1", title: "T", excerpt: "E", score: 90, reason: "why" }],
      status: "ok",
    });
    await searchStore.runSearch("regenbogen");
    expect(searchStore.loading).toBe(false);
    expect(searchStore.results?.length).toBe(1);
    expect(searchStore.lastResponse?.status).toBe("ok");
  });

  test("runSearch sets loading then clears", async () => {
    let resolvePromise!: (v: any) => void;
    vi.spyOn(searchApi, "searchEntries").mockReturnValue(
      new Promise((res) => (resolvePromise = res))
    );
    const p = searchStore.runSearch("q");
    expect(searchStore.loading).toBe(true);
    resolvePromise({ results: [], status: "ok" });
    await p;
    expect(searchStore.loading).toBe(false);
  });

  test("runSearch surfaces errors", async () => {
    vi.spyOn(searchApi, "searchEntries").mockRejectedValue(new Error("HTTP 502"));
    await searchStore.runSearch("q");
    expect(searchStore.error).toContain("502");
    expect(searchStore.results).toBeNull();
  });
});
