import { expect, test } from "@playwright/test";

test.skip(!process.env.E2E_LIVE, "requires running backend + TTS endpoint");

test("TTS: settings form shows voice + speed fields", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="password"]', process.env.APP_PASSWORD ?? "testpw");
  await page.click('button[type="submit"]');
  await page.goto("/settings");
  await expect(page.getByText("TTS-Stimme & Tempo")).toBeVisible();
  await expect(page.locator('input[placeholder*="alloy"]')).toBeVisible();
});

test("TTS: AudioPlayer renders on entry detail", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="password"]', process.env.APP_PASSWORD ?? "testpw");
  await page.click('button[type="submit"]');
  await page.goto("/entries");
  const firstEntry = page.locator("a.card").first();
  await firstEntry.click();
  await expect(page.getByRole("button", { name: "Vorlesen" })).toBeVisible();
});

test("TTS: auto-play toggle toggles aria-checked", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="password"]', process.env.APP_PASSWORD ?? "testpw");
  await page.click('button[type="submit"]');
  await page.goto("/new");
  const toggle = page.getByRole("switch", { name: "Auto-Vorlesen" });
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "true");
});
