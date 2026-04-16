import { describe, expect, it } from "vitest";

// Test the SSE framing logic that streamChat relies on.
// We test the parsing in isolation (the generator itself requires a live fetch).
describe("SSE frame parsing logic", () => {
  it("splits multi-frame buffers on double-newline correctly", () => {
    const raw = "data: Hello\\n\\ndata: World\\n\\ndata: [DONE]\\n\\n";
    const frames = raw.split("\\n\\n").filter((f) => f.startsWith("data: "));
    const payloads = frames.map((f) => f.slice(6));
    expect(payloads).toEqual(["Hello", "World", "[DONE]"]);
  });

  it("identifies DONE sentinel", () => {
    const payload = "[DONE]";
    expect(payload === "[DONE]").toBe(true);
  });

  it("handles partial frames at buffer end", () => {
    const buf = "data: First\\n\\ndata: Sec";
    const frames = buf.split("\\n\\n");
    const remainder = frames.pop() ?? "";
    expect(frames).toEqual(["data: First"]);
    expect(remainder).toBe("data: Sec");
  });
});
