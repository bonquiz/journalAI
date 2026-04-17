import { beforeEach, describe, expect, test, vi } from "vitest";
import { searchEntries, getSearchStatus, reindexEmbeddings } from "../../src/lib/search";

// api.ts reads the csrf cookie from document.cookie — fake it
function setCsrfCookie(value: string) {
  Object.defineProperty(document, "cookie", {
    configurable: true,
    get: () => `csrf=${value}`,
    set: () => {},
  });
}

describe("search api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    setCsrfCookie("t");
  });

  test("searchEntries posts to /api/search with body", async () => {
    (globalThis.fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ results: [], status: "ok" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      })
    );
    const r = await searchEntries("regenbogen", 5);
    expect(r.status).toBe("ok");
    const call = (globalThis.fetch as any).mock.calls[0];
    expect(call[0]).toBe("/api/search");
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(call[1].body)).toEqual({ query: "regenbogen", top_k: 5 });
    expect(call[1].headers["X-CSRF-Token"]).toBe("t");
  });

  test("getSearchStatus does GET", async () => {
    (globalThis.fetch as any).mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          total: 1,
          embedded: 1,
          pending: 0,
          current_model: "m",
          configured: true,
          indexing: false,
        }),
        { status: 200, headers: { "content-type": "application/json" } }
      )
    );
    const s = await getSearchStatus();
    expect(s.configured).toBe(true);
    expect((globalThis.fetch as any).mock.calls[0][0]).toBe("/api/search/status");
  });

  test("reindexEmbeddings does POST", async () => {
    (globalThis.fetch as any).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), {
        status: 202,
        headers: { "content-type": "application/json" },
      })
    );
    await reindexEmbeddings();
    const call = (globalThis.fetch as any).mock.calls[0];
    expect(call[0]).toBe("/api/search/reindex");
    expect(call[1].method).toBe("POST");
  });
});
