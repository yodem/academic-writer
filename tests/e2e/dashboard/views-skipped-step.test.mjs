// A skipped step (for example redraft in a finished write run) must read "skipped", never "unknown".
//   node --test tests/e2e/dashboard/views-skipped-step.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../src/scripts/courses/dashboard");
const read = (f) => fs.readFileSync(path.join(DIR, f), "utf8");
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// Real STATUS table from core.js, so a missing key shows up as the unknown fallback exactly as in the page.
const coreSrc = read("views/core.js");
const statusTable = vm.runInNewContext("(" + /const STATUS = (\{[\s\S]*?\n\});/.exec(coreSrc)[1] + ")");

function loadWriting() {
  const AW = {
    views: {}, esc, b: (s) => `<bdi>${esc(s)}</bdi>`, auto: (s) => `<bdi dir="auto">${esc(s)}</bdi>`,
    status: (k, w) => { const s = statusTable[k] || statusTable.unknown; return `<span class="st ${s.cls}"><span class="g">${s.g}</span> <span class="w">${esc(w || s.w)}</span></span>`; },
    stepBar: () => "", runProgress: () => ({ total: 3, done: 2, index: 3, current: null }), flowWord: (f) => f, stepWord: (f, id) => id,
    D: (iso) => new Date(iso + "T12:00:00"), DN: Array(7).fill("יום"), MONTH: Array(12).fill("בחודש"), shortWhen: () => "", localParts: () => ({}), baseName: (p) => p, dur: () => "", cost: () => "", tokens: () => "", toast() {},
  };
  vm.runInNewContext(read("views/writing.js"), { window: { AW }, console });
  return AW.views.writing;
}

test("core.js: STATUS has a skipped entry with its own plain word", () => {
  assert.ok(statusTable.skipped, "STATUS.skipped missing");
  assert.notEqual(statusTable.skipped.w, statusTable.unknown.w);
});

test("core.js: stepBar gives a skipped step its own class", () => {
  assert.match(coreSrc, /const cls = \{[^}]*skipped:\s*'s'/);
  assert.match(read("app.css"), /\.steps i\.s\{/);
});

test("writing.js: a skipped step shows the skipped word, not unknown", () => {
  const view = loadWriting();
  const el = { innerHTML: "", querySelectorAll: () => [] };
  const run = { workspace: "/w/a", flow: "write", status: "done", started: null, steps: [{ id: "draft", state: "done" }, { id: "redraft", state: "skipped" }] };
  view({ today: "2026-10-18", writing: { active: [run], history: [] }, workspaces: [] }, el);
  const li = el.innerHTML.match(/<li><span class="n">[\s\S]*?<\/li>/g);
  assert.equal(li.length, 2);
  assert.ok(!li[1].includes(statusTable.unknown.w), li[1]);
  assert.ok(li[1].includes(statusTable.skipped.w), li[1]);
  assert.ok(li[1].includes('<span class="meta">' + statusTable.skipped.w + "</span>"), li[1]);
});
