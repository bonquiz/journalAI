import { expect, test } from "@playwright/test";

test.skip(!process.env.E2E_LIVE, "requires running backend");

test("countdown is visible after login", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="password"]', "testpw");
  await page.click('button[type="submit"]');
  await expect(page.locator(".countdown")).toBeVisible();
});
