import { expect, test } from "@playwright/test";

test.skip(!process.env.E2E_LIVE, "requires running backend + mock LLM endpoint");

test("create and delete an entry", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="password"]', "testpw");
  await page.click('button[type="submit"]');

  await page.click("text=Eintrag erfassen");
  await page.fill("textarea", "Heute war ein ruhiger Tag.");
  await page.click("text=Senden");
  await page.waitForTimeout(500);
  await page.click("text=Eintrag jetzt speichern");
  await page.click("text=So speichern");
  await expect(page).toHaveURL(/\/entries/);
});
