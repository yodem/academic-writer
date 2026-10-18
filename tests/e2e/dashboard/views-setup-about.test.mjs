// Unit test for views/setup.js and views/about.js: runs each view script against a stub of window.AW.
//   node --test tests/e2e/dashboard/views-setup-about.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../src/scripts/courses/dashboard");
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const STATUS = { ok: ["✓", "מוכן"], missing: ["✗", "חסר"], waiting: ["◐", "ממתין"], unknown: ["?", "לא ידוע"] };

function load(name, aboutData) {
  const AW = {
    views: {}, esc, b: (s) => `<bdi>${esc(s)}</bdi>`, auto: (s) => `<bdi dir="auto">${esc(s)}</bdi>`,
    status: (k, w) => { const s = STATUS[k] || STATUS.unknown; return `<span class="st ${k}"><span class="g">${s[0]}</span> <span class="w">${esc(w || s[1])}</span></span>`; },
    D: (iso) => new Date(iso + "T12:00:00"), DN: ["ראשון", "שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת"],
    MONTH: Array(12).fill("בחודש"), toast() {},
    api: async () => { if (aboutData instanceof Error) throw aboutData; return aboutData; },
  };
  const el = { innerHTML: "", querySelectorAll: () => [], dataset: {} };
  const ctx = { window: { AW }, navigator: {}, console };
  vm.runInNewContext(fs.readFileSync(path.join(DIR, "views", name + ".js"), "utf8"), ctx);
  return { view: AW.views[name], el };
}
const tick = () => new Promise((r) => setTimeout(r, 0));

const CHECKS = [
  { id: "python", label_he: "Python", ok: true, optional: false, found: "3.12", required: "3.9+", reason_he: null, fix: null },
  { id: "hspell", label_he: "בדיקת איות <בעברית>", ok: false, optional: false, found: null, required: null, reason_he: "בודק האיות לא מותקן", fix: "/academic-writer:setup" },
  { id: "notebooklm", label_he: "NotebookLM", ok: false, optional: true, found: null, required: null, reason_he: "לא מותקן", fix: "/academic-writer:setup" },
  { id: "nightly-job", label_he: "משימת הלילה", ok: null, optional: true, found: null, required: null, reason_he: "רק ב-macOS", fix: null },
];
const HOME = { name: "דנה", role: "student", missing: false, configured: true };

test("setup registers a view", () => { assert.equal(typeof load("setup").view, "function"); });

test("setup: every check is glyph + word, with its reason and fix command, and the label is escaped", () => {
  const { view, el } = load("setup");
  view({ setup: { complete: false, checks: CHECKS }, home: HOME, today: "2026-10-16" }, el);
  assert.match(el.innerHTML, /✓/); assert.match(el.innerHTML, /✗/); assert.match(el.innerHTML, /◐/);
  assert.match(el.innerHTML, /בודק האיות לא מותקן/);
  assert.match(el.innerHTML, /<code>\/academic-writer:setup<\/code>/);
  assert.ok(!el.innerHTML.includes("<בעברית>"));
  assert.ok(!/style=/.test(el.innerHTML));
});

test("setup: required first, optional apart; incomplete says what is missing", () => {
  const { view, el } = load("setup");
  view({ setup: { complete: false, checks: CHECKS }, home: HOME, today: "2026-10-16" }, el);
  assert.ok(el.innerHTML.indexOf("חובה") !== -1 && el.innerHTML.indexOf("חובה") < el.innerHTML.indexOf("NotebookLM"));
  assert.match(el.innerHTML, /חסר/);
});

test("setup: complete state and unreachable home and empty checks", () => {
  let t = load("setup");
  t.view({ setup: { complete: true, checks: [CHECKS[0]] }, home: HOME, today: "2026-10-16" }, t.el);
  assert.match(t.el.innerHTML, /הכול מוכן/);
  t = load("setup");
  t.view({ setup: { complete: false, checks: [CHECKS[0]] }, home: { ...HOME, missing: true }, today: "2026-10-16" }, t.el);
  assert.match(t.el.innerHTML, /תיקיית הבית לא נמצאה/);
  t = load("setup");
  t.view({ setup: { complete: null, checks: [] }, today: "2026-10-16" }, t.el);
  assert.match(t.el.innerHTML, /עוד לא נבדק/);
});

const ABOUT = {
  version: "0.17.1", guide: "/academic-writer:intro",
  features: [
    { id: "f1", name_he: "כתיבה", description_he: "כותב <מאמר>", command: "/academic-writer:write", status: "ok", tested: "e2e",
      subfeatures: [{ id: "s1", name: "Draft gate", status: "partial", tested: "not tested yet", subfeatures: [] }] },
    { id: "f2", name_he: "קול", description_he: "סגנון", command: "/academic-writer:voice", status: "partial", tested: "manual", subfeatures: [] },
  ],
  onboarding: { student: ["צעד <א>"], lecturer: ["צעד ב"], researcher: ["צעד ג"] },
};

test("about renders features with status, command and how it is tested", async () => {
  const { view, el } = load("about", ABOUT);
  view({ home: HOME, today: "2026-10-16" }, el); await tick();
  const h = el.innerHTML;
  assert.match(h, /כתיבה/); assert.match(h, /<code>\/academic-writer:write<\/code>/);
  assert.match(h, /✓/); assert.match(h, /◐/);
  assert.match(h, /מקצה לקצה/); assert.match(h, /ידנית/); assert.match(h, /עוד לא נבדק/);
  assert.ok(!h.includes("<מאמר>") && !h.includes("<א>"));
  assert.match(h, /0\.17\.1/);
});

test("about puts the viewer's role first in onboarding and links the guide", async () => {
  const { view, el } = load("about", ABOUT);
  view({ home: { ...HOME, role: "lecturer" }, today: "2026-10-16" }, el); await tick();
  const h = el.innerHTML;
  assert.ok(h.indexOf("צעד ב") !== -1 && h.indexOf("צעד ב") < h.indexOf("צעד ג"));
  assert.match(h, /\/academic-writer:intro/);
});

test("about: failed load says so in plain words", async () => {
  const { view, el } = load("about", new Error("HTTP 500"));
  view({ home: HOME, today: "2026-10-16" }, el); await tick();
  assert.match(el.innerHTML, /לא הצלחתי לקרוא/);
});
