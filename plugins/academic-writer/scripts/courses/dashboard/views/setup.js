/* Setup: the checklist of what the plugin needs, read-only. The rows come from the same deterministic checks as
   /academic-writer:health (st.setup.checks, run by setup_checks.py). Nothing is fixed here: each row names the
   command to ask Claude for. Required checks first, optional ones apart. Look: brand file §4, "ברוכים הבאים". */
(() => {
const A = window.AW;
const {esc, b, auto, status, toast} = A;

const many = (n, one, plural) => n === 1 ? one : plural.replace('#', n);
const isReq = c => !c.optional;

/* ok true = ready; false = missing (an optional gap is "waiting", not an error); null = not relevant here */
function mark(c){
  if (c.ok === true) return status('ok');
  if (c.ok === false) return c.optional ? status('waiting', 'לא חובה') : status('missing');
  return status('unknown', 'לא רלוונטי');
}
function detail(c){
  const bits = [];
  if (c.ok === true && c.found) bits.push(`נמצא: ${auto(c.found)}`);
  if (c.required) bits.push(`נדרש: ${auto(c.required)}`);
  if (c.ok !== true && c.found) bits.push(`נמצא: ${auto(c.found)}`);
  if (c.ok !== true && c.reason_he) bits.push(esc(c.reason_he));
  return bits.length ? `<p class="meta">${bits.join(' · ')}</p>` : '';
}
function fixLine(c){
  if (c.ok !== false || !c.fix) return '';
  return `<p class="fix"><span class="meta">לבקש מ־Claude לתקן:</span> <code>${esc(c.fix)}</code>
    <button class="copy" data-copy="${esc(c.fix)}">העתקת הפקודה</button></p>`;
}
function row(c){
  return `<li class="check"><div class="what"><strong>${auto(c.label_he || c.id)}</strong>${detail(c)}${fixLine(c)}</div>
    <div class="state">${mark(c)}</div></li>`;
}
function group(title, rows){
  if (!rows.length) return '';
  return `<section class="section" aria-label="${esc(title)}"><h2>${esc(title)}</h2><ul class="checks">${rows.map(row).join('')}</ul></section>`;
}
const dateText = st => { const d = A.D(st.today); return `יום ${A.DN[d.getDay()]}, ${b(d.getDate())} ${A.MONTH[d.getMonth()]} ${b(d.getFullYear())}`; };

A.views.setup = (st, el) => {
  const s = st.setup || {complete: null, checks: []}, checks = s.checks || [];
  const missing = checks.filter(c => isReq(c) && c.ok === false);
  const optMissing = checks.filter(c => c.optional && c.ok === false);
  let lede;
  if (!checks.length) lede = 'עוד לא נבדק דבר. נסו לרענן עוד רגע.';
  else if (s.complete === false) lede = `${many(missing.length || 1, 'דבר אחד חסר', '# דברים חסרים')} לפני שהכול עובד. ליד כל שורה כתוב מה לבקש מ־Claude.`;
  else lede = optMissing.length ? `הכול מוכן. ${many(optMissing.length, 'כלי אחד לא חובה עוד לא מותקן', '# כלים לא חובה עוד לא מותקנים')}.` : 'הכול מוכן.';
  let html = `<section class="pagehead" aria-label="הגדרה">
    <div class="dateline"><span>${st.today ? dateText(st) : ''}</span><span>${checks.length ? `${b(checks.filter(c => c.ok === true).length)} מתוך ${b(checks.length)} מוכנים` : ''}</span></div>
    <h1>הגדרה</h1><p class="lede">${esc(lede)} העמוד הזה רק קורא ומראה: הוא לא מתקין ולא משנה שום דבר.</p></section>`;
  if (st.home && st.home.missing) html += `<p class="banner"><span>${status('missing', 'תיקיית הבית לא נמצאה')}</span><span>התיקייה זזה או נמחקה. לבקש מ־Claude לבחור תיקייה מחדש: <code>/academic-writer:setup</code></span></p>`;
  if (!checks.length){
    html += `<section class="empty" aria-label="אין בדיקות"><div><p>עוד לא נבדק דבר.</p><p>אפשר להריץ <code>/academic-writer:health</code> בטרמינל.</p></div></section>`;
  } else {
    html += group('חובה', checks.filter(isReq)) + group('לא חובה', checks.filter(c => c.optional));
    if (s.complete) html += `<section class="section" aria-label="מה עכשיו"><h2>מה עכשיו</h2><p>אפשר להתחיל: <a class="lnk" href="#about">מה אפשר לעשות עם התוסף</a>.</p></section>`;
  }
  el.innerHTML = html;
  el.querySelectorAll('[data-copy]').forEach(btn => btn.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(btn.dataset.copy); toast('הפקודה הועתקה.'); }
    catch(e) { toast('לא הצלחתי להעתיק. הפקודה: ' + esc(btn.dataset.copy)); }
  }));
};
})();
