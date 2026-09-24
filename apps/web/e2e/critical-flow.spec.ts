import { expect, test } from "@playwright/test";

// Serial: later steps use the leads created by the search.
test.describe.configure({ mode: "serial" });

test("search → results (demo provider)", async ({ page }) => {
  await page.goto("/search");
  await expect(page.getByText(/Demo mode/).first()).toBeVisible();
  await page.getByLabel("Location").fill("Varna");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page).toHaveURL(/job=\d+/);
  await expect(page.getByText("Completed", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
  const cards = page.locator('[role="link"][aria-label^="Demo"]');
  await expect(cards.first()).toBeVisible();
  expect(await cards.count()).toBeGreaterThan(5);

  // Re-running the same search must not create duplicates.
  await page.goto("/leads?city=Varna");
  const header = page.getByRole("heading", { level: 1 });
  await expect(header).toHaveText(/Leads \d+/);
  const before = await header.innerText();
  await page.goto("/search");
  await page.getByLabel("Location").fill("Varna");
  await page.getByRole("button", { name: "Search", exact: true }).click();
  await expect(page.getByText("Completed", { exact: true }).first()).toBeVisible({ timeout: 60_000 });
  await page.goto("/leads?city=Varna");
  await expect(header).toHaveText(/Leads \d+/);
  await expect(header).toHaveText(before);
});

test("lead filtering, detail and call outcome", async ({ page }) => {
  await page.goto("/leads");
  await page.getByRole("button", { name: "No website", exact: true }).click();
  await expect(page).toHaveURL(/opportunity=NO_WEBSITE/);
  const firstRow = page.locator("tbody tr").first();
  await expect(firstRow).toContainText("NO_WEBSITE");
  await firstRow.click();

  const why = page.locator('[data-slot="card"]', { hasText: "Why this lead?" });
  await expect(why).toContainText("NO_WEBSITE");
  await expect(why).toContainText(/No website listed|social media page|link page|profile, not an own website/);
  await expect(page.getByText("Suggested pitch")).toBeVisible();
  await page.getByLabel("Call notes").fill("E2E: asked for examples");
  await page.getByRole("button", { name: "Interested", exact: true }).click();
  await expect(page.getByText(/Interested recorded/)).toBeVisible();
  await expect(page.getByLabel("Lead status")).toContainText("Interested");
  await expect(page.getByText("E2E: asked for examples").first()).toBeVisible();
});

test("keyboard calling session", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Start calling session" }).first().click();
  await expect(page.getByText(/leads match/)).toBeVisible();
  await page.getByRole("button", { name: "Start session" }).click();
  await expect(page).toHaveURL(/\/calling\/\d+/);
  await expect(page.getByText("Why we're calling")).toBeVisible();

  const name = page.getByRole("heading", { level: 1 });
  const first = await name.innerText();
  await page.keyboard.press("n");
  await expect(name).not.toHaveText(first);
  await expect(page.getByText(/1\s+calls/)).toBeVisible();

  await page.keyboard.press("d");
  await expect(page.getByText(/permanently mark this number/)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByText(/permanently mark this number/)).toBeHidden();
});

test("CSV export of the filtered list", async ({ page }) => {
  await page.goto("/leads?priority=HOT");
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("link", { name: "Export CSV" }).click()]);
  expect(download.suggestedFilename()).toMatch(/^leads-\d{8}-\d{4}\.csv$/);
  const path = await download.path();
  const fs = await import("node:fs/promises");
  const content = await fs.readFile(path!, "utf8");
  expect(content.charCodeAt(0)).toBe(0xfeff);
  expect(content).toContain("Business,Category,Phone,International Phone");
  expect(content).toContain(",HOT,");
  expect(content).not.toContain(",COLD,");
});
