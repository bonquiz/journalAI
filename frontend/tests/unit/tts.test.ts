import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearCache, synthesize } from "$lib/tts";

const createdUrls: string[] = [];
const revokedUrls: string[] = [];

beforeEach(() => {
  createdUrls.length = 0;
  revokedUrls.length = 0;
  URL.createObjectURL = vi.fn((_blob: Blob) => {
    const u = `blob:mock-${createdUrls.length}`;
    createdUrls.push(u);
    return u;
  });
  URL.revokeObjectURL = vi.fn((u: string) => {
    revokedUrls.push(u);
  });
  document.cookie = "csrf=testcsrf; path=/";
  clearCache();
});

afterEach(() => {
  vi.restoreAllMocks();
});

function mockFetchOnce(body: ArrayBuffer | string, status = 200) {
  const blob = new Blob([body], { type: "audio/mpeg" });
  return vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(new Response(blob, { status, headers: { "Content-Type": "audio/mpeg" } }));
}

describe("tts synthesize", () => {
  it("fetches and caches result", async () => {
    const f = mockFetchOnce("audio-bytes-1");
    const first = await synthesize("Hallo Welt");
    const second = await synthesize("Hallo Welt");
    expect(first).not.toBeNull();
    expect(second).not.toBeNull();
    expect(first!.url).toBe(second!.url);
    expect(f).toHaveBeenCalledTimes(1);
  });

  it("different text creates different cache entries", async () => {
    mockFetchOnce("a");
    mockFetchOnce("b");
    const a = await synthesize("Text A");
    const b = await synthesize("Text B");
    expect(a!.url).not.toBe(b!.url);
  });

  it("different voice invalidates cache", async () => {
    mockFetchOnce("a");
    mockFetchOnce("b");
    await synthesize("Hallo", { voice: "alloy" });
    await synthesize("Hallo", { voice: "echo" });
    expect(createdUrls).toHaveLength(2);
  });

  it("returns null and shows toast on error", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response("", { status: 500 })
    );
    const out = await synthesize("Hallo");
    expect(out).toBeNull();
  });

  it("clearCache revokes blob URLs", async () => {
    mockFetchOnce("x");
    await synthesize("Hallo");
    expect(createdUrls.length).toBe(1);
    clearCache();
    expect(revokedUrls).toContain(createdUrls[0]);
  });
});
