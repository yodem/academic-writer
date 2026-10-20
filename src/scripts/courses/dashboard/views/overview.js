/* Overview. Student: masthead, the next submission as the one primary card, four ruled columns.
   Lecturer and researcher: the same masthead, the article in progress as the primary card, three ruled columns
   (projects, recent results, library). Look: src/brand/DESIGN.md section 4, mockup overview-sunday-v3 (A). */
(() => {
const A = window.AW;
const {esc, b, auto, D, DN, DL, MONTH, dm, dayDiff, addDays, today, status, hueClass, titleHTML, stepBar, runProgress,
       flowWord, stepWord, shortWhen, baseName, dur} = A;

const many = (n, one, plural) => n === 1 ? one : plural.replace('#', n);
const LIMIT = 5;

/* ---------- masthead ---------- */
function dateLine(st){
  const d = D(st.today);
  const left = `יום ${DN[d.getDay()]}, ${b(d.getDate())} ${MONTH[d.getMonth()]} ${b(d.getFullYear())}`;
  const right = st.week_mode === 'week-ahead' ? 'מבט על השבוע הקרוב' : 'מבט על היום';
  return `<div class="dateline"><span>${left}</span><span>${right}</span></div>`;
}
function greeting(st){
  const hello = st.week_mode === 'week-ahead' ? 'שבוע טוב' : 'שלום';
  const name = st.home && st.home.name;
  return name ? `${hello}, ${auto(name)}` : hello;
}
function ledeHTML(st){
  return (st.lede || []).map(seg => seg.mark === 'circ' ? `<span class="circ">${esc(seg.t)}</span>` : esc(seg.t)).join('');
}
function masthead(st, solo){
  return `<section class="mast${solo ? ' solo' : ''}" aria-label="פתיחה">
    <div>${dateLine(st)}<h1 class="greet">${greeting(st)}</h1>${solo ? '' : `<p class="lede">${ledeHTML(st)}</p>`}</div>
    ${solo ? '' : '<div class="art"><img src="img/hero-desk.webp" alt="" width="800" height="447"></div>'}
  </section>`;
}

/* ---------- banners ---------- */
function banners(st){
  let out = '';
  if (st.home && st.home.missing)
    out += `<div class="banner" role="status"><p>${status('missing', 'תיקיית הבית לא נמצאה')} אם הזזתם אותה, בקשו מ־Claude לעדכן את המיקום: <code class="path">/academic-writer:setup</code></p></div>`;
  if (st.setup && st.setup.complete === false)
    out += `<div class="banner" role="status"><p>${status('waiting', 'ההגדרה עוד לא הושלמה')} חסרים כמה דברים כדי שהכול יעבוד.</p><a class="lnk" href="#setup">לעמוד ההגדרה</a></div>`;
  return out;
}

/* ---------- column helpers ---------- */
const head = (cls, text) => `<h3><span class="sq ${cls}" aria-hidden="true"></span>${text}</h3>`;
const none = html => `<p class="none">${html}</p>`;
const line = (what, val) => `<li class="ln">${what}<span class="lead" aria-hidden="true"></span><span class="val">${val}</span></li>`;
const more = (n, href) => n > 0 ? `<a class="more" href="${href}">ועוד ${b(n)}</a>` : '';

/* ---------- student ---------- */
function openTasks(st){ return (st.courses || []).flatMap(c => c.tasks.filter(t => t.status !== 'submitted').map(t => [c, t])); }
function nextTask(st){
  const rows = (st.overview && st.overview.rows || []).filter(r => !r.submitted);
  const tasks = rows.map(r => A.task(r.course + '/' + r.task)).filter(Boolean);
  return tasks.find(t => !t.reading && !t.exam) || tasks[0] || null;
}
function countdown(t){
  const d = A.effDate(t);
  if (!d) return {n: '—', word: 'בלי תאריך'};
  const n = dayDiff(today(), d);
  if (n === 0) return {n: '0', word: t.overdue ? 'המועד עבר' : 'היום'};
  if (n < 0) return {n: String(-n), word: n === -1 ? 'יום באיחור' : 'ימים באיחור'};
  return {n: String(n), word: n === 1 ? 'יום' : 'ימים'};
}
function sourceFacts(t){
  const items = t.items || [];
  if (!items.length) return status('waiting', 'עוד לא קושרו מקורות');
  const ready = items.filter(i => i.downloaded && i.in_trove).length;
  const miss = items.filter(i => i.missing).length;
  const wait = items.filter(i => i.waiting).length;
  const out = [];
  if (ready) out.push(status('ok', many(ready, 'מקור אחד מוכן', '# מקורות מוכנים')));
  if (miss) out.push(status('missing', many(miss, 'מקור אחד חסר', '# מקורות חסרים')));
  if (wait) out.push(status('waiting', many(wait, 'מקור אחד ממתין', '# מקורות ממתינים')));
  if (!out.length) out.push(status('waiting', 'המקורות בדרך'));
  return out.join('');
}
function nextCard(st){
  const t = nextTask(st);
  if (!t) return `<section class="card next" aria-label="ההגשה הבאה">
    <div class="num">0<small>הגשות פתוחות</small></div>
    <div><p class="k">ההגשה הבאה</p><h2>אין הגשה פתוחה</h2><p class="facts">${status('ok', 'הכול הוגש')}</p></div>
    <a class="btn secondary" href="#${st.nav && st.nav.includes('courses') ? 'courses' : 'overview'}">לקורסים</a></section>`;
  const c = A.course(t.course), cd = countdown(t);
  const due = A.effDate(t) ? `עד ${A.dueHTML(t, false)}` : 'בלי תאריך';
  return `<section class="card next" aria-label="${t.reading ? 'הקריאה הבאה' : 'ההגשה הבאה'}">
    <div class="num">${esc(cd.n)}<small>${cd.word}</small></div>
    <div>
      <p class="k">${t.reading ? 'הקריאה הבאה' : 'ההגשה הבאה'}</p>
      <h2>${esc(t.title)}</h2>
      <p class="facts"><span class="cname ${hueClass(c && c.color)}">${auto(c ? c.name : t.course)}</span><span>${due}</span>${sourceFacts(t)}</p>
    </div>
    <a class="btn" href="#course/${encodeURIComponent(t.course)}" data-nav>${t.reading ? 'פתח את הקריאה' : 'פתח את המטלה'}</a>
  </section>`;
}

/* column 1: today, or the coming week */
function agendaLines(days, withDay){
  const lines = [];
  days.forEach(day => (day.items || []).forEach(i => {
    const c = A.course(i.course); if (!c) return;
    const t = i.type === 'task' ? A.task(i.course + '/' + i.task) : null;
    const dayTag = withDay ? `${DL[D(day.date).getDay()]} ${b(dm(day.date))} · ` : '';
    const what = t ? `${esc(t.kind_word)}: ${esc(t.title)}<span class="sub">${auto(c.name)}</span>` : auto(c.name);
    lines.push(line(`<span class="what">${dayTag}${what}</span>`, i.time ? b(i.time) : ''));
  }));
  return lines;
}
function weekColumn(st, days){
  const ahead = st.week_mode === 'week-ahead';
  const lines = agendaLines(ahead ? days : days.filter(d => d.today), ahead);
  const body = lines.length ? `<ul>${lines.slice(0, 6).join('')}</ul>${more(lines.length - 6, '#timeline')}` :
    none(ahead ? 'אין שיעורים או הגשות השבוע.' : 'אין שיעורים או הגשות היום.');
  return head('r-indigo', ahead ? 'השבוע' : 'היום') + body;
}
const nextWeek = {};
function fillNextWeek(st, el){
  /* from Saturday evening the week ahead is the next Sunday-to-Saturday: ask the server for that week once */
  const week = addDays(st.today, 1), key = st.version + week;
  if (!nextWeek[key]) nextWeek[key] = A.weekState(week).then(s => s.agenda.days).catch(() => null);
  nextWeek[key].then(days => {
    const col = document.getElementById('col-week');
    if (days && col && document.getElementById('view') === el && el.dataset.view === 'overview') { col.innerHTML = weekColumn(st, days); A.bidiFix(col); }
  });
}

/* column 2: exams and deadlines */
function deadlineColumn(st, skip){
  const rows = [];
  (st.exams || []).forEach(e => {
    const c = A.course(e.course); if (!c || !e.due_date) return;
    const where = [e.room ? `חדר ${e.room}` : '', e.due_time && e.due_time !== '00:00' ? e.due_time : ''].filter(Boolean).join(' · ');
    rows.push([e.due_date, line(`<a class="what" href="#course/${encodeURIComponent(c.slug)}" data-nav><strong>מבחן: ${esc(e.title)}</strong><span class="sub">${auto(c.name)}${where ? ' · ' + esc(where) : ''}</span></a>`, b(dm(e.due_date)))]);
  });
  openTasks(st).forEach(([c, t]) => {
    if (t.exam || t === skip || !A.effDate(t)) return;
    /* a reading due before a lesson is a deadline too: marked so it is not mistaken for a hand-in */
    const what = t.reading ? `${esc(t.kind_word)}: ${esc(t.title)}` : esc(t.title);
    rows.push([A.effDate(t), line(`<a class="what" href="#course/${encodeURIComponent(c.slug)}" data-nav>${what}<span class="sub">${auto(c.name)}</span></a>`, b(dm(A.effDate(t))))]);
  });
  rows.sort((x, y) => x[0] < y[0] ? -1 : x[0] > y[0] ? 1 : 0);
  const body = rows.length ? `<ul>${rows.slice(0, LIMIT).map(r => r[1]).join('')}</ul>${more(rows.length - LIMIT, '#timeline')}` : none('אין מבחנים או מועדי הגשה קרובים.');
  return head('r-bad', 'מבחנים ודדליינים') + body;
}

/* column 3: not ready (what Claude will handle tonight is marked with its own glyph) */
function notReadyColumn(st){
  const rows = [];
  (st.courses || []).forEach(c => {
    c.tasks.filter(t => t.status !== 'submitted' && ['missing', 'waiting', 'pending'].includes(t.state)).forEach(t => {
      const queued = t.items.some(i => i.queued);
      const note = t.state === 'missing' ? many(t.missing_count, 'חסר מקור אחד', 'חסרים # מקורות') :
        t.state === 'waiting' ? (queued ? 'Claude יביא את מה שחסר' : 'מחכה לזיהוי הטקסט') : 'עוד לא כל המקורות אצלך';
      const val = t.state === 'missing' ? status('missing') : queued ? status('night') : status('waiting');
      rows.push(line(`<a class="what" href="#course/${encodeURIComponent(c.slug)}" data-nav>${esc(t.title)}<span class="sub">${auto(c.name)} · ${esc(note)}</span></a>`, val));
    });
    if (c.perusall_open) rows.push(line(`<a class="what" href="#course/${encodeURIComponent(c.slug)}" data-nav>${many(c.perusall_open, 'קריאה אחת ב־Perusall', '# קריאות ב־Perusall')}<span class="sub">${auto(c.name)} · עוד לא צולמו</span></a>`, status('waiting')));
  });
  const un = (st.wispr_unmatched || []).length;
  if (un) rows.push(line(`<span class="what">${many(un, 'הקלטה אחת שלא שויכה לקורס', '# הקלטות שלא שויכו לקורס')}<span class="sub">Wispr</span></span>`, status('waiting')));
  const body = rows.length ? `<ul>${rows.slice(0, LIMIT).join('')}</ul>${more(rows.length - LIMIT, '#overview')}` : none(status('ok', 'הכול מוכן'));
  return head('r-marker', 'לא מוכן') + body;
}

/* column 4: writing */
function writingColumn(st, to){
  const w = st.writing || {active: [], history: []};
  const run = w.active[0];
  let body;
  if (run){
    const p = runProgress(run);
    body = `<ul>${line(`<a class="what" href="${to}" data-nav>${auto(baseName(run.workspace) || flowWord(run.flow))}<span class="sub">${esc(flowWord(run.flow))} · ${esc(p.current ? stepWord(run.flow, p.current.id) : 'בתהליך')}</span></a>`, `שלב ${b(p.index + "/" + p.total)}`)}</ul>${stepBar(run)}`;
  } else {
    const last = w.history[0];
    body = none('אין כתיבה בעיצומה.') + (last ? `<ul>${line(`<a class="what" href="${to}" data-nav>${auto(baseName(last.workspace) || flowWord(last.flow))}<span class="sub">${esc(flowWord(last.flow))} · הריצה האחרונה</span></a>`, status(last.status))}</ul>` : '');
  }
  return head('r-violet', 'כתיבה') + body;
}

function studentPage(st){
  const t = nextTask(st), writing = st.nav && st.nav.includes('writing') ? '#writing' : '#overview';
  return `${masthead(st)}${banners(st)}${nextCard(st)}
    <div class="cols">
      <section class="col" id="col-week" aria-label="${st.week_mode === 'week-ahead' ? 'השבוע' : 'היום'}">${weekColumn(st, st.agenda.days)}</section>
      <section class="col" aria-label="מבחנים ודדליינים">${deadlineColumn(st, t)}</section>
      <section class="col" aria-label="לא מוכן">${notReadyColumn(st)}</section>
      <section class="col" aria-label="כתיבה">${writingColumn(st, writing)}</section>
    </div>`;
}

/* ---------- empty install ---------- */
function emptyPage(st){
  const setup = st.setup && st.setup.complete === false;
  let body;
  if (st.reason === 'ambiguous-term')
    body = `<p>יש כאן יותר מסמסטר אחד, והלוח לא יודע איזה להציג.</p><p>הפעילו אותו מחדש עם <code>--term</code> ושם הסמסטר, או עם המשתנה <code>ACADEMIC_TERM</code>.</p>`;
  else if (setup)
    body = `<p>עוד לא סיימנו להגדיר את סביבת העבודה.</p><p>העמוד <a class="lnk" href="#setup">הגדרה</a> מראה מה חסר ואיך לתקן.</p>`;
  else
    body = `<p>עוד אין קורסים. הריצו <code>/academic-writer:courses</code></p><p>הפקודה מגדירה את הסמסטר ואת הקורסים. הלוח הזה יתעדכן מעצמו כשהם יופיעו.</p>`;
  return `${masthead(st, true)}${banners(st)}<section class="empty" aria-label="עוד אין נתונים"><img class="plate" src="img/hero-desk.webp" alt="" width="800" height="447"><div>${body}</div></section>`;
}

/* ---------- lecturer and researcher ---------- */
function writerCard(st){
  const run = st.overview.primary;
  if (!run) return `<section class="card next" aria-label="כתיבה">
    <div class="num ink">0<small>ריצות פעילות</small></div>
    <div><p class="k">כתיבה</p><h2>אין כתיבה בעיצומה</h2><p class="facts"><span>כדי להתחיל, בקשו מ־Claude לכתוב או לערוך מאמר: <code class="path">/academic-writer:write</code></span></p></div>
    <a class="btn secondary" href="#writing">לעמוד הכתיבה</a></section>`;
  const p = runProgress(run);
  return `<section class="card next" aria-label="כתיבה בעיצומה">
    <div class="num ink">${b(p.index)}<small>מתוך ${b(p.total)} שלבים</small></div>
    <div>
      <p class="k">כתיבה בעיצומה · ${esc(flowWord(run.flow))}</p>
      <h2>${auto(baseName(run.workspace) || flowWord(run.flow))}</h2>
      <p class="facts">${status(run.status)}<span>${esc(p.current ? 'עכשיו: ' + stepWord(run.flow, p.current.id) : 'בין שלבים')}</span><span>${esc(dur(run.elapsed_s))}</span></p>
      ${stepBar(run)}
    </div>
    <a class="btn" href="#writing" data-nav>לעמוד הכתיבה</a>
  </section>`;
}
function writerPage(st){
  const ov = st.overview, lib = ov.library || [];
  const projects = (ov.projects || []).map(w => line(
    `<a class="what" href="#writing" data-nav>${auto(w.name)}<span class="sub">${w.type === 'course' ? 'קורס' : 'פרויקט'}${w.runs ? ' · ' + many(w.runs, 'ריצה אחת', '# ריצות') : ''}</span></a>`,
    w.exists ? (w.last_run ? shortWhen(w.last_run) : 'עוד לא נכתב') : status('notfound')));
  const results = (ov.results || []).map(r => line(
    `<a class="what" href="#writing" data-nav>${auto(baseName(r.workspace))}<span class="sub">${esc(flowWord(r.flow))}${r.docx ? ' · ' + esc(baseName(r.docx)) : ''}${r.redrafted ? ' · ' + many(r.redrafted, 'סעיף אחד נכתב מחדש', '# סעיפים נכתבו מחדש') : ''}</span></a>`,
    status(r.status)));
  const books = lib.map(x => line(`<span class="what">${auto(x.title)}<span class="sub">${auto(x.workspace)}</span></span>`, shortWhen(x.added)));
  const col = (label, cls, title, rows, empty) => `<section class="col" aria-label="${label}">${head(cls, title)}${rows.length ? `<ul>${rows.slice(0, LIMIT).join('')}</ul>` : none(empty)}</section>`;
  return `${masthead(st)}${banners(st)}${writerCard(st)}
    <div class="cols ${lib.length ? 'three' : 'two'}">
      ${col('פרויקטים', 'r-indigo', 'פרויקטים', projects, 'עוד אין פרויקטים. תיקיית עבודה נרשמת כשמתחילים לכתוב בה.')}
      ${col('תוצאות אחרונות', 'r-violet', 'תוצאות אחרונות', results, 'עוד אין ריצות שהסתיימו.')}
      ${lib.length ? col('ספרייה', 'r-marker', 'ספרייה: נוספו השבוע', books, '') : ''}
    </div>`;
}

A.views.overview = (st, el) => {
  const writer = st.overview && st.overview.projects !== undefined;
  el.innerHTML = writer ? writerPage(st) : st.empty ? emptyPage(st) : studentPage(st);
  if (!writer && !st.empty && st.week_mode === 'week-ahead' && D(st.today).getDay() === 6) fillNextWeek(st, el);
};
})();
