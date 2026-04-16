import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AutoPlayToggle from "$lib/components/AutoPlayToggle.svelte";
import PlayMessageButton from "$lib/components/PlayMessageButton.svelte";

function mockFetchAudio() {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(new Blob([new Uint8Array([0xff, 0xfb, 0x00])], { type: "audio/mpeg" }),
                  { status: 200, headers: { "Content-Type": "audio/mpeg" } }),
  );
}

beforeEach(() => {
  document.cookie = "csrf=testcsrf; path=/";
  URL.createObjectURL = vi.fn(() => "blob:mock");
  URL.revokeObjectURL = vi.fn();
  HTMLMediaElement.prototype.play = vi.fn().mockResolvedValue(undefined);
  HTMLMediaElement.prototype.pause = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AutoPlayToggle", () => {
  it("renders with aria-checked reflecting value", () => {
    const { getByRole } = render(AutoPlayToggle, { props: { value: false } });
    expect(getByRole("switch")).toHaveAttribute("aria-checked", "false");
  });

  it("click flips the value via two-way binding", async () => {
    const { getByRole } = render(AutoPlayToggle, { props: { value: false } });
    await fireEvent.click(getByRole("switch"));
    expect(getByRole("switch")).toHaveAttribute("aria-checked", "true");
  });
});

describe("PlayMessageButton", () => {
  it("shows idle state initially", () => {
    const { getByRole } = render(PlayMessageButton, { props: { text: "Hallo" } });
    expect(getByRole("button")).toHaveAttribute("aria-pressed", "false");
  });

  it("fetches + plays on first click", async () => {
    const f = mockFetchAudio();
    const { getByRole } = render(PlayMessageButton, { props: { text: "Hallo Welt" } });
    await fireEvent.click(getByRole("button"));
    await new Promise((r) => setTimeout(r, 50));
    expect(f).toHaveBeenCalled();
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });

  it("autoplay prop triggers playback automatically", async () => {
    const f = mockFetchAudio();
    render(PlayMessageButton, { props: { text: "Automatisch", autoplay: true } });
    await new Promise((r) => setTimeout(r, 100));
    expect(f).toHaveBeenCalled();
    expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });
});
