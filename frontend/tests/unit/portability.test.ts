import { describe, it, expect, vi, beforeEach } from "vitest";
import { exportUrl, importZip, type ImportResult } from "../../src/lib/portability";

describe("portability client", () => {
  it("exportUrl returns relative path to export endpoint", () => {
    expect(exportUrl()).toBe("/api/export");
  });

  describe("importZip", () => {
    beforeEach(() => {
      vi.restoreAllMocks();
    });

    it("POSTs multipart with file, mode, dry_run and returns parsed JSON", async () => {
      const mock: ImportResult = {
        dry_run: true, mode: "skip", total_in_file: 3,
        new_entries: 3, conflicts: 0, would_apply: 3,
        tags_new: 1, tags_merged: 0, errors: [],
      };
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true, json: async () => mock, status: 200,
      });
      vi.stubGlobal("fetch", fetchMock);

      const file = new File([new Uint8Array([1, 2, 3])], "export.zip");
      const result = await importZip(file, "skip", true);

      expect(result).toEqual(mock);
      expect(fetchMock).toHaveBeenCalledOnce();
      const [url, init] = fetchMock.mock.calls[0];
      expect(url).toBe("/api/import");
      expect(init.method).toBe("POST");
      const body = init.body as FormData;
      expect(body.get("mode")).toBe("skip");
      expect(body.get("dry_run")).toBe("true");
      expect(body.get("file")).toBe(file);
    });

    it("throws on non-OK response", async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: false, status: 400, json: async () => ({ detail: "bad zip" }),
      });
      vi.stubGlobal("fetch", fetchMock);

      const file = new File([new Uint8Array([0])], "bad.zip");
      await expect(importZip(file, "skip", false)).rejects.toThrow(/bad zip/);
    });
  });
});
