/* About: everything the plugin can do, from /about.json (generated from features.json by scripts/gen-about.py, so
   there is no hand-written list here). Each feature: plain description, the command that starts it, status
   (ok / partial) and how it is tested. Below: first steps by role, the viewer's own role first. */
(() => {
const A = window.AW;
const {esc, b, auto, status} = A;

const TESTED = {e2e: 'בדיקות מקצה לקצה', unit: 'בדיקות יחידה', manual: 'בדיקה ידנית', 'not tested yet': 'עוד לא נבדק'};
const STATE = {ok: ['ok', 'פועל'], partial: ['waiting', 'חלקי']};
const ROLES = [['student', 'סטודנטים'], ['lecturer', 'מרצים'], ['researcher', 'חוקרים']];

const tested = t => TESTED[t] || TESTED['not tested yet'];
const state = s => { const [k, w] = STATE[s] || ['unknown', 'לא ידוע']; return status(k, w); };
const cmd = c => c ? `<code>${esc(c)}</code>` : '';

function subs(list){
  if (!Array.isArray(list) || !list.length) return '';
  return `<details class="subs"><summary>${list.length === 1 ? 'פרט אחד' : `${b(list.length)} פרטים`}</summary>
    <ul>${list.map(s => `<li><span class="sname">${auto(s.name || s.id)}</span> ${state(s.status)} <span class="meta">${esc(tested(s.tested))}</span>${subs(s.subfeatures)}</li>`).join('')}</ul></details>`;
}
function feature(f){
  return `<article class="feat" aria-label="${esc(f.name_he || f.id)}">
    <header><h3>${auto(f.name_he || f.id)}</h3>${state(f.status)}</header>
    <p>${esc(f.description_he || '')}</p>
    <p class="meta">${cmd(f.command)}${f.command ? ' · ' : ''}נבדק: <strong>${esc(tested(f.tested))}</strong></p>
    ${subs(f.subfeatures)}</article>`;
}
function onboarding(data, role){
  const all = data.onboarding || {};
  const order = ROLES.filter(([k]) => Array.isArray(all[k]) && all[k].length).sort((x, y) => (y[0] === role) - (x[0] === role));
  if (!order.length) return '';
  const blocks = order.map(([k, word], i) => `<details class="role"${i === 0 ? ' open' : ''}><summary><strong>${esc(word)}</strong>${k === role ? ' <span class="meta">(התפקיד שלכם)</span>' : ''}</summary>
    <ol class="first">${all[k].map(s => `<li>${auto(s)}</li>`).join('')}</ol></details>`).join('');
  return `<section class="section" aria-label="צעדים ראשונים"><h2>צעדים ראשונים</h2>${blocks}
    <p class="meta guide">למדריך המלא: <code>${esc(data.guide || '/academic-writer:intro')}</code></p></section>`;
}
const dateText = st => { if (!st.today) return ''; const d = A.D(st.today); return `יום ${A.DN[d.getDay()]}, ${b(d.getDate())} ${A.MONTH[d.getMonth()]} ${b(d.getFullYear())}`; };

A.views.about = (st, el) => {
  const head = right => `<section class="pagehead" aria-label="אודות">
    <div class="dateline"><span>${dateText(st)}</span><span>${right}</span></div>
    <h1>אודות</h1><p class="lede">כל מה שהתוסף יודע לעשות, ואיך כל דבר נבדק. הרשימה נוצרת מעצמה מקובץ התכונות, כך שהיא לא נשארת מאחור.</p></section>`;
  el.innerHTML = head('') + '<p class="meta">טוען…</p>';
  A.api('/about.json').then(data => {
    if (el.dataset.view && el.dataset.view !== 'about') return;
    const feats = Array.isArray(data.features) ? data.features : [];
    const role = st.home && st.home.role;
    el.innerHTML = head(`גרסה ${b(data.version || '')} · ${b(feats.length)} תכונות`) +
      `<section class="section" aria-label="תכונות"><h2>מה אפשר לעשות</h2><div class="feats">${feats.map(feature).join('')}</div></section>` +
      onboarding(data, role);
  }).catch(() => {
    el.innerHTML = head('') + '<p class="notice">לא הצלחתי לקרוא את רשימת התכונות. אפשר לרענן את הדף.</p>';
  });
};
})();
