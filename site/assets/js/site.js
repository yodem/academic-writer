/* Academic Writer site: theme, language, copy, hero demo, scrollytelling, reveals. Vanilla, no deps. */
(function () {
  'use strict';
  var d = document, root = d.documentElement;
  var $ = function (s, c) { return (c || d).querySelector(s); };
  var $$ = function (s, c) { return Array.prototype.slice.call((c || d).querySelectorAll(s)); };
  var HE = window.AW_I18N_HE || {};
  var reduceMQ = window.matchMedia('(prefers-reduced-motion: reduce)');
  var store = {
    get: function (k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set: function (k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
    del: function (k) { try { localStorage.removeItem(k); } catch (e) { /* private mode */ } }
  };

  /* English strings used only by script (the Hebrew ones live in AW_I18N_HE under the same keys). */
  var EN = {
    copied: 'Copied', pause: 'Pause animation', play: 'Play animation',
    theme_system: 'Theme: match system. Change theme', theme_light: 'Theme: light. Change theme', theme_dark: 'Theme: dark. Change theme',
    step: 'Step', doc_title: 'Academic Writer — cited academic articles with Claude'
  };
  var lang = root.lang === 'he' ? 'he' : 'en';
  function t(key) { return (lang === 'he' && HE[key]) || EN[key] || (function () { var n = d.querySelector('[data-i18n="' + key + '"]'); return n && n.__en; })() || key; }

  /* ---------- i18n ---------- */
  var nodes = [];
  function collect() {
    $$('[data-i18n],[data-i18n-html],[data-i18n-attr]').forEach(function (el) {
      var rec = { el: el };
      if (el.hasAttribute('data-i18n')) { rec.key = el.getAttribute('data-i18n'); rec.en = el.textContent; el.__en = rec.en; }
      if (el.hasAttribute('data-i18n-html')) { rec.hkey = el.getAttribute('data-i18n-html'); rec.hen = el.innerHTML; }
      if (el.hasAttribute('data-i18n-attr')) {
        rec.attrs = el.getAttribute('data-i18n-attr').split(';').map(function (p) {
          var i = p.indexOf(':'); var a = p.slice(0, i).trim();
          return { a: a, k: p.slice(i + 1).trim(), en: el.getAttribute(a) };
        });
      }
      nodes.push(rec);
    });
  }
  function applyLang(l, persist) {
    lang = l === 'he' ? 'he' : 'en';
    root.lang = lang; root.dir = lang === 'he' ? 'rtl' : 'ltr';
    nodes.forEach(function (r) {
      if (r.key !== undefined) r.el.textContent = (lang === 'he' && HE[r.key] != null) ? HE[r.key] : r.en;
      if (r.hkey !== undefined) r.el.innerHTML = (lang === 'he' && HE[r.hkey] != null) ? HE[r.hkey] : r.hen;
      if (r.attrs) r.attrs.forEach(function (x) { r.el.setAttribute(x.a, (lang === 'he' && HE[x.k] != null) ? HE[x.k] : x.en); });
    });
    $$('.seg button').forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-lang') === lang)); });
    d.title = t('doc_title');
    var sheet = $('#demo-sheet'); if (sheet) { sheet.lang = lang; sheet.dir = lang === 'he' ? 'rtl' : 'ltr'; }
    setThemeLabel(); labelRail(); labelPause(); syncTracks();
    if (persist) store.set('aw-lang', lang);
    if (demoApi) demoApi.restart();
    if (storyApi) storyApi.update();
  }
  collect();

  /* ---------- version ---------- */
  var ver = root.getAttribute('data-version') || '';
  $$('[data-ver]').forEach(function (n) { n.textContent = ver; });

  /* ---------- theme ---------- */
  var themeBtn = $('#theme-btn');
  var modes = ['system', 'light', 'dark'];
  function curMode() { var v = root.getAttribute('data-theme'); return v === 'light' || v === 'dark' ? v : 'system'; }
  function setThemeLabel() { if (!themeBtn) return; var m = curMode(); themeBtn.setAttribute('data-mode', m); themeBtn.setAttribute('aria-label', t('theme_' + m)); }
  if (themeBtn) themeBtn.addEventListener('click', function () {
    var next = modes[(modes.indexOf(curMode()) + 1) % 3];
    if (next === 'system') { root.removeAttribute('data-theme'); store.del('aw-theme'); }
    else { root.setAttribute('data-theme', next); store.set('aw-theme', next); }
    setThemeLabel();
  });

  /* ---------- language buttons ---------- */
  $$('.seg button').forEach(function (b) { b.addEventListener('click', function () { applyLang(b.getAttribute('data-lang'), true); }); });

  /* ---------- mobile menu ---------- */
  var menuBtn = $('#menu-btn'), nav = $('#nav');
  function closeMenu() { if (!nav) return; nav.classList.remove('is-open'); menuBtn.setAttribute('aria-expanded', 'false'); }
  if (menuBtn && nav) {
    menuBtn.addEventListener('click', function () { var o = nav.classList.toggle('is-open'); menuBtn.setAttribute('aria-expanded', String(o)); });
    nav.addEventListener('click', function (e) { if (e.target.closest('a')) closeMenu(); });
    d.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeMenu(); });
  }

  /* ---------- copy buttons ---------- */
  function fallbackCopy(text) {
    var ta = d.createElement('textarea'); ta.value = text; ta.setAttribute('readonly', ''); ta.style.cssText = 'position:fixed;opacity:0;top:0';
    d.body.appendChild(ta); ta.select(); try { d.execCommand('copy'); } catch (e) { /* ignore */ } d.body.removeChild(ta);
  }
  $$('.copy').forEach(function (btn) {
    var label = $('.copy__t', btn), tm;
    btn.addEventListener('click', function () {
      var text = btn.getAttribute('data-copy') || '';
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).catch(function () { fallbackCopy(text); });
      else fallbackCopy(text);
      btn.classList.add('is-done'); label.textContent = t('copied');
      clearTimeout(tm);
      tm = setTimeout(function () { btn.classList.remove('is-done'); label.textContent = t('copy'); }, 1800);
    });
  });

  /* ---------- reveals ---------- */
  var rv = $$('.rv');
  if (!('IntersectionObserver' in window) || reduceMQ.matches) rv.forEach(function (n) { n.classList.add('in'); });
  else {
    var rvIO = new IntersectionObserver(function (es) {
      es.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add('in'); rvIO.unobserve(e.target); } });
    }, { rootMargin: '0px 0px -8% 0px', threshold: 0.08 });
    rv.forEach(function (n) { rvIO.observe(n); });
  }

  /* ---------- hero demo ---------- */
  var demoApi = (function () {
    var demo = $('#demo'); if (!demo) return null;
    var live = $('[data-demo-text]', demo), ghost = $('.demo__ghost [data-i18n]', demo), btn = $('#demo-pause');
    var gen = 0, timers = [], paused = false, visible = true;
    function clear() { timers.forEach(clearTimeout); timers = []; }
    function at(ms, fn, my) { timers.push(setTimeout(function () { if (my === gen) fn(); }, ms)); }
    function showFinal() { clear(); gen++; live.textContent = ghost.textContent; demo.setAttribute('data-step', '3'); demo.classList.remove('is-reset'); }
    function run() {
      clear(); var my = ++gen;
      if (reduceMQ.matches) { showFinal(); return; }
      if (paused || !visible) return;
      var text = ghost.textContent, i = 0;
      demo.classList.remove('is-reset'); demo.setAttribute('data-step', '0'); live.textContent = '';
      (function type() {
        if (my !== gen) return;
        i += 2; live.textContent = text.slice(0, i);
        if (i < text.length) timers.push(setTimeout(type, 34));
        else {
          at(250, function () { demo.setAttribute('data-step', '1'); }, my);
          at(1000, function () { demo.setAttribute('data-step', '2'); }, my);
          at(1800, function () { demo.setAttribute('data-step', '3'); }, my);
          at(5300, function () { demo.classList.add('is-reset'); }, my);
          at(5600, run, my);
        }
      })();
    }
    function stop() { clear(); gen++; }
    if (btn) btn.addEventListener('click', function () {
      paused = !paused; btn.setAttribute('aria-pressed', String(paused)); labelPause();
      if (paused) stop(); else run();
    });
    if ('IntersectionObserver' in window) new IntersectionObserver(function (es) {
      visible = es[0].isIntersecting;
      if (!visible) stop(); else if (!paused) run();
    }, { threshold: 0.2 }).observe(demo);
    reduceMQ.addEventListener && reduceMQ.addEventListener('change', run);
    return { restart: function () { if (reduceMQ.matches || paused) showFinal(); else run(); } };
  })();
  function labelPause() { var b = $('#demo-pause'); if (!b) return; $('.pause__t', b).textContent = t(b.getAttribute('aria-pressed') === 'true' ? 'play' : 'pause'); }

  /* ---------- film captions follow the language ---------- */
  function syncTracks() {
    var v = $('#film-video'); if (!v || !v.textTracks) return;
    for (var i = 0; i < v.textTracks.length; i++) v.textTracks[i].mode = v.textTracks[i].language === lang ? 'showing' : 'disabled';
  }
  (function () { var v = $('#film-video'); if (v) v.addEventListener('loadedmetadata', syncTracks); })();

  /* ---------- film fallback ---------- */
  (function () {
    var v = $('#film-video'), sec = $('#film'); if (!v) return;
    var fail = function () { sec.classList.add('film--fail'); };
    v.addEventListener('error', fail);
    var srcs = $$('source', v); if (srcs.length) srcs[srcs.length - 1].addEventListener('error', fail);
  })();

  /* ---------- gate diagram: reveal observer handles .in ---------- */

  /* ---------- scrollytelling ---------- */
  var storyApi = (function () {
    var sec = $('#how'), grid = $('#story'); if (!sec || !grid) return null;
    var stageWrap = $('.stage-wrap', grid), stage = $('#stage'), body = $('.stage__body', grid), rail = $('.rail', grid);
    var steps = $$('.step', grid), scenes = steps.map(function (s) { return $('.scene', s); });
    var titles = $$('.stage__frame .frame__title', stage), count = $('[data-count]', stage);
    var dots = $$('.rail li', grid), links = $$('.rail a', grid);
    var bar = $('#bar'), mobileMQ = window.matchMedia('(max-width: 899px)');
    var pinned = false, inView = false, ticking = false, cur = -1, lastP = -1, lastG = -1;

    function enable() {
      if (pinned) return; pinned = true;
      scenes.forEach(function (s) { body.appendChild(s); });
      sec.classList.add('is-pinned'); cur = -1; update();
    }
    function disable() {
      if (!pinned) return; pinned = false;
      scenes.forEach(function (s, i) { $('.frame__body', steps[i]).appendChild(s); s.classList.remove('is-on'); });
      sec.classList.remove('is-pinned');
      stage.style.removeProperty('--p'); grid.style.removeProperty('--g');
      steps.forEach(function (s) { s.classList.remove('is-on'); });
    }
    function sync() { if (reduceMQ.matches) disable(); else enable(); }

    function geometry() {
      var vh = window.innerHeight, barH = bar ? bar.offsetHeight : 56, top = barH;
      if (mobileMQ.matches) top = barH + stageWrap.offsetHeight + rail.offsetHeight;
      var centers = steps.map(function (s) { var r = s.getBoundingClientRect(); return r.top + r.height / 2; });
      return { focus: (top + vh) / 2, centers: centers };
    }
    function uOf(g) {
      var c = g.centers, f = g.focus, n = c.length - 1;
      if (f <= c[0]) return 0;
      if (f >= c[n]) return n;
      for (var i = 0; i < n; i++) if (f < c[i + 1]) return i + (f - c[i]) / (c[i + 1] - c[i]);
      return n;
    }
    function update() {
      ticking = false;
      if (!pinned) return;
      var g = geometry(), u = uOf(g), v = u + 0.5, idx = Math.min(6, Math.floor(v)), p;
      if (idx === 0) p = (v - 0.5) / 0.5; else if (idx === 6) p = (v - 6) / 0.5; else p = v - idx;
      p = Math.max(0, Math.min(1, p));
      if (Math.abs(p - lastP) > 0.0004) { stage.style.setProperty('--p', p.toFixed(4)); lastP = p; }
      var gg = u / 6; if (Math.abs(gg - lastG) > 0.001) { grid.style.setProperty('--g', gg.toFixed(4)); lastG = gg; }
      if (idx !== cur) {
        cur = idx; stage.setAttribute('data-scene', String(idx + 1)); if (count) count.textContent = String(idx + 1);
        scenes.forEach(function (s, i) { s.classList.toggle('is-on', i === idx); });
        steps.forEach(function (s, i) { s.classList.toggle('is-on', i === idx); });
        titles.forEach(function (n, i) { n.classList.toggle('is-on', i === idx); });
        dots.forEach(function (li, i) { li.classList.toggle('is-on', i === idx); li.classList.toggle('is-done', i < idx); });
        links.forEach(function (a, i) { if (i === idx) a.setAttribute('aria-current', 'step'); else a.removeAttribute('aria-current'); });
      }
    }
    function request() { if (!ticking && pinned && inView) { ticking = true; requestAnimationFrame(update); } }
    window.addEventListener('scroll', request, { passive: true });
    window.addEventListener('resize', function () { request(); }, { passive: true });
    if ('IntersectionObserver' in window) new IntersectionObserver(function (es) { inView = es[0].isIntersecting; if (inView) request(); }, { rootMargin: '200px 0px' }).observe(sec);
    else inView = true;

    links.forEach(function (a, i) {
      a.addEventListener('click', function (e) {
        if (!pinned) return;
        e.preventDefault();
        var g = geometry(), c = g.centers, target = c[i] + (i < 6 ? 0.4 * (c[i + 1] - c[i]) : 0) - g.focus;
        window.scrollBy({ top: target, behavior: reduceMQ.matches ? 'auto' : 'smooth' });
      });
    });
    reduceMQ.addEventListener && reduceMQ.addEventListener('change', sync);
    sync();
    return { update: function () { lastP = -1; update(); } };
  })();
  function labelRail() { $$('.rail a').forEach(function (a, i) { a.setAttribute('aria-label', t('step') + ' ' + (i + 1)); }); }

  /* ---------- init ---------- */
  if (lang === 'he') applyLang('he', false); else { setThemeLabel(); labelRail(); labelPause(); d.title = t('doc_title'); var sh = $('#demo-sheet'); if (sh) { sh.lang = 'en'; sh.dir = 'ltr'; } }
  syncTracks();
  if (storyApi) storyApi.update();
  if (demoApi) demoApi.restart();
})();
