import * as fs from "node:fs";
import * as path from "node:path";
import { test, expect } from "@playwright/test";
import { open, prepare, registry } from "./fixtures";

// These specs write to the fixture registry, so each browser project has its own copy of the student fixture.
test.describe.configure({ mode: "serial" });
const instance = (name: string) => `student-${name}`;

const taskStatus = (inst: string) => {
  const course = JSON.parse(fs.readFileSync(path.join(registry(inst), "alpha.json"), "utf8"));
  return (course.tasks || []).map((t: { status?: string }) => t.status);
};

test("submit then undo within 5 seconds restores the task", async ({ page }, info) => {
  const inst = instance(info.project.name);
  await prepare(page);
  await open(page, inst, "course/alpha");
  const done = page.locator("[data-done]").first();
  await done.click();
  await expect(page.locator("[data-undo]").first()).toBeVisible();
  await expect.poll(() => taskStatus(inst)).toContain("submitted");

  const undo = page.locator("#toastUndo");
  await expect(undo).toBeVisible();
  await undo.click();
  await expect.poll(() => taskStatus(inst), { timeout: 5000 }).not.toContain("submitted");
  await expect(page.locator("[data-done]").first()).toBeVisible();
});

test("fetching a selected source writes a queue/fetch job", async ({ page }, info) => {
  const inst = instance(info.project.name);
  const queue = path.join(registry(inst), "queue", "fetch");
  await prepare(page);
  await open(page, inst, "course/alpha");
  await page.locator("input[data-src]").first().check();
  await page.locator("#fetchBtn").click();
  await expect.poll(() => (fs.existsSync(queue) ? fs.readdirSync(queue).filter((f) => f.endsWith(".json")).length : 0)).toBeGreaterThan(0);
  const job = JSON.parse(fs.readFileSync(path.join(queue, fs.readdirSync(queue).filter((f) => f.endsWith(".json"))[0]), "utf8"));
  expect(JSON.stringify(job)).toContain("alpha");
});
