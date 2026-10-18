/* Courses: one card per course with its colour spine, lecturer and slot, the next task, what is open (glyph + word),
   links, and the folder's writing status. Courses of a later semester sit below, quieter.
   Look: src/brand/DESIGN.md section 4 ("Course card"), Stitch screen "הקורסים שלי" (stitch-courses.png). */
(() => {
const A = window.AW;
const {esc, b, auto, D, DN, dm, dayDiff, today, status, hueClass} = A;

const many = (n, one, plural) => n === 1 ? one : plural.replace('#', n);
const DAYKEY = {Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6};
const SEM = {A: 'סמסטר א׳', B: 'סמסטר ב׳'};

function slotsText(c){
  const slots = (c.slots || []).map(s => `${DN[DAYKEY[s.day]] || esc(s.day)} ${b((s.start || '') + '–' + (s.end || ''))}`);
  if (slots.length) return slots.join(' · ');
  return c.mode === 'async' ? 'מקוון' : c.mode === 'zoom' ? 'בזום' : '';
}
function semesterText(c){
  const set = [...new Set((c.slots || []).map(s => SEM[s.semester]).filter(Boolean))];
  return set.join(' · ');
}
const metaLine = c => [c.lecturer ? auto(c.lecturer) : '', slotsText(c)].filter(Boolean).join(' · ');

/* ---------- what is open in a course ---------- */
function openActions(c){
  const items = c.tasks.filter(t => t.status !== 'submitted').flatMap(t => t.items || []).concat(c.more || []);
  const missing = c.tasks.filter(t => t.status !== 'submitted').reduce((n, t) => n + (t.missing_count || 0), 0);
  const queued = items.filter(i => i.queued).length;
  const ocr = items.filter(i => i.ocr && !i.queued).length;
  const out = [];
  if (missing) out.push(status('missing', many(missing, 'מקור אחד חסר', '# מקורות חסרים')));
  if (queued) out.push(status('night', many(queued, 'Claude יביא מקור אחד', 'Claude יביא # מקורות')));
  if (ocr) out.push(status('waiting', many(ocr, 'מקור אחד מחכה לזיהוי הטקסט', '# מקורות מחכים לזיהוי הטקסט')));
  if (c.perusall_open) out.push(status('waiting', many(c.perusall_open, 'קריאה אחת ב־Perusall לצילום', '# קריאות ב־Perusall לצילום')));
  if (c.unmatched_recordings) out.push(status('waiting', many(c.unmatched_recordings, 'הקלטה אחת לא שויכה', '# הקלטות לא שויכו')));
  if (c.new_lesson) out.push(status('ok', 'שיעור חדש תומלל'));
  const unready = c.tasks.some(t => t.status !== 'submitted' && t.state && t.state !== 'ready');
  if (!out.length) out.push(unready ? status('waiting', 'עוד לא כל המקורות אצלך') : status('ok', 'הכול מוכן'));
  return `<ul class="cc-open" aria-label="לטיפול">${out.map(s => `<li>${s}</li>`).join('')}</ul>`;
}

function nextTaskBlock(c){
  const t = c.next_task ? A.task(c.slug + '/' + c.next_task) : null;
  if (!t) return `<div class="cc-next"><p class="k">המטלה הבאה</p><p class="none">אין מטלה פתוחה.</p></div>`;
  const left = A.effDate(t) ? A.dueHTML(t) : 'בלי תאריך';
  const st = t.overdue ? status('missing', 'המועד עבר') : t.state === 'missing' ? status('missing', 'חסר מקור') :
    t.state === 'waiting' ? status(t.items.some(i => i.queued) ? 'night' : 'waiting') : t.state === 'ready' ? status('ok') : status('waiting', 'עוד לא כל המקורות');
  return `<div class="cc-next"><p class="k">${t.reading ? 'הקריאה הבאה' : t.exam ? 'המבחן הבא' : 'המטלה הבאה'}</p>
    <p class="t">${esc(t.title)}</p><p class="d">${left}</p><p>${st}</p></div>`;
}

/* ---------- links and folder ---------- */
function ext(href, text){ return `<a class="lnk" href="${esc(href)}" target="_blank" rel="noopener noreferrer">${text}</a>`; }
function linksRow(c){
  const L = c.links || {}, out = [];
  if (L.lemida) out.push(ext(L.lemida, 'למידה'));
  if (L.notebook) out.push(ext(L.notebook, b('NotebookLM')));
  if (L.drive) out.push(ext(L.drive, 'דרייב'));
  if (L.trove_url) out.push(ext(L.trove_url, b('Trove')));
  else if (L.trove_book_id) out.push(`<a class="lnk" href="#course/${encodeURIComponent(c.slug)}" data-nav>${b('Trove')}</a>`);
  if (L.wispr) out.push(ext(L.wispr, b('Wispr')));
  return out.length ? `<p class="cc-links">${out.join('<span class="dot" aria-hidden="true">·</span>')}</p>` : '';
}
function folderLine(st, c){
  const ws = (st.workspaces || []).find(w => w.type === 'course' && w.course === c.slug);
  if (!ws) return '';
  if (!ws.exists) return `<p class="cc-folder">תיקיית הכתיבה: ${status('notfound')}</p>`;
  const w = ws.runs ? `${many(ws.runs, 'ריצה אחת', '# ריצות')}${ws.last_status ? ' · ' + status(ws.last_status) : ''}` : 'עוד לא נכתב בה';
  return `<p class="cc-folder">תיקיית הכתיבה: ${w}</p>`;
}

/* ---------- cards ---------- */
function card(st, c){
  return `<article class="cc-card ${hueClass(c.color)}" aria-label="${esc(c.name)}">
    <header><h3><a href="#course/${encodeURIComponent(c.slug)}" data-nav>${auto(c.name)}</a></h3>
      ${semesterText(c) ? `<span class="label">${esc(semesterText(c))}</span>` : ''}</header>
    ${metaLine(c) ? `<p class="meta">${metaLine(c)}</p>` : ''}
    ${nextTaskBlock(c)}
    ${openActions(c)}
    ${linksRow(c)}${folderLine(st, c)}
  </article>`;
}
function quietCard(c){
  const first = (c.slots || []).map(s => SEM[s.semester]).find(Boolean);
  return `<article class="cc-card quiet ${hueClass(c.color)}" aria-label="${esc(c.name)}">
    <header><h3><a href="#course/${encodeURIComponent(c.slug)}" data-nav>${auto(c.name)}</a></h3>${first ? `<span class="label">${esc(first)}</span>` : ''}</header>
    ${metaLine(c) ? `<p class="meta">${metaLine(c)}</p>` : ''}
    <p class="label">${c.season === 'past' ? 'הקורס הסתיים' : 'עוד לא התחיל'}</p>
  </article>`;
}

/* ---------- page ---------- */
function stats(list){
  const open = list.flatMap(c => c.tasks.filter(t => t.status !== 'submitted'));
  const dated = open.filter(t => A.effDate(t)).sort((x, y) => A.effDate(x) < A.effDate(y) ? -1 : 1);
  const waiting = open.filter(t => ['waiting', 'pending', 'unlinked'].includes(t.state)).length;
  const next = dated[0];
  const nd = next ? dayDiff(today(), A.effDate(next)) : null;
  const nextWord = nd === null ? '—' : nd < 0 ? `${-nd} ימים באיחור` : nd === 0 ? 'היום' : nd === 1 ? 'מחר' : `${nd} ימים`;
  return `<dl class="cc-stats">
    <div><dt>פריטים פתוחים</dt><dd>${b(open.length)}</dd></div>
    <div><dt>מטלות שממתינות לחומרים</dt><dd>${b(waiting)}</dd></div>
    <div><dt>הדד־ליין הקרוב בעוד</dt><dd>${nd === null ? '—' : esc(nextWord)}</dd></div></dl>`;
}
function page(st){
  const all = st.courses || [];
  const active = all.filter(c => c.season !== 'later' && c.season !== 'past');
  const quiet = all.filter(c => c.season === 'later' || c.season === 'past');
  const term = st.term ? ` · ${auto(st.term)}` : '';
  if (!all.length)
    return `<header class="pagehead"><h1>הקורסים שלי</h1></header><section class="empty" aria-label="עוד אין קורסים"><img class="plate" src="img/hero-desk.webp" alt="" width="800" height="447"><div><p>עוד אין קורסים.</p><p>הריצו <code>/academic-writer:courses</code> כדי להגדיר את הסמסטר ואת הקורסים. הלוח יתעדכן מעצמו.</p></div></section>`;
  const lede = `${many(active.length, 'קורס אחד פעיל', '# קורסים פעילים')}${quiet.length ? ' · ' + many(quiet.length, 'עוד אחד בהמשך', 'עוד # בהמשך') : ''}.`;
  return `<header class="pagehead"><h1>הקורסים שלי${term}</h1><p class="lede">${lede}</p></header>
    ${stats(active.length ? active : all)}
    <section class="cc-sec" aria-labelledby="ccActive"><h2 id="ccActive">פעילים עכשיו</h2>
      ${active.length ? `<div class="cc-grid">${active.map(c => card(st, c)).join('')}</div>` : '<p class="notice">אין קורסים פעילים כרגע.</p>'}</section>
    ${quiet.length ? `<section class="cc-sec" aria-labelledby="ccQuiet"><h2 id="ccQuiet">בהמשך</h2><div class="cc-grid">${quiet.map(quietCard).join('')}</div></section>` : ''}`;
}

A.views.courses = (st, el) => { el.innerHTML = page(st); };
})();
