/* Course page: header in the course colour, tabs (tasks, sources, lessons and recordings, writing, storage), the
   next task as the one primary card with its sources table and "mark missing so Claude fetches it", earlier tasks,
   and a margin column (to handle, recent lessons, storage). Actions reuse core: markDone, undoDone, queueFetch.
   Look: src/brand/DESIGN.md section 4, mockups overview-sunday-v3 and dark-mode. */
(() => {
const A = window.AW;
const {esc, b, auto, $, $$, DN, dm, dueHTML, dueClass, fromIso, status, hueClass, TICK, CARET, NO, titleHTML, glossHTML,
       verbDone, markDone, undoDone, queueFetch, toast, SEL, tkey, S, saveS, rel, effDate, shortWhen} = A;

const many = (n, one, plural) => n === 1 ? one : plural.replace('#', n);
const DAYKEY = {Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6};
const SEM = {A: 'סמסטר א׳', B: 'סמסטר ב׳'};
const TABS = [['tasks', 'מטלות'], ['sources', 'מקורות'], ['lessons', 'שיעורים והקלטות'], ['writing', 'כתיבה'], ['storage', 'אחסון']];
const tabOf = {};                                  /* the open tab per course, kept across live updates */
const lessonWord = l => l.status === 'done' ? 'בטרוב' : l.status === 'appended' ? 'נכתב, עוד לא נבדק' : 'בתור';

/* ---------- sources ---------- */
function itemGloss(i){
  if (i.queued) return `<span class="gloss">Claude יחפש את זה בריצה הלילית. מה שדורש הורדה בדפדפן יהפוך למשימה אצלך.</span>`;
  if (i.type === 'chore') return `<span class="gloss red">לא נמצא בחומרי הקורס</span>`;
  if (i.missing) return `<span class="gloss red">${i.status === 'not-found' ? 'לא נמצא בספרייה' : 'קיים רק בדפוס, בלי טקסט'}</span>`;
  if (i.ocr === 'blocked' || i.ocr === 'flagged') return `<span class="gloss">הזיהוי האוטומטי של הטקסט סומן לבדיקה: כדאי להשוות לסריקה לפני שמצטטים</span>`;
  if (i.ocr === 'queued') return `<span class="gloss">ממתין לזיהוי הטקסט</span>`;
  if (i.downloaded || i.in_trove) return '';
  const words = {online: 'זמין ברשת, עוד לא הורד', kotar: 'בכותר, עוד לא הורד', pending: 'עוד לא חיפשו אותו בספרייה'};
  return words[i.status] ? `<span class="gloss">${words[i.status]}</span>` : '';
}
function sourceRow(i, taskId){
  const marks = [i.downloaded, i.in_trove, i.in_notebooklm].map(h => h ? TICK : NO);
  const id = `src-${i.type}-${i.key}${taskId ? '-' + taskId : ''}`;
  const pick = i.fetchable && i.type === 'ref' ?
    `<input type="checkbox" id="${esc(id)}" data-src="${esc(i.key)}" data-task="${esc(taskId || '')}"${SEL.has(i.key) ? ' checked' : ''} aria-label="לסמן את המקור כדי ש־Claude יביא אותו">` : '';
  return `<tr><td class="pick">${pick}</td><td class="wrap cite">${auto(i.title)}${itemGloss(i)}</td>${marks.map(m => `<td class="mk">${m}</td>`).join('')}</tr>`;
}
function sourceTable(items, taskId){
  return `<div class="tscroll" tabindex="0" role="region" aria-label="טבלת מקורות"><table class="cp-src">
    <thead><tr><th><span class="sr">בחירה</span></th><th>מקור</th><th>הורד</th><th>${b('Trove')}</th><th>${b('NotebookLM')}</th></tr></thead>
    <tbody>${items.map(i => sourceRow(i, taskId)).join('')}</tbody></table></div>`;
}
function fetchBar(){
  return `<div class="cp-fetchbar" id="fetchbar" hidden><p id="fetchTxt"></p><button class="btn" id="fetchBtn" type="button"></button></div>`;
}
function updateFetchbar(el){
  const bar = $('#fetchbar', el); if (!bar) return;
  const sel = $$('input[data-src]:checked', el);
  bar.hidden = !sel.length;
  $('#toast').classList.toggle('lifted', !!sel.length);
  if (!sel.length) return;
  $('#fetchTxt', el).textContent = sel.length === 1 ? 'נבחר מקור אחד. Claude יחפש אותו בריצה הלילית.' : `נבחרו ${sel.length} מקורות. Claude יחפש אותם בריצה הלילית.`;
  $('#fetchBtn', el).textContent = sel.length === 1 ? 'לבקש מ־Claude להביא את המקור' : `לבקש מ־Claude להביא ${sel.length} מקורות`;
}

/* ---------- tasks tab ---------- */
function when(t){
  return t.due_date ? `${t.reading ? 'לקרוא עד' : t.exam ? 'המבחן ב' : 'להגיש עד'} ${dueHTML(t, false)} <span class="label">· ${rel(effDate(t))}</span>` : 'בלי תאריך הגשה';
}
function taskBody(t){
  const desc = t.desc ? `<p class="desc">${esc(t.desc)}</p>` : '';
  const core = (t.core_texts || []).length ? `<p class="desc">טקסטי ליבה: ${t.core_texts.map(auto).join('; ')}</p>` : '';
  const exam = t.exam && (t.room || t.material) ? `<p class="desc">${t.room ? 'חדר ' + esc(t.room) : ''}${t.room && t.material ? ' · ' : ''}${t.material ? 'חומר: ' + esc(t.material) : ''}</p>` : '';
  return desc + core + exam;
}
function actions(t){
  const done = t.status === 'submitted';
  const lem = t.lemida_url ? `<a class="lnk" href="${esc(t.lemida_url)}" target="_blank" rel="noopener noreferrer">לפתוח בלמידה</a>` : '';
  if (done) return `<div class="acts"><button class="btn secondary" id="undo-${esc(tkey(t))}" data-undo="${esc(tkey(t))}" type="button">לבטל את הסימון</button><span class="label">סימנת ש${t.reading ? 'קראת' : 'הגשת'}. ${t.reading ? 'הקריאה' : 'המטלה'} ירדה מהסקירה.</span></div>`;
  return `<div class="acts"><button class="btn secondary" id="done-${esc(tkey(t))}" data-done="${esc(tkey(t))}" type="button">${verbDone(t)}</button>${lem}</div>`;
}
function primaryCard(t){
  const items = t.items || [];
  return `<article class="card cp-next" data-slip="${esc(t.id)}" aria-label="${t.reading ? 'הקריאה הבאה' : 'המטלה הבאה'}">
    <p class="k">${t.reading ? 'הקריאה הבאה' : t.exam ? 'המבחן הבא' : 'המטלה הבאה'} · ${esc(t.kind_word)}</p>
    <h2>${titleHTML(t)}</h2>
    <p class="when${dueClass(t)}">${when(t)}</p>${glossHTML(t)}${taskBody(t)}
    ${items.length ? `<h3 class="cp-sub">מקורות למטלה</h3><p class="label">לסמן מקור חסר כדי ש־Claude יביא אותו</p>${sourceTable(items, t.id)}` : '<p class="label cp-sub">עוד לא קושרו מקורות למטלה הזאת.</p>'}
    ${actions(t)}
  </article>`;
}
function slip(t){
  const done = t.status === 'submitted';
  return `<article class="cp-slip${done ? ' done' : ''}" data-slip="${esc(t.id)}">
    <span class="kind">${esc(t.kind_word)}</span><h3>${titleHTML(t)}</h3>
    <p class="when">${when(t)}</p>${taskBody(t)}${actions(t)}</article>`;
}
function tasksTab(c){
  const open = c.tasks.filter(t => t.status !== 'submitted');
  const recent = c.tasks.filter(t => t.status === 'submitted' && t.recently_submitted);
  const older = c.tasks.filter(t => t.status === 'submitted' && !t.recently_submitted);
  const next = open.find(t => t.id === c.next_task) || open[0];
  const rest = open.filter(t => t !== next);
  const empty = `<div class="empty"><img class="plate" src="img/revise.webp" alt="" width="800" height="598"><div><p>אין מטלות פתוחות בקורס הזה.</p><p>${c.perusall_open ? many(c.perusall_open, 'קריאה אחת', '# קריאות') + ' ב־Perusall עוד לא צולמו. ' : ''}כשתעלה מטלה ללמידה, היא תופיע כאן אחרי הסריקה הבאה.</p></div></div>`;
  const more = (c.more || []).length ? `<details class="cp-more"><summary>המרצה הזכיר עוד · ${b(c.more.length)}</summary>${sourceTable(c.more, '')}</details>` : '';
  return (next ? primaryCard(next) : empty) +
    (rest.length ? `<section class="cp-sec"><h2>עוד פתוח</h2>${rest.map(slip).join('')}</section>` : '') +
    (recent.length ? `<section class="cp-sec"><h2>הוגשו לאחרונה</h2>${recent.map(slip).join('')}</section>` : '') +
    more + fetchBar() +
    (older.length ? `<section class="cp-sec prev"><h2>מטלות קודמות</h2><ul>${older.map(t => `<li class="ln"><span class="what">${titleHTML(t)}</span><span class="lead" aria-hidden="true"></span><span class="val">${t.due_date ? dueHTML(t) : ''}</span></li>`).join('')}</ul></section>` : '');
}

/* ---------- other tabs ---------- */
function sourcesTab(c){
  const all = [], seen = new Set();
  c.tasks.filter(t => t.status !== 'submitted').forEach(t => (t.items || []).forEach(i => { const k = i.type + i.key; if (!seen.has(k)){ seen.add(k); all.push([i, t.id]); } }));
  (c.more || []).forEach(i => { const k = i.type + i.key; if (!seen.has(k)){ seen.add(k); all.push([i, '']); } });
  if (!all.length) return `<p class="notice">עוד אין מקורות בקורס הזה.</p>`;
  const rows = all.map(([i, tid]) => sourceRow(i, tid)).join('');
  return `<p class="label">לסמן מקור חסר כדי ש־Claude יביא אותו</p><div class="tscroll" tabindex="0" role="region" aria-label="כל המקורות"><table class="cp-src">
    <thead><tr><th><span class="sr">בחירה</span></th><th>מקור</th><th>הורד</th><th>${b('Trove')}</th><th>${b('NotebookLM')}</th></tr></thead><tbody>${rows}</tbody></table></div>${fetchBar()}`;
}
function lessonsTab(c){
  const list = c.lessons.length ? `<ul class="cp-list">${c.lessons.map((l, k) => `<li class="ln"><span class="what">שיעור ${b(k + 1)}${l.date ? ' · ' + b(dm(l.date)) : ''}${l.new ? ' ' + CARET + '<span class="sr"> (חדש)</span>' : ''}</span><span class="lead" aria-hidden="true"></span><span class="val">${lessonWord(l)}</span></li>`).join('')}</ul>` : '<p class="notice">עוד אין שיעורים מתומללים.</p>';
  const un = c.unmatched_recordings ? `<p class="cp-note">${status('waiting', many(c.unmatched_recordings, 'הקלטה אחת לא שויכה לשיעור', '# הקלטות לא שויכו לשיעור'))}</p>` : '';
  const w = c.links && c.links.wispr ? `<p><a class="lnk" href="${esc(c.links.wispr)}" target="_blank" rel="noopener noreferrer">${b('Wispr')}: ההקלטות של הקורס</a></p>` : '';
  return `${list}${un}${w}`;
}
function writingTab(st, c){
  const ws = (st.workspaces || []).find(w => w.type === 'course' && w.course === c.slug);
  if (!ws) return `<p class="notice">עוד אין תיקיית כתיבה לקורס הזה. היא נרשמת כשמתחילים לכתוב בו: <code class="path">/academic-writer:write</code></p>`;
  const state = !ws.exists ? status('notfound') : ws.runs ? `${many(ws.runs, 'ריצה אחת', '# ריצות')}${ws.last_status ? ' · ' + status(ws.last_status) : ''}` : 'עוד לא נכתב בה';
  const nav = st.nav && st.nav.includes('writing');
  return `<ul class="cp-list"><li class="ln"><span class="what">תיקייה<span class="sub"><code class="path">${esc(ws.path)}</code></span></span><span class="lead" aria-hidden="true"></span><span class="val">${state}</span></li>
    ${ws.last_run ? `<li class="ln"><span class="what">ריצה אחרונה</span><span class="lead" aria-hidden="true"></span><span class="val">${shortWhen(ws.last_run)}</span></li>` : ''}</ul>
    ${nav ? '<p><a class="lnk" href="#writing" data-nav>לעמוד הכתיבה</a></p>' : ''}`;
}
function storageTab(c){
  const s = c.storage || {}, L = c.links || {}, book = s.trove_book_id;
  const row = (k, v) => `<li class="ln"><span class="what">${k}</span><span class="lead" aria-hidden="true"></span><span class="val">${v}</span></li>`;
  return `<ul class="cp-list">
    ${row('ספר בטרוב', book ? `יש <code class="bid">${esc(book)}</code> <button class="copy" id="copyBook" data-copy="${esc(book)}" type="button">להעתיק</button>` : '—')}
    ${row(b('NotebookLM'), s.notebook_sources === 1 ? 'מקור אחד' : b(s.notebook_sources || 0) + ' מקורות')}
    ${row('דרייב', L.drive ? 'תיקייה' : '—')}
    ${row('מסמכים בספרייה', b(s.sources || 0))}
    ${row('ציטוטים שנאספו', b(s.refs || 0))}</ul>`;
}

/* ---------- header, links, margin ---------- */
function slotsText(c){
  const slots = c.slots.map(s => `${DN[DAYKEY[s.day]] || esc(s.day)} ${b((s.start || '') + '–' + (s.end || ''))}${SEM[s.semester] ? ' · ' + SEM[s.semester] : ''}`);
  return [].concat(slots, c.mode === 'async' ? ['מקוון'] : c.mode === 'zoom' && !slots.length ? ['בזום'] : [],
    c.lecturer ? [auto(c.lecturer)] : [], c.lessons.length ? [many(c.lessons.length, 'שיעור אחד מתומלל', '# שיעורים מתומללים')] : []).join(' · ');
}
function linksHTML(c){
  const L = c.links, out = [];
  const ext = (h, t) => `<a class="lnk" href="${esc(h)}" target="_blank" rel="noopener noreferrer">${t}</a>`;
  if (L.lemida) out.push(ext(L.lemida, 'למידה'));
  if (L.notebook) out.push(ext(L.notebook, b('NotebookLM')));
  if (L.trove_url) out.push(ext(L.trove_url, b('Trove')));
  if (L.drive) out.push(ext(L.drive, 'דרייב'));
  if (L.wispr) out.push(ext(L.wispr, b('Wispr')));
  return out.length ? `<p class="c-links">${out.join(' · ')}</p>` : '';
}
function rail(c){
  const notices = c.notices.slice(0, 6).map(n => { const p = fromIso(n.due_at); return `<li class="ln"><span class="what">${auto(n.title)}</span><span class="lead" aria-hidden="true"></span><span class="val">${p ? b(dm(p.date)) : ''}</span></li>`; }).join('') +
    (c.notices.length > 6 ? `<li class="label">ועוד ${b(c.notices.length - 6)}</li>` : '');
  const lessons = c.lessons.slice(-3).reverse().map(l => `<li class="ln"><span class="what">${l.date ? b(dm(l.date)) : 'ללא תאריך'}${l.new ? ' ' + CARET + '<span class="sr"> (חדש)</span>' : ''}</span><span class="lead" aria-hidden="true"></span><span class="val">${lessonWord(l)}</span></li>`).join('');
  const s = c.storage || {};
  return `<aside class="cp-rail" aria-label="בשולי הקורס">
    <section><h3>לטיפול שלך</h3>${notices ? `<ul>${notices}</ul>` : '<p class="none">אין דברים פתוחים.</p>'}</section>
    ${lessons ? `<section><h3>שיעורים אחרונים</h3><ul>${lessons}</ul></section>` : ''}
    <section><h3>אחסון</h3><ul>
      <li class="ln"><span class="what">ספר בטרוב</span><span class="lead" aria-hidden="true"></span><span class="val">${s.trove_book_id ? 'יש' : '—'}</span></li>
      <li class="ln"><span class="what">${b('NotebookLM')}</span><span class="lead" aria-hidden="true"></span><span class="val">${s.notebook_sources === 1 ? 'מקור אחד' : b(s.notebook_sources || 0) + ' מקורות'}</span></li>
      <li class="ln"><span class="what">דרייב</span><span class="lead" aria-hidden="true"></span><span class="val">${s.drive ? 'תיקייה' : '—'}</span></li></ul></section>
  </aside>`;
}

/* ---------- page ---------- */
function render(st, el, slug){
  const c = A.course(slug);
  if (!c){
    el.innerHTML = `<p class="crumb"><a href="#overview">סקירה</a></p><header class="pagehead"><h1>אין קורס כזה</h1><p class="lede">אולי הוא הוסר מהרישום. אפשר לחזור לרשימת הקורסים.</p></header>`;
    return;
  }
  S.lastCourse = slug; saveS();
  const tab = tabOf[slug] || 'tasks';
  const body = tab === 'sources' ? sourcesTab(c) : tab === 'lessons' ? lessonsTab(c) : tab === 'writing' ? writingTab(st, c) : tab === 'storage' ? storageTab(c) : tasksTab(c);
  const crumbRoot = st.nav && st.nav.includes('courses') ? ['courses', 'קורסים'] : ['overview', 'סקירה'];
  el.innerHTML = `
    <p class="crumb"><a href="#${crumbRoot[0]}">${crumbRoot[1]}</a> / ${auto(c.name)}</p>
    <header class="c-head ${hueClass(c.color)}">
      <h1 class="c-title">${auto(c.name)}</h1>
      ${slotsText(c) ? `<p class="c-meta">${slotsText(c)}</p>` : ''}${linksHTML(c)}
    </header>
    <div class="cp-tabs" role="tablist" aria-label="חלקי הקורס">${TABS.map(([id, label]) =>
      `<button type="button" role="tab" id="tab-${id}" data-tab="${id}" aria-selected="${id === tab}" aria-controls="panel" tabindex="${id === tab ? 0 : -1}">${label}</button>`).join('')}</div>
    <div class="cp-grid"><div class="cp-main" id="panel" role="tabpanel" aria-labelledby="tab-${tab}">${body}</div>${rail(c)}</div>`;
  wire(st, el, slug, c);
}
function wire(st, el, slug, c){
  const tabs = $$('[data-tab]', el);
  tabs.forEach((t, i) => {
    t.onclick = () => { tabOf[slug] = t.dataset.tab; render(st, el, slug); A.bidiFix(el); const n = $('#tab-' + t.dataset.tab, el); n && n.focus(); };
    t.onkeydown = e => {
      /* RTL: the left arrow moves to the next tab */
      const d = e.key === 'ArrowLeft' ? 1 : e.key === 'ArrowRight' ? -1 : 0;
      if (!d) return;
      e.preventDefault(); tabs[(i + d + tabs.length) % tabs.length].click();
    };
  });
  $$('[data-done]', el).forEach(btn => btn.onclick = () => markDone(btn.dataset.done));
  $$('[data-undo]', el).forEach(btn => btn.onclick = () => undoDone(btn.dataset.undo));
  $$('input[data-src]', el).forEach(i => i.onchange = () => { i.checked ? SEL.add(i.dataset.src) : SEL.delete(i.dataset.src); updateFetchbar(el); });
  const fb = $('#fetchBtn', el); if (fb) fb.onclick = () => queueFetch(slug, $$('input[data-src]:checked', el));
  const cp = $('#copyBook', el);
  if (cp) cp.onclick = () => { navigator.clipboard && navigator.clipboard.writeText(cp.dataset.copy).then(() => toast('מספר הספר בטרוב הועתק.'), () => toast('לא הצלחתי להעתיק.')); };
  updateFetchbar(el);
}

A.views.course = (st, el) => render(st, el, A.route().id);
})();
