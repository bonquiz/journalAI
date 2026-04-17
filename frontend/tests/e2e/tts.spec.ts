import { expect, test } from "@playwright/test";
import { login } from "./helpers";

test.skip(!process.env.E2E_LIVE, "requires running backend + TTS endpoint");

test("TTS: settings form shows voice + speed fields", async ({ page }) => {
  await login(page);
  await page.goto("/settings");
  await expect(page.getByText("TTS-Stimme & Tempo")).toBeVisible();
  await expect(page.locator('input[placeholder*="alloy"]')).toBeVisible();
});

test("TTS: AudioPlayer renders on entry detail", async ({ page }) => {
  await login(page);
  await page.goto("/entries");
  const firstEntry = page.locator("a.card").first();
  await firstEntry.waitFor({ state: "visible" });
  await firstEntry.click();
  await expect(page.getByRole("button", { name: "Vorlesen" })).toBeVisible();
});

test("TTS: auto-play toggle toggles aria-checked", async ({ page }) => {
  await login(page);
  await page.goto("/new");
  const toggle = page.getByRole("switch", { name: "Auto-Vorlesen" });
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "true");
});
