import { expect, test, type Page } from "@playwright/test";

/**
 * Login helper with rate-limit (429) retry.
 *
 * The backend limits POST /api/auth/login to 5/minute per IP. When running the
 * full E2E suite sequentially, later tests can hit the limit. If the login form
 * still shows the password input after submit, we wait for the rate-limit
 * window to roll over and retry once. The helper bumps the per-test timeout so
 * the 62s wait fits.
 */
export async function login(page: Page): Promise<void> {
  test.setTimeout((test.info().timeout || 30_000) + 90_000);
  const password = process.env.APP_PASSWORD ?? "testpw";

  const attempt = async () => {
    await page.goto("/login");
    await page.fill('input[type="password"]', password);
    await page.click('button[type="submit"]');
    try {
      await page.waitForURL("/", { timeout: 5_000 });
      return true;
    } catch {
      return false;
    }
  };

  if (await attempt()) return;
  // Rate-limit window is 60s; wait and try again.
  await page.waitForTimeout(62_000);
  await attempt();
  await expect(page).toHaveURL("/");
}
