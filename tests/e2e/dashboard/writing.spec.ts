import { test, expect } from "@playwright/test";
import { open, prepare } from "./fixtures";

// Read-only: the lecturer fixture is never changed, /api/state is rewritten in the browser only.
type Run = { steps: Array<{ id: string; state: string }>; units: Array<Record<string, string>>; run: string; workspace: string; docx?: string };
type State = { writing: { active: Run[]; history: Run[] } };

async function withState(page: import("@playwright/test").Page, edit: (s: State) => void) {
  await page.route(/\/api\/state(\?|$)/, async (route) => {
    const response = await route.fetch();
    const body = (await response.json()) as State;
    edit(body);
    await route.fulfill({ response, json: body });
  });
}

test("unit boxes say passed or rejected, with the plain reason; a skipped step is a skipped step", async ({ page }) => {
  await prepare(page);
  await withState(page, (s) => {
    const run = s.writing.active[0];
    run.units = [
      { id: "intro", state: "passed" },
      { id: "U1", state: "rejected", reason: "אין הערת שוליים למקור" },
    ];
    run.steps = run.steps.map((st) => (st.id === "redraft" ? { ...st, state: "skipped" } : st));
  });
  await open(page, "lecturer", "writing");
  const units = page.locator("article.run .units .unit");
  await expect(units.nth(0)).toContainText("עבר בדיקה");
  await expect(units.nth(0)).toContainText("✓");
  await expect(units.nth(1)).toContainText("נדחה");
  await expect(units.nth(1)).toContainText("✗");
  await expect(units.nth(1)).toContainText("אין הערת שוליים למקור");
  const skipped = page.locator("article.run .slist li", { hasText: "כתיבה מחדש" });
  await expect(skipped).toContainText("↷");
  await expect(skipped).toContainText("דולג");
  await expect(skipped).not.toContainText("בתור");
  await expect(page.locator("article.run .steps i.s")).toHaveCount(1);
});

test("history offers opening the Word file, and copying the path stays as the fallback", async ({ page }) => {
  await prepare(page);
  const posted: Array<Record<string, string>> = [];
  await page.route(/\/api\/open$/, async (route) => {
    posted.push(route.request().postDataJSON());
    await route.fulfill({ status: 200, json: { ok: true, name: "article.docx" } });
  });
  await open(page, "lecturer", "writing");
  const row = page.locator("tbody tr", { has: page.locator("[data-open]") }).first();
  await expect(row.locator("[data-copy]")).toBeVisible();
  await row.locator("[data-open]").click();
  await expect.poll(() => posted.length).toBe(1);
  expect(Object.keys(posted[0]).sort()).toEqual(["run", "workspace"]);
  await expect(page.locator("#toast")).toContainText("נפתח");
});

test("when the file cannot be opened the author is told, in plain words", async ({ page }) => {
  await prepare(page);
  await open(page, "lecturer", "writing"); // the fixture's .docx files do not exist on disk: the server refuses
  await page.locator("[data-open]").first().click();
  await expect(page.locator("#toast")).toContainText("לא הצלחתי לפתוח");
});
