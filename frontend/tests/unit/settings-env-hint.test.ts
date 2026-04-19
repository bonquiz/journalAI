import { describe, it, expect } from "vitest";
import { envHint } from "../../src/lib/settings-env-hint";

describe("envHint", () => {
  it("returns null when DB value is set", () => {
    expect(envHint("http://custom/v1", "http://ollama:11434/v1")).toBeNull();
  });

  it("returns the resolved value when DB value is empty", () => {
    expect(envHint("", "http://ollama:11434/v1")).toBe("http://ollama:11434/v1");
    expect(envHint(null, "http://ollama:11434/v1")).toBe("http://ollama:11434/v1");
  });

  it("returns null when neither is set", () => {
    expect(envHint("", null)).toBeNull();
    expect(envHint("", "")).toBeNull();
  });

  it("does not leak resolved when DB equals resolved (redundant hint)", () => {
    expect(envHint("http://ollama:11434/v1", "http://ollama:11434/v1")).toBeNull();
  });
});
