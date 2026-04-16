import { expect, test } from "@playwright/test";

test.skip(!process.env.E2E_LIVE, "requires running backend with APP_PASSWORD=testpw");

test("login redirects to home", async ({ page }) => {
  await page.goto("/login");
  await page.fill('input[type="password"]', "testpw");
  await page.click('button[type="submit"]');
  await expect(page).toHaveURL("/");
  await expect(page.getByText("Eintrag erfassen")).toBeVisible();
});
