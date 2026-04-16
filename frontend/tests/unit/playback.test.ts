import { beforeEach, describe, expect, it, vi } from "vitest";
import { get } from "svelte/store";
import { clearCurrent, currentPlayback, setCurrent, stopAll } from "$lib/stores/playback";

describe("playback store", () => {
  beforeEach(() => stopAll());

  function makeAudio() {
    const el = document.createElement("audio");
    el.pause = vi.fn();
    return el;
  }

  it("setCurrent stores the reference", () => {
    const a = makeAudio();
    setCurrent("a", a);
    expect(get(currentPlayback)?.id).toBe("a");
  });

  it("setCurrent with a new id pauses the previous audio", () => {
    const a = makeAudio();
    const b = makeAudio();
    setCurrent("a", a);
    setCurrent("b", b);
    expect(a.pause).toHaveBeenCalledTimes(1);
    expect(get(currentPlayback)?.id).toBe("b");
  });

  it("setCurrent with same id does not pause", () => {
    const a = makeAudio();
    setCurrent("a", a);
    setCurrent("a", a);
    expect(a.pause).not.toHaveBeenCalled();
  });

  it("stopAll pauses and clears", () => {
    const a = makeAudio();
    setCurrent("a", a);
    stopAll();
    expect(a.pause).toHaveBeenCalledTimes(1);
    expect(get(currentPlayback)).toBeNull();
  });

  it("clearCurrent(id) clears only when id matches", () => {
    const a = makeAudio();
    setCurrent("a", a);
    clearCurrent("b");
    expect(get(currentPlayback)?.id).toBe("a");
    clearCurrent("a");
    expect(get(currentPlayback)).toBeNull();
    expect(a.pause).not.toHaveBeenCalled();
  });

  it("clearCurrent() without id clears unconditionally", () => {
    const a = makeAudio();
    setCurrent("a", a);
    clearCurrent();
    expect(get(currentPlayback)).toBeNull();
  });
});
