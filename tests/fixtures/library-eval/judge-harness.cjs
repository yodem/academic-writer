// Drives the judging page in a Node vm with a small stub DOM (no browser, no packages).
// Usage: node judge-harness.cjs <filled-page.html> <local|shared>
// Prints one JSON object of facts about what the page showed and exported; tests/test_library_judge_page.py asserts on it.
'use strict';
const fs = require('fs');
const vm = require('vm');

const htmlPath = process.argv[2];
const mode = process.argv[3] || 'local';
const html = fs.readFileSync(htmlPath, 'utf8');

const pairsBody = /<script type="application\/json" id="pairs">([\s\S]*?)<\/script>/.exec(html)[1];
let source = /<script>([\s\S]*?)<\/script>/.exec(html)[1];
const ids = [...html.matchAll(/<[a-z0-9]+[^>]*\sid="([^"]+)"/g)].map((match) => match[1]);

const flags = { fail: false, hold: false };
let sharedSource = source;
{
  // Stand-in for the artifact capability: proves the three-method contract is enough to run the page.
  const patched = source.replace(/function createSharedStore\(\) \{\n    return null;[^\n]*\n  \}/, `function createSharedStore() {
    var backing = window.__sharedBacking;
    function all() { return Promise.resolve(Object.keys(backing).filter(function (k) { return k.indexOf('judgments/') === 0; }).map(function (k) { return JSON.parse(backing[k]); })); }
    return { kind: 'shared', canDownload: false, load: all, list: all,
      save: function (j) {
        if (window.__flags.fail) return Promise.reject(new Error('rejected'));
        if (window.__flags.hold) return new Promise(function () {});
        backing['judgments/' + j.pair_id] = JSON.stringify(j); return Promise.resolve();
      } };
  }`);
  if (patched === source) throw new Error('createSharedStore block not found');
  sharedSource = patched;
}

class TextNode {
  constructor(data) { this.nodeType = 3; this.data = data; this.parentNode = null; }
  get textContent() { return this.data; }
}

class Element {
  constructor(tag) {
    this.nodeType = 1; this.tagName = tag.toUpperCase(); this.attrs = new Map(); this.children = [];
    this.listeners = {}; this.parentNode = null; this.value = ''; this.checked = false;
  }
  get id() { return this.attrs.get('id') || ''; }
  setAttribute(name, value) { this.attrs.set(name, String(value)); }
  getAttribute(name) { return this.attrs.has(name) ? this.attrs.get(name) : null; }
  hasAttribute(name) { return this.attrs.has(name); }
  removeAttribute(name) { this.attrs.delete(name); }
  appendChild(node) { if (node.parentNode) node.parentNode.removeChild(node); node.parentNode = this; this.children.push(node); return node; }
  removeChild(node) { this.children = this.children.filter((child) => child !== node); node.parentNode = null; return node; }
  replaceChildren(...nodes) { this.children.forEach((child) => { child.parentNode = null; }); this.children = []; nodes.forEach((node) => this.appendChild(node)); }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  get textContent() { return this.children.map((child) => child.textContent).join(''); }
  set textContent(text) { this.replaceChildren(new TextNode(String(text))); }
  focus() { this.ownerDocument.activeElement = this; }
  select() { this.selected = true; }
  scrollIntoView() { this.scrolled = true; }
  click() { this.ownerDocument.onAnchorClick(this); fire(this, 'click'); }
}

function fire(node, type) {
  const event = { type, target: node, preventDefault() {} };
  (node.listeners[type] || []).forEach((fn) => fn(event));
}
function walk(node, visit) { visit(node); (node.children || []).forEach((child) => walk(child, visit)); }
function findAll(root, test) { const out = []; walk(root, (node) => { if (node.nodeType === 1 && test(node)) out.push(node); }); return out; }
const tag = (name) => (node) => node.tagName === name.toUpperCase();
const tick = () => new Promise((resolve) => setImmediate(resolve));

function boot(storage, shared, useShared) {
  const downloads = [];
  const blobs = new Map();
  const document = {
    activeElement: null, listeners: {}, byId: new Map(), title: 'Judge the results',
    createElement(name) { const node = new Element(name); node.ownerDocument = document; return node; },
    createTextNode(text) { return new TextNode(text); },
    getElementById(id) { return document.byId.get(id) || null; },
    addEventListener(type, fn) { (document.listeners[type] = document.listeners[type] || []).push(fn); },
    onAnchorClick(node) { if (node.tagName === 'A' && node.hasAttribute('download')) downloads.push({ filename: node.getAttribute('download'), text: blobs.get(node.getAttribute('href')) }); },
  };
  document.body = document.createElement('body');
  ids.forEach((id) => { const node = document.createElement('div'); node.setAttribute('id', id); document.byId.set(id, node); document.body.appendChild(node); });
  document.byId.get('pairs').textContent = pairsBody;
  const windowListeners = {};
  const localStorage = {
    getItem: (key) => (storage.has(key) ? storage.get(key) : null),
    setItem: (key, value) => { if (storage.broken) throw new Error('blocked'); storage.set(key, String(value)); },
  };
  const window = { localStorage, addEventListener(type, fn) { (windowListeners[type] = windowListeners[type] || []).push(fn); }, __sharedBacking: shared, __flags: flags };
  let count = 0;
  const sandbox = {
    window, document, navigator: { clipboard: { writeText: async () => {} } }, setTimeout, clearTimeout, console,
    Blob: class { constructor(parts) { this.text = parts.join(''); } },
    URL: { createObjectURL(blob) { count += 1; const url = `blob:stub-${count}`; blobs.set(url, blob.text); return url; }, revokeObjectURL() {} },
  };
  vm.runInNewContext(useShared ? sharedSource : source, sandbox, { filename: 'judge-page.inline.js' });
  const app = document.byId.get('app');
  const root = () => app;
  return {
    document, downloads, root,
    pagehide() { (windowListeners.pagehide || []).forEach((fn) => fn({ type: 'pagehide' })); },
    button(label) { const found = findAll(root(), (n) => n.tagName === 'BUTTON' && n.textContent === label); if (!found.length) throw new Error(`no button ${label}`); return found[0]; },
    hasButton(label) { return findAll(root(), (n) => n.tagName === 'BUTTON' && n.textContent === label).length > 0; },
    choose(value) {
      const radios = findAll(root(), (n) => n.tagName === 'INPUT' && n.getAttribute('type') === 'radio');
      radios.forEach((radio) => { radio.checked = radio.getAttribute('value') === value; });
      fire(radios.find((radio) => radio.getAttribute('value') === value), 'change');
    },
    type(text) { const note = document.getElementById ? findAll(root(), (n) => n.getAttribute('id') === 'note')[0] : null; note.value = text; fire(note, 'input'); },
    snapshot() {
      const heading = findAll(root(), (n) => n.getAttribute('id') === 'pair-heading')[0];
      const claim = findAll(root(), tag('blockquote'))[0];
      const radios = findAll(root(), (n) => n.tagName === 'INPUT' && n.getAttribute('type') === 'radio');
      const note = findAll(root(), (n) => n.getAttribute('id') === 'note')[0];
      const results = findAll(root(), (n) => n.tagName === 'SECTION' && n.getAttribute('class') === 'result');
      const toggles = findAll(root(), (n) => n.tagName === 'BUTTON' && n.hasAttribute('aria-controls'));
      const texts = findAll(root(), (n) => /\bpage-text\b/.test(n.getAttribute('class') || ''));
      return {
        heading: heading ? heading.textContent : null,
        focused: document.activeElement === heading,
        notice: findAll(root(), (n) => n.getAttribute('class') === 'notice').map((n) => n.textContent),
        claim: claim ? { text: claim.textContent, dir: claim.getAttribute('dir') } : null,
        radios: radios.map((r) => ({ name: r.getAttribute('name'), value: r.getAttribute('value'), checked: r.checked, id: r.getAttribute('id') })),
        radioLabels: findAll(root(), (n) => n.tagName === 'LABEL' && n.getAttribute('class') === 'choice').map((n) => n.textContent),
        fieldsets: findAll(root(), tag('fieldset')).length,
        legends: findAll(root(), tag('legend')).map((n) => n.textContent),
        note: note ? { value: note.value, dir: note.getAttribute('dir'), label: findAll(root(), (n) => n.tagName === 'LABEL' && n.getAttribute('for') === 'note').length } : null,
        results: results.map((section) => ({
          labelledby: section.getAttribute('aria-labelledby'),
          heading: findAll(section, tag('h3'))[0].textContent,
          meta: findAll(section, (n) => n.getAttribute('class') === 'meta')[0].textContent,
          pageLabels: findAll(section, (n) => n.getAttribute('class') === 'page-label').map((n) => n.textContent),
          paragraphDirs: findAll(section, (n) => n.tagName === 'P' && n.parentNode && /\bpage-text\b/.test(n.parentNode.getAttribute('class') || '')).map((n) => n.getAttribute('dir')),
          empty: findAll(section, (n) => n.getAttribute('class') === 'empty').map((n) => n.textContent),
          text: section.textContent,
        })),
        toggles: toggles.map((t) => ({ label: t.textContent, expanded: t.getAttribute('aria-expanded'), controls: t.getAttribute('aria-controls') })),
        clamped: texts.map((n) => /\bclamped\b/.test(n.getAttribute('class'))),
        progress: findAll(root(), tag('progress')).map((n) => ({ value: n.getAttribute('value'), max: n.getAttribute('max'), label: n.getAttribute('aria-label') })),
        buttons: findAll(root(), tag('button')).map((n) => n.textContent),
        allText: root().textContent,
      };
    },
    exportText() { return findAll(root(), (n) => n.getAttribute('id') === 'export-json')[0].value; },
    toggleFirst() { const toggle = findAll(root(), (n) => n.tagName === 'BUTTON' && n.hasAttribute('aria-controls'))[0]; fire(toggle, 'click'); },
    gridButton(n) { const grid = findAll(root(), (x) => x.tagName === 'UL')[0]; const btn = findAll(grid, tag('button'))[n - 1]; return { label: btn.getAttribute('aria-label'), click: () => fire(btn, 'click') }; },
    click(label) { fire(this.button(label), 'click'); },
  };
}

async function main() {
  const storage = new Map();
  const shared = {};
  const out = { mode };

  // Every pair, in order, in a throwaway session.
  out.sweep = [];
  const sweep = boot(new Map(), {}, false); await tick();
  for (let guard = 0; guard < 50; guard += 1) {
    const view = sweep.snapshot();
    out.sweep.push({ heading: view.heading, claim: view.claim, radios: view.radios, results: view.results.map((r) => ({ heading: r.heading, meta: r.meta, labelledby: r.labelledby })), fieldsets: view.fieldsets, legends: view.legends, note: view.note });
    if (!sweep.hasButton('Next')) break;
    sweep.click('Next'); await tick();
  }

  let page = boot(storage, shared, mode === 'shared'); await tick();
  out.first = page.snapshot();
  // The long page text starts collapsed and opens on request.
  page.click('Next'); await tick();
  out.second_before_toggle = page.snapshot();
  page.toggleFirst();
  out.second_after_toggle = page.snapshot();
  page.click('Previous'); await tick();
  page.choose('B'); page.type('הערה בעברית: ב טוב יותר'); page.pagehide(); await tick();
  out.first_after_answer = page.snapshot();
  page.click('Next'); await tick();
  page.choose('same'); await tick();
  page.click('Next'); await tick();
  out.third = page.snapshot();
  page.click('Skip this pair'); await tick();
  out.fourth = page.snapshot();

  // Close the tab and open the page again against the same store.
  page = boot(storage, shared, mode === 'shared'); await tick();
  out.resumed = page.snapshot();
  page.click('Previous'); await tick();
  out.resumed_prev = page.snapshot();
  page.click('Review and export'); await tick();
  out.export_view = page.snapshot();
  out.export_text = page.exportText();
  out.has_download = page.hasButton('Download judgments');
  out.has_copy = page.hasButton('Copy judgments');
  out.grid_first = page.gridButton(1).label;
  page.gridButton(1).click(); await tick();
  out.after_jump = page.snapshot();
  page.click('Review and export'); await tick();
  if (page.hasButton('Download judgments')) { page.click('Download judgments'); out.downloads = page.downloads; } else out.downloads = [];
  out.shared_keys = Object.keys(shared).sort();

  // A browser that refuses storage: the page still works and tells the judge.
  const blocked = new Map(); blocked.broken = true;
  const lone = boot(blocked, {}, false); await tick();
  lone.choose('A'); await tick();
  out.blocked_notice = lone.snapshot().allText;
  process.stdout.write(`${JSON.stringify(out)}\n`);
}

const PREFIX = `judge-page:ev-20261016-a:${'ab'.repeat(6)}`;
const GOOD_AT = '2026-10-16T08:00:00.000Z';

async function edge() {
  const out = {};
  // A resumed judgment keeps its saved note when only the verdict changes.
  const stored = new Map([[`${PREFIX}:judgments`, JSON.stringify([{ pair_id: 'p01', verdict: 'B', note: 'saved note', at: GOOD_AT }])]]);
  let page = boot(stored, {}, false); await tick();
  page.click('Previous'); await tick();
  out.note_shown = page.snapshot().note.value;
  page.choose('A'); await tick();
  page.click('Review and export'); await tick();
  out.note_kept = page.exportText();

  // A shared store that rejects saves: failures stay visible and the summary does not claim they are saved.
  flags.fail = true;
  const shared = {};
  page = boot(new Map(), shared, true); await tick();
  page.choose('B'); await tick();
  out.fail_pair = page.snapshot();
  page.click('Next'); await tick();
  out.fail_other_pair = page.snapshot();
  page.click('Review and export'); await tick();
  out.fail_export = page.snapshot();
  out.fail_export_text = page.exportText();
  page.click('Try saving pair 1 again'); await tick();
  out.fail_retry_still_failing = page.snapshot();
  out.fail_keys_while_failing = Object.keys(shared);
  flags.fail = false;
  page.click('Try saving pair 1 again'); await tick();
  out.fail_retry_ok = page.snapshot();
  out.fail_keys_after = Object.keys(shared);

  // A save that never answers: the page says it is still saving.
  flags.hold = true;
  page = boot(new Map(), {}, true); await tick();
  page.choose('same'); await tick();
  page.click('Review and export'); await tick();
  out.hold_export = page.snapshot();
  flags.hold = false;

  // Restored records that do not fit the schema are dropped and reported.
  const bad = [
    { pair_id: 'p01', verdict: 'B', note: 'ok', at: 123 },
    { pair_id: 'p99', verdict: 'A', note: '', at: GOOD_AT },
    { pair_id: 'p02', verdict: 'bogus', note: '', at: GOOD_AT },
    { pair_id: 'p03', verdict: 'A', note: 7, at: GOOD_AT },
    { pair_id: 'p05', verdict: 'A', note: 'x'.repeat(2001), at: GOOD_AT },
    { pair_id: 'p04', verdict: 'same', note: '', at: GOOD_AT },
    { pair_id: 'p06', verdict: 'neither', note: 'fine', at: GOOD_AT, extra: 'zzz' },
    null, 'text',
  ];
  page = boot(new Map([[`${PREFIX}:judgments`, JSON.stringify(bad)]]), {}, false); await tick();
  out.bad_local_view = page.snapshot();
  page.click('Review and export'); await tick();
  out.bad_local_export = page.exportText();
  out.bad_local_summary = page.snapshot().allText;
  const backing = {};
  bad.forEach((item, index) => { backing[`judgments/${item && item.pair_id ? item.pair_id : `x${index}`}`] = JSON.stringify(item); });
  page = boot(new Map(), backing, true); await tick();
  page.click('Review and export'); await tick();
  out.bad_shared_export = page.exportText();
  process.stdout.write(`${JSON.stringify(out)}\n`);
}

(mode === 'edge' ? edge() : main()).catch((error) => { process.stderr.write(`${error.stack}\n`); process.exit(1); });
