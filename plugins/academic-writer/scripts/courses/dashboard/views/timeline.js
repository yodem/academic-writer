/* Timeline: the semester by week. The current week is framed, a red "today" line runs through it, course filters
   narrow the list, each week is a table (date, course, item, kind, status as glyph + word), exams are emphasised,
   and a margin column notes what stands out. Past weeks and runs of empty weeks fold away.
   Everything is derived from state.timeline.weeks and state.courses; nothing is invented here.
   Look: src/brand/DESIGN.md section 4, Stitch screen "ציר זמן" (stitch-timeline.png). */
(() => {
const A = window.AW;
const {esc, b, auto, D, DL, DN, MONTH, dm, dayDiff, addDays, status, hueClass, S, saveS} = A;

const many = (n, one, plural) => n === 1 ? one : plural.replace('#', n);
const KIND = {exam: 'מבחן', reading: 'קריאה', submit: 'הגשה'};

/* viewer's filters: this browser only (saved in aw.dashboard.v2 through core's saveS) */
S.tl = S.tl && typeof S.tl === 'object' ? S.tl : {};
S.tl.hide = S.tl.hide && typeof S.tl.hide === 'object' && !Array.isArray(S.tl.hide) ? S.tl.hide : {};
let pastOpen = false;

/* ---------- derived facts ---------- */
const isOpen = i => i.status !== 'submitted';
function visible(item){
  if (S.tl.hide[item.course]) return false;
  if (S.tl.onlyDue && item.kind === 'reading') return false;
  return true;
}
function weekLabel(start){
  const a = D(start), z = D(addDays(start, 6));
  return a.getMonth() === z.getMonth() ?
    `${b(a.getDate() + '–' + z.getDate())} ${MONTH[a.getMonth()]}` :
    `${b(dm(start) + '–' + dm(addDays(start, 6)))}`;
}
const shortDate = iso => `${DL[D(iso).getDay()]} ${b(dm(iso))}`;

function itemStatus(i, t){
  if (i.status === 'submitted') return status('done', i.kind === 'reading' ? 'נקרא' : 'הוגש');
  if (t && t.overdue) return status('missing', 'המועד עבר');
  if (i.kind === 'exam') return status('waiting', 'מבחן קרוב');
  if (i.state === 'missing') return status('missing', 'חסר מקור');
  if (i.state === 'waiting') return status((t && t.items.some(x => x.queued)) ? 'night' : 'waiting');
  if (i.state === 'ready') return status('ok');
  return status('waiting', 'עוד לא כל המקורות');
}

/* ---------- one week ---------- */
function itemRow(i, st){
  const c = A.course(i.course), t = A.task(i.course + '/' + i.task);
  const where = t && t.exam && t.room ? ` · חדר ${esc(t.room)}` : '';
  const time = i.time ? ` · ${b(i.time)}` : '';
  const cls = ['tl-row', i.kind === 'exam' ? 'exam' : '', i.status === 'submitted' ? 'done' : '', i.date < st.today && isOpen(i) ? 'past' : ''].join(' ').trim();
  return `<tr class="${cls}">
    <td class="num2">${shortDate(i.date)}${time}</td>
    <td class="wrap"><span class="cname ${hueClass(c && c.color)}">${auto(c ? c.name : i.course)}</span></td>
    <td class="wrap"><a class="tl-what" href="#course/${encodeURIComponent(i.course)}" data-nav>${esc(i.title)}</a>${where}</td>
    <td class="num2">${KIND[i.kind] || ''}</td>
    <td class="num2">${itemStatus(i, t)}</td>
  </tr>`;
}
function todayRow(st){
  return `<tr class="tl-today" aria-label="היום"><td colspan="5"><span class="tl-now">היום · ${DN[D(st.today).getDay()]}, ${b(dm(st.today))}</span></td></tr>`;
}
function weekBlock(w, n, st, rows){
  const open = rows.filter(isOpen).length;
  let body = '';
  if (w.current){
    let placed = false;
    rows.forEach(i => { if (!placed && i.date > st.today){ body += todayRow(st); placed = true; } body += itemRow(i, st); });
    if (!placed) body += todayRow(st);
  } else body = rows.map(i => itemRow(i, st)).join('');
  const sum = rows.length ? many(open, 'פריט אחד פתוח', '# פריטים פתוחים') : 'פנוי';
  const head = `<header><h3>שבוע ${b(n)}<span class="when"> · ${weekLabel(w.start)}</span></h3>${w.current ? '<span class="tl-cur">השבוע הנוכחי</span>' : ''}<span class="label">${sum}</span></header>`;
  const table = rows.length || w.current ?
    `<div class="tscroll" tabindex="0" role="region" aria-label="שבוע ${n}"><table class="tl-table"><thead><tr><th>תאריך</th><th>קורס</th><th>פריט</th><th>סוג</th><th>סטטוס</th></tr></thead><tbody>${body}</tbody></table></div>` : '';
  return `<section class="tl-week${w.current ? ' current' : ''}" aria-label="שבוע ${n}">${head}${table}</section>`;
}
function gap(run, first){
  const a = run[0], z = run[run.length - 1];
  const label = run.length === 1 ? `שבוע ${b(first(a))} · ${weekLabel(a.start)} · פנוי` :
    `שבועות ${b(first(a) + '–' + first(z))} · ${b(dm(a.start) + '–' + dm(addDays(z.start, 6)))} · פנוי`;
  return `<p class="tl-gap">${label}</p>`;
}
function weeksHTML(weeks, st){
  const base = weeks.length ? weeks[0].start : st.today;
  const num = w => Math.floor(dayDiff(base, w.start) / 7) + 1;
  const prepared = weeks.map(w => ({w, rows: (w.items || []).filter(visible)}));
  const render = list => {
    let out = '', run = [];
    const flush = () => { if (run.length) out += gap(run, num); run = []; };
    list.forEach(({w, rows}) => {
      if (!rows.length && !w.current) run.push(w); else { flush(); out += weekBlock(w, num(w), st, rows); }
    });
    flush();
    return out;
  };
  const cut = prepared.findIndex(p => p.w.current || p.w.start > st.today);
  const split = cut < 0 ? prepared.length : cut;
  const past = prepared.slice(0, split).filter(p => p.rows.length), rest = prepared.slice(split);
  const pastBlock = past.length ?
    `<details class="tl-past" id="tlPast"${pastOpen ? ' open' : ''}><summary>שבועות קודמים · ${b(past.length)}</summary>${render(past)}</details>` : '';
  return pastBlock + render(rest);
}

/* ---------- filters ---------- */
function filtersHTML(st){
  const chips = (st.courses || []).map(c => {
    const on = !S.tl.hide[c.slug];
    return `<button class="tl-chip ${hueClass(c.color)}" type="button" id="tlf-${esc(c.slug)}" data-course="${esc(c.slug)}" aria-pressed="${on}"><span class="sq" aria-hidden="true"></span>${auto(c.name)}<span class="sr">${on ? ' (מוצג)' : ' (מוסתר)'}</span></button>`;
  }).join('');
  return `<div class="tl-filters" role="group" aria-label="סינון">
    <span class="label">סינון קורסים:</span>${chips}
    <label class="tl-only"><input type="checkbox" id="tlOnly"${S.tl.onlyDue ? ' checked' : ''}> רק הגשות ומבחנים</label>
  </div>`;
}

/* ---------- margin notes ---------- */
function marginNotes(st, weeks){
  const dated = weeks.flatMap(w => w.items || []);
  const open = dated.filter(isOpen);
  const notes = [];
  const busiest = weeks.map(w => [w, (w.items || []).filter(isOpen)]).filter(x => x[1].length >= 2 && x[0].start >= addDays(st.today, -6))
    .sort((x, y) => y[1].length - x[1].length || (x[0].start < y[0].start ? -1 : 1))[0];
  if (busiest) notes.push(`<section><h3>השבוע העמוס</h3><p>${weekLabel(busiest[0].start)}: ${many(busiest[1].length, 'פריט אחד', '# פריטים')}. כדאי להקדים.</p></section>`);
  const exam = (st.exams || []).find(e => e.due_date && e.due_date >= st.today);
  if (exam){
    const c = A.course(exam.course);
    notes.push(`<section><h3>המבחן הקרוב</h3><p><a class="lnk" href="#course/${encodeURIComponent(exam.course)}" data-nav>${esc(exam.title)}</a><span class="sub">${auto(c ? c.name : exam.course)} · ${shortDate(exam.due_date)}${exam.room ? ' · חדר ' + esc(exam.room) : ''}</span></p></section>`);
  }
  const missing = (st.courses || []).flatMap(c => c.tasks.filter(t => t.status !== 'submitted' && t.state === 'missing').map(t => [c, t]));
  if (missing.length){
    const [c, t] = missing[0];
    notes.push(`<section><h3>מקורות חסרים</h3><p>${many(missing.length, 'מטלה אחת עם מקור חסר', '# מטלות עם מקורות חסרים')}. הראשונה: <a class="lnk" href="#course/${encodeURIComponent(c.slug)}" data-nav>${esc(t.title)}</a>.</p></section>`);
  }
  const undated = (st.courses || []).reduce((n, c) => n + c.tasks.filter(t => t.status !== 'submitted' && !t.due_date).length, 0);
  if (undated) notes.push(`<section><h3>בלי תאריך</h3><p>${many(undated, 'מטלה פתוחה אחת', '# מטלות פתוחות')} בלי מועד, ולכן לא על הציר.</p></section>`);
  const done = dated.length - open.length;
  notes.push(`<section><h3>במספרים</h3><ul>
    <li class="ln"><span class="what">הוגשו או נקראו</span><span class="lead" aria-hidden="true"></span><span class="val">${b(done + ' / ' + dated.length)}</span></li>
    <li class="ln"><span class="what">עוד פתוחים</span><span class="lead" aria-hidden="true"></span><span class="val">${b(open.length)}</span></li></ul></section>`);
  return `<aside class="tl-margin" aria-label="בשולי הדף"><h2>בשולי הדף</h2>${notes.join('')}</aside>`;
}

/* ---------- page ---------- */
function page(st){
  const weeks = (st.timeline && st.timeline.weeks) || [];
  const dated = weeks.flatMap(w => w.items || []);
  if (!weeks.length || (!dated.length && !(st.courses || []).length))
    return `<header class="pagehead"><h1>ציר זמן</h1></header><section class="empty" aria-label="עוד אין נתונים"><img class="plate" src="img/hero-desk.webp" alt="" width="800" height="447"><div><p>עוד אין מה להציג על הציר.</p><p>כשיהיו קורסים ומטלות עם תאריכים, השבועות יופיעו כאן.</p></div></section>`;
  const exams = dated.filter(i => i.kind === 'exam' && isOpen(i)).length;
  const subs = dated.filter(i => i.kind === 'submit' && isOpen(i)).length;
  const term = st.term ? ` · ${auto(st.term)}` : '';
  return `<header class="pagehead"><h1>ציר זמן${term}</h1>
      <p class="tl-sum"><strong>${b(weeks.length)}</strong> שבועות <span class="sep" aria-hidden="true">|</span> ${many(subs, 'הגשה פתוחה אחת', '# הגשות פתוחות')} <span class="sep" aria-hidden="true">|</span> ${many(exams, 'מבחן אחד', '# מבחנים')}</p></header>
    ${filtersHTML(st)}
    <div class="tl-grid"><div class="tl-main" id="tlMain">${weeksHTML(weeks, st)}</div>${marginNotes(st, weeks)}</div>`;
}

function wire(st, el){
  el.querySelectorAll('.tl-chip').forEach(btn => btn.onclick = () => {
    const slug = btn.dataset.course;
    if (S.tl.hide[slug]) delete S.tl.hide[slug]; else S.tl.hide[slug] = true;
    saveS(); redraw(st, el, btn.id);
  });
  const only = el.querySelector('#tlOnly');
  if (only) only.onchange = () => { S.tl.onlyDue = only.checked; saveS(); redraw(st, el, 'tlOnly'); };
  const past = el.querySelector('#tlPast');
  if (past) past.addEventListener('toggle', () => { pastOpen = past.open; });
}
function redraw(st, el, focusId){
  el.innerHTML = page(st);
  wire(st, el);
  A.bidiFix(el);
  const f = focusId && document.getElementById(focusId); f && f.focus({preventScroll: true});
}

A.views.timeline = (st, el) => { el.innerHTML = page(st); wire(st, el); };
})();
