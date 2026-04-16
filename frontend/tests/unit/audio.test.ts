import { describe, expect, it } from "vitest";
import { Recorder, transcribe } from "$lib/audio";

describe("audio module", () => {
  it("exports Recorder class and transcribe function", () => {
    expect(typeof Recorder).toBe("function");
    expect(typeof transcribe).toBe("function");
  });
});
