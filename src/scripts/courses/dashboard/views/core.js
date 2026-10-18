/* Dashboard core: data, router, theme, palette, keyboard, live updates, submit + undo, fetch queue.

   Every view file is a plain script that registers one function:

       window.AW.views.<name> = (state, el) => void      // fill `el` (the #view mount) with the page

   `name` is one of: overview timeline courses course writing setup about. core.js loads a view's script the
   first time its route is shown, so the shell does not have to list them.

   Shared helpers a view may use (all on window.AW):
     data      state() course(slug) task(key) tkey(t) load(force) weekState(isoMonday) api(path, body) go(hash)
     text      esc b auto  (escape, <bdi>, <bdi dir=auto>)   fmt: dur(sec) cost(usd) tokens(n)
     dates     D isoOf addDays dm dayDiff rel today effDate dueHTML dueClass fromIso localParts shortWhen baseName  DL DN MONTH
     marks     status(key, word) hueClass(hue) TICK CARET NO titleHTML(t) glossHTML(t)
     runs      flowWord(flow) stepWord(flow, id) stepBar(run) runProgress(run) runWhen(run)
     actions   markDone(key) undoDone(key) queueFetch(slug, boxes) toast(html, undoFn, ms)
     viewer    S (per-browser state, saved with saveS())  saveS()
     ink       inkify(root, mode) bidiFix(root)
   Course colours reach the page as classes (c-teal ...), never inline styles: the CSP forbids style attributes. */
(() => {
'use strict';
const AW = window.AW = window.AW || {};
AW.views = AW.views || {};

/* ================= constants ================= */
const DL = ['א׳','ב׳','ג׳','ד׳','ה׳','ו׳','ש׳'];
const DN = ['ראשון','שני','שלישי','רביעי','חמישי','שישי','שבת'];
const MONTH = ['בינואר','בפברואר','במרץ','באפריל','במאי','ביוני','ביולי','באוגוסט','בספטמבר','באוקטובר','בנובמבר','בדצמבר'];
const HUES = ['teal','coral','violet','blue','ochre','rose','olive','slate'];
const LABEL = {overview:'סקירה', timeline:'ציר זמן', courses:'קורסים', course:'קורס', writing:'כתיבה', setup:'הגדרה', about:'אודות'};
const KNOWN = Object.keys(LABEL);
const LEGACY = {agenda:'timeline'};
const BRAND = 'שולחן הלימודים';
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const b = s => `<bdi>${esc(s)}</bdi>`;
/* a course code such as BIBL-204 stays one unbroken run, so a wrapped Hebrew title cannot split it */
const auto = s => `<bdi dir="auto">${esc(s).replace(/[A-Za-z]{2,}-\d+/g, m => `<bdi>${m}</bdi>`)}</bdi>`;
const $ = (s, r=document) => r.querySelector(s), $$ = (s, r=document) => [...r.querySelectorAll(s)];
const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

/* ================= per-viewer state (this browser only; never required) ================= */
const KEY = 'aw.dashboard.v2';
let S = {theme:null, moved:{}, lastCourse:null, inked:{}};
try { const raw = localStorage.getItem(KEY); if (raw) S = Object.assign(S, JSON.parse(raw)); } catch(e) {}
if (!S || typeof S !== 'object') S = {theme:null, moved:{}, lastCourse:null, inked:{}};
/* saved moves are keyed course/task; an older unscoped key could name another course's task, so it is dropped */
S.moved = Object.fromEntries(Object.entries(S.moved || {}).filter(([k]) => k.includes('/')));
S.inked = S.inked || {};
const saveS = () => { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch(e) {} };
if (S.theme === 'light' || S.theme === 'dark') document.documentElement.dataset.theme = S.theme;

/* ================= data ================= */
let ST = null, CM = {}, TM = {};
const SEL = new Set();                 /* checked fetch boxes, kept across live re-renders */
const course = slug => CM[slug];
/* a task id is unique only inside its course (spec ids such as s-t2 repeat), so every lookup, action,
   element id and saved move is keyed by course and id together */
const tkey = t => t.course + '/' + t.id;
const task = key => TM[key];
const today = () => (ST && ST.today) || isoOf(new Date());

async function api(path, body){
  const opt = body === undefined ? {credentials:'same-origin'} :
    {method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)};
  const r = await fetch(path, opt);
  if (r.status === 403) { stale('הקישור של הדף הזה כבר לא תקף. פתחו את הקישור החדש שהופיע בטרמינל כשהלוח הופעל.'); throw new Error('forbidden'); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || ('HTTP ' + r.status));
  return data;
}
function stale(msg){ const el = $('#stale'); el.textContent = msg; el.hidden = !msg; }
/* the state of another week, without replacing the page's own state (week = any date inside that week) */
const weekState = week => api('/api/state?week=' + encodeURIComponent(week));

async function load(force){
  let data;
  try { data = await api('/api/state'); }
  catch(e) { if (e.message !== 'forbidden') stale('לא הצלחתי לקרוא את הנתונים: ' + e.message); return; }
  stale('');
  const same = ST && ST.version === data.version && !force;
  ST = data; CM = {}; TM = {};
  (ST.courses || []).forEach(c => { CM[c.slug] = c; (c.tasks || []).forEach(t => TM[tkey(t)] = t); });
  if (same) return;
  renderNav(); renderBar();
  render(true);
}

/* ================= dates ================= */
const D = iso => new Date(iso + 'T12:00:00');
const isoOf = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
const addDays = (s, n) => { const d = D(s); d.setDate(d.getDate()+n); return isoOf(d); };
const dm = s => { const d = D(s); return `${d.getDate()}.${d.getMonth()+1}`; };
const dayDiff = (a, c) => Math.round((D(c) - D(a)) / 864e5);
const effDate = t => (t.reading && S.moved[tkey(t)]) || t.due_date;
function rel(d){
  const n = dayDiff(today(), d);
  if (n === 0) return 'היום'; if (n === 1) return 'מחר'; if (n === 2) return 'בעוד יומיים';
  if (n < 0) return n === -1 ? 'אתמול' : `לפני ${-n} ימים`;
  return `בעוד ${n} ימים`;
}
/* an ISO timestamp (any zone) as this browser's local date and clock time */
function localParts(iso){
  const d = new Date(iso); if (!iso || isNaN(d)) return null;
  return {date: isoOf(d), hm: `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`};
}
const shortWhen = iso => { const p = localParts(iso); return p ? `${DL[D(p.date).getDay()]} ${b(dm(p.date))}` : 'לא ידוע'; };
const baseName = p => String(p || '').split(/[\\/]/).filter(Boolean).pop() || '';
function dueHTML(t, withRel=true){
  const d = effDate(t);
  if (!d) return 'בלי תאריך';
  let s = `${DL[D(d).getDay()]} ${b(dm(d))}`;
  if (t.due_time && t.due_time !== '00:00') s += `, ${b(t.due_time)}`;
  /* red is never the only signal: a soon or late date also says so in words */
  if (withRel && t.status !== 'submitted' && t.overdue) s += ' · עבר';
  else if (withRel && t.status !== 'submitted' && t.soon) s += ` · ${rel(d)}`;
  return s;
}
const dueClass = t => t.status === 'submitted' ? '' : (t.overdue ? ' late' : (t.soon ? ' soon' : ''));
function fromIso(s){ const m = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})/.exec(s || ''); return m ? {date:`${m[1]}-${m[2]}-${m[3]}`, hm:`${m[4]}:${m[5]}`} : null; }

/* ================= numbers shown to people ================= */
function dur(sec){
  if (sec == null || isNaN(sec)) return 'לא ידוע';
  const m = Math.floor(sec / 60);
  if (sec < 60) return `${Math.max(0, Math.round(sec))} שנ׳`;
  if (m < 60) return `${m} דק׳`;
  return `${Math.floor(m / 60)} שע׳` + (m % 60 ? ` ${m % 60} דק׳` : '');
}
const cost = usd => usd == null ? 'לא ידוע' : `<bdi>$${usd < 10 ? usd.toFixed(2) : usd.toFixed(1)}</bdi>`;
const tokens = n => n == null ? 'לא ידוע' : `<bdi>${n >= 10000 ? Math.round(n / 1000) + 'K' : n.toLocaleString('en-US')}</bdi>`;

/* ================= status = glyph + word, never a colour alone ================= */
const STATUS = {
  ok:       {g:'✓', w:'מוכן',          cls:'ok'},
  missing:  {g:'✗', w:'חסר',           cls:'bad'},
  waiting:  {g:'◐', w:'ממתין',         cls:'wait'},
  night:    {g:'⟳', w:'Claude הלילה',  cls:'night'},
  running:  {g:'⟳', w:'בכתיבה',        cls:'night'},
  done:     {g:'✓', w:'הושלם',         cls:'ok'},
  failed:   {g:'✗', w:'נכשל',          cls:'bad'},
  stalled:  {g:'◐', w:'נעצר',          cls:'wait'},
  unknown:  {g:'?', w:'לא ידוע',       cls:'wait'},
  notfound: {g:'✗', w:'לא נמצאה',      cls:'bad'},
  passed:   {g:'✓', w:'עבר בדיקה',     cls:'ok'},
  rejected: {g:'✗', w:'נדחה',          cls:'bad'},
  drafted:  {g:'◐', w:'נכתב',          cls:'wait'},
  redrafted:{g:'⟳', w:'נכתב מחדש',     cls:'night'},
  todo:     {g:'○', w:'בתור',          cls:'wait'},
  skipped:  {g:'–', w:'דולג',          cls:'wait'}
};
function status(key, word){
  const s = STATUS[key] || STATUS.unknown;
  return `<span class="st ${s.cls}"><span class="g" aria-hidden="true">${s.g}</span> <span class="w">${esc(word || s.w)}</span></span>`;
}
const hue = h => HUES.includes(h) ? h : 'slate';
const hueClass = h => 'c-' + hue(h);

/* ================= writing runs (shared by the Overview and the Writing page) ================= */
const FLOW = {write:'מאמר', proofread:'הגהה', revise:'עדכון לפי הערות', edit:'עריכה', 'edit-section':'עריכת סעיף'};
const STEP = {
  write: {outline:'תכנון ומתווה', draft:'טיוטה', audit:'בדיקת מקורות', redraft:'כתיבה מחדש', synthesize:'מעברים בין פסקאות', word:'קובץ Word'},
  proofread: {find:'איתור', verify:'אימות', memo:'תזכיר', apply:'החלה'},
  revise: {read:'קריאת ההערות', 'update-draft':'עדכון הטיוטה', 'update-stores':'עדכון המאגרים'},
  edit: {edit:'עריכה'}, 'edit-section': {edit:'עריכה'}
};
const flowWord = f => FLOW[f] || 'ריצה';
const stepWord = (f, id) => (STEP[f] || STEP.edit)[id] || id;
function runProgress(run){
  const steps = run.steps || [];
  const cur = steps.findIndex(s => s.state === 'current');
  const done = steps.filter(s => s.state === 'done').length;
  return {total: steps.length, done, index: cur >= 0 ? cur + 1 : Math.min(done + 1, steps.length), current: cur >= 0 ? steps[cur] : null};
}
/* one bar of equal segments: done = filled, current = hatched, todo = empty, skipped = dotted, unknown = dashed */
function stepBar(run){
  const steps = run.steps || [];
  if (!steps.length) return '';
  const p = runProgress(run);
  const cls = {done:'d', current:'n', todo:'', skipped:'s', unknown:'u'};
  return `<div class="steps" role="img" aria-label="${p.done} מתוך ${p.total} שלבים הושלמו">` +
    steps.map(s => `<i class="${cls[s.state] || ''}" title="${esc(stepWord(run.flow, s.id))}"></i>`).join('') + '</div>';
}
const runWhen = run => run.status === 'running' ? `${dur(run.elapsed_s)} מתחילת הריצה` : dur(run.elapsed_s);

/* ================= ink ================= */
const NS = 'http://www.w3.org/2000/svg';
function rng(seed){ let s = seed % 2147483647 || 7; return () => (s = s * 16807 % 2147483647) / 2147483647; }
function hash(str){ let h = 7; for (const ch of str) h = (h * 31 + ch.charCodeAt(0)) % 2147483647; return h; }
function ellipse(W, H, r){
  const cx = W/2, cy = H/2, rx = W/2 - 3, ry = H/2 - 3;
  const a0 = -0.5 - r()*0.4, turns = 1.09 + r()*0.05, ph = r()*6.28, N = 72;
  let d = '';
  for (let i = 0; i <= N; i++){
    const t = i/N, a = a0 - t*turns*2*Math.PI;
    const k = 1 + 0.03*Math.sin(t*12.6 + ph) + (t - 0.5)*0.07;
    const x = cx + Math.cos(a)*rx*k, y = cy + Math.sin(a)*ry*k + Math.sin(t*3.1)*1.2;
    d += (i ? 'L' : 'M') + x.toFixed(1) + ',' + y.toFixed(1);
  }
  return d;
}
function svgEl(W, H, d, left, top){
  const s = document.createElementNS(NS, 'svg');
  s.setAttribute('class', 'ink'); s.setAttribute('aria-hidden', 'true');
  s.setAttribute('viewBox', `0 0 ${W} ${H}`); s.setAttribute('width', W); s.setAttribute('height', H);
  s.style.left = left + 'px'; s.style.top = top + 'px';
  const p = document.createElementNS(NS, 'path'); p.setAttribute('d', d); s.appendChild(p);
  return s;
}
let drawIndex = 0;
function draw(path, delay){
  if (reduced) return;
  const L = path.getTotalLength();
  path.style.strokeDasharray = L; path.style.strokeDashoffset = L;
  const a = path.animate([{strokeDashoffset:L},{strokeDashoffset:0}], {duration:520, delay, easing:'cubic-bezier(.25,1,.5,1)', fill:'forwards'});
  a.finished.then(() => { path.style.strokeDasharray = ''; path.style.strokeDashoffset = ''; a.cancel(); }).catch(()=>{});
}
/* isolate numbers, ranges, dates and times only (Latin runs are left to dir=auto, so long titles can wrap) */
const BIDI_RE = /\d+(?:[.,:]\d+)*\s?[–-]\s?\d+(?:[.,:]\d+)*|\d{1,2}\.\d{1,2}(?:\.\d{2,4})?|\d{1,2}:\d{2}/g;
function bidiFix(root){
  const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT), nodes = [];
  while (w.nextNode()){ const n = w.currentNode, p = n.parentElement;
    if (!p || p.closest('bdi,script,style,svg,input,code')) continue;
    BIDI_RE.lastIndex = 0; if (BIDI_RE.test(n.data)) nodes.push(n); }
  nodes.forEach(n => {
    const frag = document.createDocumentFragment(); let last = 0; const txt = n.data; BIDI_RE.lastIndex = 0; let m;
    while ((m = BIDI_RE.exec(txt))){ frag.append(txt.slice(last, m.index)); const bd = document.createElement('bdi'); bd.textContent = m[0]; frag.append(bd); last = m.index + m[0].length; }
    frag.append(txt.slice(last)); n.replaceWith(frag);
  });
}
/* mode: 'all' draws every mark, 'new' only [data-new] marks, 'none' static */
function inkify(root, mode='none'){
  bidiFix(root);
  drawIndex = 0;
  const marks = [];
  $$('.circ', root).forEach(el => {
    el.querySelector(':scope>svg.ink')?.remove();
    const w = el.offsetWidth, h = el.offsetHeight; if (!w) return;
    const px = Math.max(7, w*0.05), py = Math.max(4, h*0.16), W = w + 2*px, H = h + 2*py;
    const s = svgEl(W, H, ellipse(W, H, rng(hash(el.textContent))), -px, -py);
    el.appendChild(s); marks.push([s.firstChild, el]);
  });
  $$('.strike:not(.plain)', root).forEach(el => {
    el.querySelector(':scope>svg.ink')?.remove();
    const w = el.offsetWidth, h = el.offsetHeight; if (!w) return;
    const y = h*0.56, W = w + 8, r = rng(hash(el.textContent));
    const d = `M${W-1},${(y+1).toFixed(1)} C${(W*0.66).toFixed(1)},${(y-1.5-r()).toFixed(1)} ${(W*0.33).toFixed(1)},${(y+1.6+r()).toFixed(1)} 1,${(y-0.8).toFixed(1)}`;
    const s = svgEl(W, h, d, -4, 0); el.appendChild(s); marks.push([s.firstChild, el]);
  });
  $$('.tick path', root).forEach(p => marks.push([p, p.closest('.tick')]));
  $$('.hl', root).forEach(el => marks.push([null, el]));
  const sorted = marks.sort((a, c) => a[1].getBoundingClientRect().top - c[1].getBoundingClientRect().top);
  sorted.forEach(([p, el]) => {
    const isNew = el.hasAttribute('data-new') || el.closest('[data-new]');
    if (mode === 'all' || (mode === 'new' && isNew)){
      const delay = Math.min(drawIndex++ * 80, 1200);
      if (p) draw(p, delay);
      else if (!reduced){ el.style.animationDelay = delay + 'ms'; el.classList.remove('swipe'); void el.offsetWidth; el.classList.add('swipe'); }
    }
  });
  $$('[data-new]', root).forEach(e => e.removeAttribute('data-new'));
}
const TICK = '<span class="tick" role="img" aria-label="יש"><svg viewBox="0 0 22 20" aria-hidden="true"><path d="M2.5 11.5c2 1.6 3.6 3.6 5 6 3-6.4 7-11.6 12.5-15"/></svg></span>';
const CARET = '<svg class="caret" viewBox="0 0 12 12" aria-hidden="true"><path d="M1 11 6 2l5 9"/></svg>';
const NO = '<span class="no" role="img" aria-label="אין">—</span>';

/* ================= task marks ================= */
const doneWord = t => t.reading ? 'נקרא' : 'נשלח';
const verbDone = t => t.reading ? 'קראתי' : 'הגשתי';
function titleHTML(t){
  const title = esc(t.title);
  if (t.status === 'submitted') return `<span class="strike" data-mark="${esc(tkey(t))}">${title}</span><span class="sent">${doneWord(t)}</span>`;
  if (t.state === 'missing') return (t.title.length <= 44 ? `<span class="circ">${title}</span>` : title) + '<span class="sr"> · חסר מקור</span>';
  if (t.reading) return `<span class="hl">${title}</span><span class="sr"> · לקרוא</span>`;
  if (t.state === 'ready') return `${title}${TICK}<span class="sr"> · כל המקורות מוכנים</span>`;
  return title;
}
function glossText(t){
  if (t.status === 'submitted') return null;
  if (t.state === 'missing') return {red:true, text: t.missing_count === 1 ? 'חסר מקור אחד' : `חסרים ${t.missing_count} מקורות`};
  if (t.overdue) return {red:true, text:'מועד ההגשה עבר'};
  if (t.state === 'waiting') return {text: t.items.some(i => i.queued) ? 'Claude יביא את מה שחסר בריצה הלילית' : 'מחכה לבדיקת הזיהוי האוטומטי של הטקסט'};
  if (t.state === 'pending') return {text:'עוד לא כל המקורות אצלך'};
  return null;
}
function glossHTML(t, tag='p'){
  const g = glossText(t); if (!g) return '';
  return `<${tag} class="gloss${g.red ? ' red' : ''}">${esc(g.text)}</${tag}>`;
}

/* ================= shell: nav, scan line, banner ================= */
const ICON = {
  overview: '<path d="M3 4h14v12H3zM3 8h14M8 8v8"/>',
  timeline: '<path d="M3 5h14M3 10h14M3 15h14M7 3v4M13 8v4"/>',
  courses:  '<path d="M4 3h9a2 2 0 0 1 2 2v12H6a2 2 0 0 1-2-2zM4 15a2 2 0 0 1 2-2h9"/>',
  writing:  '<path d="M3 17l1-4L14 3l3 3L7 16zM12 5l3 3"/>',
  setup:    '<path d="M4 6l2 2 3-4M4 14l2 2 3-4M12 6h5M12 14h5"/>',
  about:    '<path d="M10 9v6M10 5.5v.5"/><path d="M3 3h14v14H3z"/>'
};
const icon = id => `<svg class="ni" viewBox="0 0 20 20" aria-hidden="true">${ICON[id] || ICON.about}</svg>`;
function navIds(){ const n = ST && Array.isArray(ST.nav) && ST.nav.length ? ST.nav : ['overview']; return n.filter(id => KNOWN.includes(id)); }
function renderNav(){
  $('#nav').innerHTML = navIds().map(id => `<a href="#${id}" data-view="${id}">${icon(id)}<span>${LABEL[id]}</span></a>`).join('');
  $('#nav').dataset.count = navIds().length;
}
function renderBar(){
  const el = $('#scan');
  if (!ST.nightly){ el.textContent = ST.term ? 'עוד לא הייתה סריקה' : ''; return; }
  const p = fromIso(ST.nightly); if (!p){ el.textContent = ''; return; }
  const n = dayDiff(p.date, today());
  const day = n === 0 ? 'היום' : n === 1 ? 'אתמול' : `${DL[D(p.date).getDay()]} ${dm(p.date)}`;
  el.innerHTML = `סריקה אחרונה: ${esc(day)}, ${b(p.hm)}`;
  bidiFix(el);
}

/* ================= toast ================= */
let toastT;
function toast(msg, undo, ms=3200){
  const t = $('#toast'), u = $('#toastUndo');
  $('#toastMsg').innerHTML = msg; bidiFix($('#toastMsg'));
  u.hidden = !undo; u.onclick = () => { t.classList.remove('show'); undo && undo(); };
  t.classList.add('show'); clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove('show'), ms);
}

/* ================= fetch queue ================= */
async function queueFetch(slug, boxes){
  const refs = boxes.map(i => i.dataset.src);
  if (!refs.length) return;
  const taskIds = [...new Set(boxes.map(i => i.dataset.task).filter(Boolean))];
  try {
    await api('/api/fetch', {course:slug, refs, task: taskIds.length === 1 ? taskIds[0] : null});
    refs.forEach(k => SEL.delete(k));
    $('#toast').classList.remove('lifted');
    toast(refs.length === 1 ? 'Claude יביא את המקור בריצה הלילית. הסימון כאן יתעדכן כשהוא יגיע.' : `Claude יביא את ${refs.length} המקורות בריצה הלילית. הסימון כאן יתעדכן כשהם יגיעו.`);
    await load(true);
  } catch(e) { if (e.message !== 'forbidden') toast('הבקשה לא נשמרה: ' + esc(e.message)); }
}

/* ================= submit + undo (written to the registry through tasks.py) ================= */
async function markDone(id){
  const t = task(id); if (!t || t.status === 'submitted') return;
  try { await api('/api/task/submit', {course:t.course, task:t.id}); }
  catch(e) { if (e.message !== 'forbidden') toast('הסימון לא נשמר: ' + esc(e.message)); return; }
  await load(true);
  const el = $('#view');
  $$(`[data-mark="${CSS.escape(id)}"]`, el).forEach(s => s.setAttribute('data-new', ''));
  inkify(el, 'new');
  toast(`סימנת ש${t.reading ? 'קראת' : 'הגשת'} את ${esc(t.title)}.`, () => undoDone(id), 5000);
  const u = $(`#undo-${CSS.escape(id)}`); u && u.focus();
}
async function undoDone(id){
  const t = task(id); if (!t) return;
  try { await api('/api/task/unsubmit', {course:t.course, task:t.id}); }
  catch(e) { if (e.message !== 'forbidden') toast('הביטול לא נשמר: ' + esc(e.message)); return; }
  await load(true);
  toast('הסימון בוטל.');
  const d = $(`#done-${CSS.escape(id)}`); d && d.focus();
}

/* ================= routing and rendering ================= */
function route(){
  const raw = decodeURIComponent(location.hash.replace(/^#/, ''));
  const parts = raw.split('/');
  const view = LEGACY[parts[0]] || (KNOWN.includes(parts[0]) ? parts[0] : 'overview');
  if (view !== 'course') return {view};
  const first = ST && ST.courses && ST.courses[0] && ST.courses[0].slug;
  return {view, id: parts.slice(1).join('/') || S.lastCourse || first || ''};
}
const go = hash => { location.hash = hash; };
const loading = {};
function ensureView(name){
  if (AW.views[name]) return Promise.resolve(true);
  if (!/^[a-z-]+$/.test(name)) return Promise.resolve(false);
  if (!loading[name]) loading[name] = new Promise(res => {
    const s = document.createElement('script');
    s.src = 'views/' + name + '.js';
    s.onload = () => res(!!AW.views[name]);
    s.onerror = () => { delete loading[name]; res(false); };
    document.head.appendChild(s);
  });
  return loading[name];
}
let renderToken = 0, booted = false;
async function render(live){
  if (!ST) return;
  const r = route(), token = ++renderToken;
  const ok = await ensureView(r.view);
  if (token !== renderToken) return;
  const el = $('#view');
  const focusId = document.activeElement && document.activeElement.id;
  const scroll = scrollY;
  el.dataset.view = r.view;
  const shown = r.view === 'course' ? 'courses' : r.view;
  $$('#nav a').forEach(a => a.dataset.view === shown ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current'));
  if (ok){
    try { AW.views[r.view](ST, el); }
    catch(e) { console.error(e); el.innerHTML = '<p class="notice">העמוד הזה לא נטען עד הסוף. אפשר לרענן את הדף.</p>'; }
  } else {
    el.innerHTML = '<p class="notice">העמוד הזה עוד לא מוכן.</p>';
  }
  const c = r.view === 'course' ? course(r.id) : null;
  document.title = c ? `${c.name} · ${BRAND}` : (r.view === 'overview' ? BRAND : `${LABEL[r.view]} · ${BRAND}`);
  /* the ink draws once per day per view; live updates and later visits are static */
  const key = r.view === 'course' ? 'c:' + r.id : r.view;
  const first = booted && S.inked[key] !== today();
  if (booted){ if (first){ S.inked[key] = today(); saveS(); } inkify(el, first ? 'all' : 'none'); }
  else bidiFix(el);
  if (live){
    if (focusId){ const f = document.getElementById(focusId); f && f.focus({preventScroll:true}); }
    scrollTo({top:scroll});
  }
  if (!$('input[data-src]:checked', el)) $('#toast').classList.remove('lifted');
}
window.addEventListener('hashchange', () => { render(false).then(() => scrollTo({top:0})); });
let rz; window.addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => { if (ST) inkify($('#view')); }, 120); });

/* ================= theme ================= */
function setTheme(t){
  document.documentElement.dataset.theme = t; S.theme = t; saveS();
}
function toggleTheme(){
  const r = document.documentElement;
  const dark = r.dataset.theme ? r.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  setTheme(dark ? 'light' : 'dark');
}

/* ================= palette ================= */
let pal, palIn, palList, palItems = [], palSel = 0;
function commands(){
  const out = [];
  if (!ST) return out;
  navIds().forEach(id => out.push({label:esc(LABEL[id]), hint:'עמוד', run:() => go('#' + id)}));
  (ST.courses || []).forEach(c => out.push({label:esc(c.name), hint:'קורס', run:() => go('#course/' + encodeURIComponent(c.slug))}));
  (ST.courses || []).forEach(c => c.tasks.forEach(t => {
    if (t.status === 'submitted'){ if (t.recently_submitted) out.push({label:`לבטל את הסימון: ${esc(t.title)}`, hint:esc(c.name), run:() => undoDone(tkey(t))}); }
    else out.push({label:`${verbDone(t)}: ${esc(t.title)}`, hint:esc(c.name), run:() => markDone(tkey(t))});
  }));
  (ST.courses || []).forEach(c => {
    const all = c.tasks.filter(t => t.status !== 'submitted').flatMap(t => t.items.map(i => [i, t.id])).concat(c.more.map(i => [i, '']));
    const miss = all.filter(([i]) => i.fetchable && i.type === 'ref' && (i.missing || i.status === 'pending' || i.status === 'kotar' || i.status === 'online'));
    const keys = [...new Set(miss.map(([i]) => i.key))];
    if (keys.length) out.push({label:`לבקש מ־Claude להביא ${keys.length === 1 ? 'את המקור החסר' : keys.length + ' מקורות חסרים'} ב${esc(c.name)}`, hint:'מקורות', run: async () => {
      const tids = [...new Set(miss.map(([, t]) => t).filter(Boolean))];
      try { await api('/api/fetch', {course:c.slug, refs:keys, task: tids.length === 1 ? tids[0] : null}); toast(`Claude יביא ${keys.length === 1 ? 'את המקור' : 'את ' + keys.length + ' המקורות'} בריצה הלילית.`); await load(true); }
      catch(e) { if (e.message !== 'forbidden') toast('הבקשה לא נשמרה: ' + esc(e.message)); }
    }});
  });
  out.push({label:'להחליף בין מצב בהיר לכהה', hint:'תצוגה', run:toggleTheme});
  out.push({label:'קיצורי מקלדת', hint:'?', run:openHelp});
  return out;
}
const strip = h => { const d = document.createElement('div'); d.innerHTML = h; return d.textContent; };
function palRender(){
  const q = palIn.value.trim().split(/\s+/).filter(Boolean);
  palItems = commands().filter(c => { const s = strip(c.label + ' ' + c.hint); return q.every(w => s.includes(w)); });
  palSel = Math.min(palSel, Math.max(0, palItems.length - 1));
  palList.innerHTML = palItems.length ? palItems.map((c, i) => `<li role="option" id="po${i}" aria-selected="${i === palSel}" data-i="${i}"><span>${c.label}</span><span class="label">${/^g |^\?$/.test(c.hint) ? b(c.hint) : c.hint}</span></li>`).join('')
    : `<li class="none" role="option" aria-disabled="true">אין התאמה. אפשר לחפש שם של עמוד, קורס או פעולה.</li>`;
  bidiFix(palList);
  palIn.setAttribute('aria-activedescendant', palItems.length ? 'po' + palSel : '');
  const sel = $('#po' + palSel); sel && sel.scrollIntoView({block:'nearest'});
}
function openPalette(){ if (pal.open) return; $('#help').open && $('#help').close(); palIn.value = ''; palSel = 0; palRender(); pal.showModal(); palIn.focus(); }
function runPal(i){ const c = palItems[i]; if (!c) return; pal.close(); c.run(); }
function openHelp(){ const h = $('#help'); if (!h.open) h.showModal(); }

/* ================= keyboard ================= */
let gWait = false, gT;
const G_MAP = {KeyO:'overview', KeyT:'timeline', KeyC:'courses', KeyW:'writing', KeyS:'setup', KeyA:'about'};
function onKey(e){
  if ((e.metaKey || e.ctrlKey) && e.code === 'KeyK'){ e.preventDefault(); pal.open ? pal.close() : openPalette(); return; }
  if (document.querySelector('dialog[open]')) return;
  const t = e.target;
  if (t.matches && t.matches('input,textarea,select,[contenteditable="true"]')) return;
  const view = route().view;
  if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown') && AW.onAltArrow){ AW.onAltArrow(e, view); return; }
  if (e.metaKey || e.ctrlKey || e.altKey) return;
  if (gWait){
    gWait = false; clearTimeout(gT);
    const id = G_MAP[e.code];
    if (id && navIds().includes(id)){ e.preventDefault(); go('#' + id); }
    return;
  }
  if (e.code === 'KeyG' && !e.shiftKey){ gWait = true; gT = setTimeout(() => gWait = false, 1200); return; }
  if (e.key === '?' || (e.code === 'Slash' && e.shiftKey)){ e.preventDefault(); openHelp(); return; }
  if (e.key === 'Escape' && view === 'course'){ go(navIds().includes('courses') ? '#courses' : '#overview'); return; }
  if (e.key === 'ArrowDown' || e.key === 'ArrowUp'){
    const items = $$('#view [data-nav]'); if (!items.length) return;
    e.preventDefault();
    let i = items.indexOf(t.closest ? t.closest('[data-nav]') : null);
    i = i < 0 ? (e.key === 'ArrowDown' ? 0 : items.length - 1) : Math.max(0, Math.min(items.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)));
    items[i].focus(); items[i].scrollIntoView({block:'nearest'});
  }
}

/* ================= live updates: the server pushes, the page never polls ================= */
function listen(){
  const es = new EventSource('/api/events');
  es.addEventListener('state-changed', () => load(false));
}

/* ================= boot ================= */
function boot(){
  pal = $('#pal'); palIn = $('#palIn'); palList = $('#palList');
  /* the key in the URL became a cookie on this load: take it out of the address bar */
  if (/[?&]key=/.test(location.search)) history.replaceState(null, '', location.pathname + location.hash);
  const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent);
  if (!isMac) { $('#modKey').textContent = 'Ctrl K'; $$('.modk').forEach(e => e.textContent = 'Ctrl K'); }
  palIn.addEventListener('input', () => { palSel = 0; palRender(); });
  palIn.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown'){ e.preventDefault(); palSel = (palSel + 1) % Math.max(1, palItems.length); palRender(); }
    else if (e.key === 'ArrowUp'){ e.preventDefault(); palSel = (palSel - 1 + palItems.length) % Math.max(1, palItems.length); palRender(); }
    else if (e.key === 'Enter'){ e.preventDefault(); runPal(palSel); }
  });
  palList.addEventListener('click', e => { const li = e.target.closest('li[data-i]'); li && runPal(+li.dataset.i); });
  pal.addEventListener('click', e => { if (e.target === pal) pal.close(); });
  $('#palBtn').onclick = openPalette;
  $('#helpBtn').onclick = openHelp;
  $('#help').addEventListener('click', e => { if (e.target.id === 'help') e.target.close(); });
  $('#themeBtn').onclick = toggleTheme;
  document.addEventListener('keydown', onKey);
  bidiFix($('.top')); bidiFix($('#help'));
  const fontsReady = document.fonts ? Promise.race([document.fonts.ready, new Promise(r => setTimeout(r, 1500))]) : Promise.resolve();
  if (reduced) document.documentElement.classList.add('inked');
  load(true).then(() => fontsReady).then(() => {
    booted = true;
    render(false);
    document.documentElement.classList.add('inked');
    listen();
  });
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();

Object.assign(AW, {
  state: () => ST, course, task, tkey, load, weekState, api, go, esc, b, auto, $, $$,
  D, isoOf, addDays, dm, dayDiff, rel, today, effDate, localParts, shortWhen, baseName, dueHTML, dueClass, fromIso, DL, DN, MONTH, LABEL, HUES,
  dur, cost, tokens, status, hueClass, TICK, CARET, NO, titleHTML, glossHTML, verbDone,
  flowWord, stepWord, stepBar, runProgress, runWhen,
  markDone, undoDone, queueFetch, toast, S, saveS, inkify, bidiFix, SEL, route
});
})();
