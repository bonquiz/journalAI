import { describe, it, expect } from "vitest";
import { exportUrl } from "../../src/lib/portability";

describe("portability client", () => {
  it("exportUrl returns relative path to export endpoint", () => {
    expect(exportUrl()).toBe("/api/export");
  });
});
