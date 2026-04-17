import { describe, it, expect } from "vitest";
import { mergePage, hasMore } from "../../src/lib/entries-pagination";

type Item = { id: string };

describe("entries pagination", () => {
  it("mergePage appends new items at the end", () => {
    const prev: Item[] = [{ id: "a" }, { id: "b" }];
    const next: Item[] = [{ id: "c" }];
    expect(mergePage(prev, next)).toEqual([{ id: "a" }, { id: "b" }, { id: "c" }]);
  });

  it("mergePage deduplicates by id (last write wins on duplicates)", () => {
    const prev: Item[] = [{ id: "a" }];
    const next: Item[] = [{ id: "a" }, { id: "b" }];
    expect(mergePage(prev, next)).toEqual([{ id: "a" }, { id: "b" }]);
  });

  it("hasMore is true when loaded < total", () => {
    expect(hasMore(50, 137)).toBe(true);
  });

  it("hasMore is false when loaded >= total", () => {
    expect(hasMore(137, 137)).toBe(false);
    expect(hasMore(200, 137)).toBe(false);
  });

  it("hasMore is false when total is 0", () => {
    expect(hasMore(0, 0)).toBe(false);
  });
});
