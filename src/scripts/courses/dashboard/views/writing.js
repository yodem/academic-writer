/* Writing: every workspace's runs from the activity record (runs/<id>/activity.jsonl), read-only.
   In progress first (step bar, current step, section boxes, latest citation-check verdict, time, tokens, cost),
   then the folders, then history. A line the record could not read shows as "unknown", never a guess.
   Look: mockup agent-activity (B), brand step bar. */
(() => {
const A = window.AW;
const {esc, b, auto, status, stepBar, runProgress, flowWord, stepWord, shortWhen, localParts, baseName, dur, cost, tokens, toast} = A;

const many = (n, one, plural) => n === 1 ? one : plural.replace('#', n);
const VERDICT = {PASS: ['ok', 'עבר'], FAIL: ['missing', 'נכשל'], PARTIAL: ['waiting', 'עבר חלקית']};
const STEP_STATE = {done: ['done', 'הושלם'], current: ['running', 'עכשיו'], todo: ['todo', 'בתור'], skipped: ['skipped', 'דולג'], unknown: ['unknown', 'לא ידוע']};
const WS_TYPE = {project: 'פרויקט', course: 'קורס', teaching: 'הוראה'};

const verdict = v => VERDICT[v] ? status(VERDICT[v][0], VERDICT[v][1]) : status('unknown');
const name = run => auto(baseName(run.workspace) || flowWord(run.flow));
const whenFull = iso => { const p = localParts(iso); return p ? `${shortWhen(iso)}, ${b(p.hm)}` : 'לא ידוע'; };
const unreadable = run => run.unreadable ? `<p class="flag">${many(run.unreadable, 'שורה אחת ברשומת הפעילות לא הייתה קריאה', '# שורות ברשומת הפעילות לא היו קריאות')} ונספרו כ״לא ידוע״.</p>` : '';

/* ---------- a run in progress ---------- */
function stepLabels(run){
  const cur = (run.steps || []).findIndex(s => s.state === 'current');
  return `<div class="steplabels" aria-hidden="true">${(run.steps || []).map((s, i) => `<span class="${i === cur ? 'cur' : ''}">${esc(stepWord(run.flow, s.id))}</span>`).join('')}</div>`;
}
function nowBox(run){
  const p = runProgress(run), units = run.units || [];
  const bad = units.filter(u => u.state === 'rejected').pop();
  let out = `<p><strong>עכשיו:</strong> ${esc(p.current ? stepWord(run.flow, p.current.id) : run.status === 'running' ? 'בין שלבים' : 'לא ידוע')}</p>`;
  if (bad) out += `<p>הסעיף ${auto(bad.id)} נדחה${bad.reason ? ': ' + auto(bad.reason) : ''}</p>`;
  if (run.last_verdict) out += `<p>בדיקת המקורות האחרונה: ${verdict(run.last_verdict)}${run.redrafted ? ' · ' + many(run.redrafted, 'סעיף אחד נכתב מחדש', '# סעיפים נכתבו מחדש') : ''}</p>`;
  return `<div class="now">${out}</div>`;
}
function unitBoxes(run){
  const units = run.units || [];
  if (!units.length) return '';
  return `<ul class="units" aria-label="סעיפים">${units.map(u =>
    `<li class="unit"><b>${auto(u.id)}</b>${status(u.state)}${u.reason && u.state !== 'passed' ? `<span class="why">${auto(u.reason)}</span>` : ''}</li>`).join('')}</ul>`;
}
function stepList(run){
  return `<ol class="slist" aria-label="שלבי הריצה">${(run.steps || []).map((s, i) => {
    const [key, word] = STEP_STATE[s.state] || STEP_STATE.unknown;
    return `<li><span class="n">${b(i + 1)}</span>${status(key, stepWord(run.flow, s.id))}<span class="meta">${word}</span></li>`;
  }).join('')}</ol>`;
}
function stats(run){
  return `<p class="stats"><span>זמן: <strong>${esc(dur(run.elapsed_s))}</strong></span><span>אסימונים: <strong>${tokens(run.tokens)}</strong></span><span>עלות: <strong>${cost(run.cost_usd)}</strong></span></p>`;
}
function activeRun(run, primary){
  const p = runProgress(run), course = run.course && A.course(run.course);
  return `<article class="run${primary ? ' card' : ''}" aria-label="${esc(baseName(run.workspace))}">
    <header>
      <div><h3>${name(run)}</h3><p class="sub">${esc(flowWord(run.flow))}${course ? ' · ' + auto(course.name) : ''} · התחילה ${whenFull(run.started)}</p></div>
      ${status(run.status)}
    </header>
    <p class="meta">שלב ${b(p.index)} מתוך ${b(p.total)} · ${esc(dur(run.elapsed_s))}</p>
    ${stepBar(run)}${stepLabels(run)}
    ${nowBox(run)}${unitBoxes(run)}${stats(run)}${stepList(run)}${unreadable(run)}
  </article>`;
}

/* ---------- tables (they scroll inside their own box) ---------- */
const scroll = (label, html) => `<div class="tscroll" tabindex="0" role="region" aria-label="${label}">${html}</div>`;
function folders(rows){
  const body = rows.map(w => {
    const result = !w.exists ? status('notfound') : w.last_status ? status(w.last_status) : '<span class="meta">עוד לא נכתב</span>';
    return `<tr><td class="wrap"><strong>${auto(w.name)}</strong>${w.exists ? '' : `<br><code class="path">${esc(w.path)}</code>`}</td>
      <td>${WS_TYPE[w.type] || esc(w.type || '')}</td><td class="num2">${b(w.runs)}</td>
      <td class="num2">${w.last_run ? whenFull(w.last_run) : '—'}</td><td>${result}</td></tr>`;
  }).join('');
  return scroll('תיקיות עבודה', `<table><thead><tr><th>תיקייה</th><th>סוג</th><th>ריצות</th><th>ריצה אחרונה</th><th>מצב</th></tr></thead><tbody>${body}</tbody></table>`);
}
function history(rows){
  const body = rows.map(r => {
    const course = r.course && A.course(r.course);
    const file = r.docx ? `<code class="path">${esc(baseName(r.docx))}</code> <button class="copy" data-open data-run="${esc(r.run)}" data-ws="${esc(r.workspace)}">פתיחה ב־Word</button> <button class="copy" data-copy="${esc(r.docx)}">העתקת הנתיב</button>` : '—';
    return `<tr><td class="num2">${whenFull(r.started)}</td>
      <td class="wrap"><strong>${name(r)}</strong></td>
      <td class="wrap">${course ? auto(course.name) : r.course ? auto(r.course) : '—'}</td>
      <td>${esc(flowWord(r.flow))}</td>
      <td>${status(r.status)}${r.unreadable ? `<span class="meta"> · ${many(r.unreadable, 'שורה לא קריאה', '# שורות לא קריאות')}</span>` : ''}</td>
      <td class="num2">${r.redrafted ? b(r.redrafted) : '—'}</td>
      <td class="num2">${esc(dur(r.elapsed_s))}</td>
      <td class="num2">${cost(r.cost_usd)}</td>
      <td class="wrap">${file}</td></tr>`;
  }).join('');
  return scroll('היסטוריית ריצות', `<table><thead><tr><th>מתי</th><th>תיקייה</th><th>קורס</th><th>סוג</th><th>תוצאה</th><th>סעיפים שנכתבו מחדש</th><th>זמן</th><th>עלות</th><th>קובץ Word</th></tr></thead><tbody>${body}</tbody></table>`);
}

const dateText = st => { const d = A.D(st.today); return `יום ${A.DN[d.getDay()]}, ${b(d.getDate())} ${A.MONTH[d.getMonth()]} ${b(d.getFullYear())}`; };

A.views.writing = (st, el) => {
  const w = st.writing || {active: [], history: []}, folderRows = st.workspaces || [];
  const lede = w.active.length ? many(w.active.length, 'יש ריצת כתיבה אחת בעיצומה.', 'יש # ריצות כתיבה בעיצומן.') : 'אין כתיבה בעיצומה כרגע.';
  let html = `<section class="pagehead" aria-label="כתיבה">
    <div class="dateline"><span>${dateText(st)}</span><span>${b(w.active.length)} בעיצומה · ${b(w.history.length)} בהיסטוריה</span></div>
    <h1>כתיבה</h1><p class="lede">${lede} הריצות נרשמות מעצמן כש־Claude כותב, מגיה או עורך, ורק כשלבים ותוצאות, בלי טקסט המאמר.</p></section>`;
  if (!w.active.length && !w.history.length && !folderRows.length){
    html += `<section class="empty" aria-label="עוד אין ריצות"><img class="plate" src="img/hero-desk.webp" alt="" width="800" height="447"><div>
      <p>עוד לא נרשמה כתיבה.</p><p>כשתתחילו מאמר עם <code>/academic-writer:write</code> הוא יופיע כאן, שלב אחרי שלב.</p></div></section>`;
    el.innerHTML = html; return;
  }
  html += `<section class="section" aria-label="בעיצומה"><h2>בעיצומה</h2>${w.active.length ?
    `<div class="runs">${w.active.map((r, i) => activeRun(r, i === 0)).join('')}</div>` :
    '<p class="meta">אין ריצה פעילה. ריצה שלא זזה זמן רב נחשבת כנעצרה ועוברת להיסטוריה.</p>'}</section>`;
  if (folderRows.length) html += `<section class="section" aria-label="תיקיות עבודה"><h2>תיקיות עבודה</h2>${folders(folderRows)}</section>`;
  html += `<section class="section" aria-label="היסטוריה"><h2>היסטוריה</h2>${w.history.length ? history(w.history) : '<p class="meta">עוד אין ריצות שהסתיימו.</p>'}</section>`;
  el.innerHTML = html;
  el.querySelectorAll('[data-open]').forEach(btn => btn.addEventListener('click', async () => {
    try { await A.api('/api/open', {run: btn.dataset.run, workspace: btn.dataset.ws}); toast('הקובץ נפתח ב־Word.'); }
    catch(e) { toast('לא הצלחתי לפתוח את הקובץ. אפשר להעתיק את הנתיב ולפתוח אותו ידנית.'); }
  }));
  el.querySelectorAll('[data-copy]').forEach(btn => btn.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(btn.dataset.copy); toast('הנתיב הועתק.'); }
    catch(e) { toast('לא הצלחתי להעתיק. הנתיב: ' + esc(btn.dataset.copy)); }
  }));
};
})();
