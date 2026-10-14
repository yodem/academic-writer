/* Academic Writer site: theme, language, copy, hero demo, scrollytelling, reveals. Vanilla, no deps. */
(function () {
  'use strict';
  var d = document, root = d.documentElement;
  root.classList.add('js'); /* only now: CSS that hides content keys off this, so a failed load never hides it */
  function safe(fn) { try { return fn(); } catch (e) { if (window.console) console.warn('section failed', e); return null; } }
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
    doc_title: 'Academic Writer — cited academic articles with Claude'
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
    setThemeLabel(); labelPause();
    if (persist) store.set('aw-lang', lang);
    if (flowApi) flowApi.restart();
    if (howApi) howApi.update();
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

  /* ---------- hero flow visualization: a real /write run, almost no text ---------- */
  var flowApi = safe(function () {
    var host = $('#flowviz'), stage = $('#flow-stage'), btn = $('#flow-pause'); if (!host || !stage) return null;
    var LOOP = 18, ICON = {
      you: '<circle cx="12" cy="8" r="3.6"/><path d="M5 20c0-4.2 3-6.2 7-6.2s7 2 7 6.2"/>',
      sources: '<path d="M4 5h4v15H4zM9.5 5h4v15h-4z"/><path d="m15 7 3.7-.9 3 12.8-3.7.9z"/>',
      evidence: '<rect x="3" y="4" width="9" height="7" rx="1.5"/><rect x="12" y="13" width="9" height="7" rx="1.5"/><path d="M7.5 11v3h4.5M16.5 13V8h-4.5"/>',
      outline: '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4.6" cy="6" r="1"/><circle cx="4.6" cy="12" r="1"/><circle cx="4.6" cy="18" r="1"/>',
      draft: '<path d="m4 20 1-4L16.5 4.5a2.1 2.1 0 0 1 3 3L8 19z"/><path d="m14 7 3 3"/>',
      auditor: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/><path d="m8.5 12 2.5 2.5 4.5-5"/>',
      word: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
      revise: '<path d="M4 12a8 8 0 1 0 2.5-5.8"/><path d="M4 4v4.5h4.5"/>',
      voice: '<path d="M4 12v0M8 8v8M12 5v14M16 9v6M20 11v2"/>'
    };
    var ORDER = ['you', 'sources', 'evidence', 'outline', 'draft', 'auditor', 'word', 'revise'];
    var LEGS = [[0.3, 1.1, 'you', 'sources'], [1.3, 2.1, 'sources', 'evidence'], [2.3, 3.1, 'evidence', 'outline'], [3.3, 4.9, 'outline', 'draft'], [5.6, 6.5, 'draft', 'auditor'],
      [7.7, 8.6, 'auditor', 'draft'], [9.3, 10.2, 'draft', 'auditor'], [11.4, 12.3, 'auditor', 'word'], [13.1, 13.7, 'word', 'revise']];
    var ARRIVE = { you: 0.3, sources: 1.1, evidence: 2.1, outline: 3.1, draft: 4.9, auditor: 6.5, word: 12.3, revise: 13.7, voice: 15.3 };
    var g, D, mainEl, retEl, els = {}, T = 0, last = 0, raf = 0, paused = false, visible = false, mql = window.matchMedia('(max-width: 899px)');
    var NS = 'http://www.w3.org/2000/svg', cache = {};
    function ease(u) { u = Math.max(0, Math.min(1, u)); return 1 - Math.pow(1 - u, 4); }
    function clamp(v) { return Math.max(0, Math.min(1, v)); }
    function labels() { return $$('.flow__sr li', host).map(function (li) { return li.textContent; }); }

    function layout(mobile) {
      return mobile
        ? { W: 360, H: 352, xs: [48, 136, 224, 312], y1: 52, y2: 172, yc: 112, yr: 318, r: 25, fs: 12, vx: 180, vy: 248, vr: 17, lab: 15, k: 0.8 }
        : { W: 600, H: 470, xs: [70, 215, 360, 505], y1: 90, y2: 250, yc: 170, yr: 430, r: 32, fs: 14, vx: 287, vy: 358, vr: 22, lab: 20, k: 1 };
    }
    function build() {
      var rtl = root.dir === 'rtl', G = g = layout(mql.matches), L = labels();
      function X(x) { return rtl ? G.W - x : x; }
      var xs = G.xs, step = xs[1] - xs[0], w = xs[3] - xs[0], a = G.yc - G.y1, b = G.y2 - G.yc, A = G.yr - G.y2;
      var off = G.r + 14, ex = xs[3] + off, leftX = xs[0] - G.r - 16, B = ex - leftX;
      D = { you: 0, sources: step, evidence: 2 * step, outline: w, draft: 2 * (ex - xs[0]) + a + b };
      D.auditor = D.draft + step; D.word = D.draft + 2 * step; D.revise = D.draft + 3 * step;
      var mainD = 'M' + X(xs[0]) + ' ' + G.y1 + 'H' + X(ex) + 'V' + G.yc + 'H' + X(xs[0]) + 'V' + G.y2 + 'H' + X(xs[3]);
      var retD = 'M' + X(xs[3]) + ' ' + G.y2 + 'H' + X(ex) + 'V' + G.yr + 'H' + X(leftX) + 'V' + G.y2 + 'H' + X(xs[0] - G.r);
      g.R = off + 2 * A + B + (xs[0] - G.r - leftX); g.Vd = off + A + (ex - G.vx);
      var pos = { you: [xs[0], G.y1], sources: [xs[1], G.y1], evidence: [xs[2], G.y1], outline: [xs[3], G.y1], draft: [xs[0], G.y2], auditor: [xs[1], G.y2], word: [xs[2], G.y2], revise: [xs[3], G.y2], voice: [G.vx, G.vy] };
      var kk = G.r / 22, h = '';
      function node(name, i, rr, extra) {
        var c = pos[name], k = rr / 22, icon = '<g class="fn__i" transform="translate(' + (-12 * k) + ',' + (-12 * k) + ') scale(' + k + ')">' + ICON[name] + '</g>';
        var lab = '<text class="fn__t" y="' + (rr + G.lab - (name === 'voice' ? 4 : 0)) + '">' + L[i] + '</text>';
        return '<g class="fn' + (name === 'voice' ? ' fn--voice' : '') + '" data-n="' + name + '" transform="translate(' + X(c[0]) + ',' + c[1] + ')"><circle class="fn__c" r="' + rr + '"/><circle class="fn__hl" r="' + (rr + 4) + '"/>' + (extra || '') + icon + lab + (name === 'draft' ? '<text class="fn__s" y="' + (rr + G.lab * 2 - 3) + '">' + L[9] + '</text>' : '') + '</g>';
      }
      var ring = '<circle class="fn__bad" r="' + (G.r + 4) + '"/><circle class="fn__ok" r="' + (G.r + 4) + '"/>';
      var bx = G.r * 0.74, badge = '<g transform="translate(' + (rtl ? -bx : bx) + ',' + (-bx) + ')"><g class="fn__b0"><circle r="9"/><path d="m-4 0 3 3 5-6"/></g><g class="fn__b1"><circle r="9"/><path d="m-3.5-3.5 7 7m0-7-7 7"/></g></g>';
      var vx = X(G.vx), vyEnd = G.vy + G.vr;
      var cardY = -(G.r + 22 * G.k), s = G.k;
      h += '<defs><radialGradient id="flhalo"><stop offset="0" stop-color="oklch(0.9 0.08 270)" stop-opacity="0.55"/><stop offset="1" stop-color="oklch(0.9 0.08 270)" stop-opacity="0"/></radialGradient></defs>';
      h += '<path class="fl-base" d="' + mainD + '"/><path class="fl-base fl-ret" d="' + retD + '"/>';
      var vTarget = [X(xs[0] + 20 * G.k + 0), G.y2 + 20 * G.k];
      h += '<path class="fl-voice" d="M' + (rtl ? vx + G.vr : vx - G.vr) + ' ' + (G.vy - 6) + 'L' + vTarget[0] + ' ' + vTarget[1] + '"/>';
      h += '<g class="fx"><path class="fl-trail" id="fl-tm" d="' + mainD + '"/><path class="fl-trail" id="fl-tr" d="' + retD + '"/></g>';
      ORDER.forEach(function (n, i) { h += node(n, i, G.r, n === 'auditor' ? ring + badge : ''); });
      h += node('voice', 8, G.vr);
      h += '<g class="fx">';
      h += '<g class="pk" id="fl-pk"><circle class="pk__halo" r="' + (18 * G.k) + '" fill="url(#flhalo)"/><circle class="pk__dot" r="' + (5 * G.k) + '"/>';
      h += '<g id="fl-card"><line class="pk__stem" x1="0" y1="0" x2="0" y2="' + (cardY + 16 * s) + '"/><g transform="translate(0,' + cardY + ') scale(' + s + ')"><rect class="pk__paper" x="-23" y="-16" width="46" height="32" rx="4"/><rect class="pk__ln" x="-16" y="-8" width="32" height="3" rx="1.5"/><rect class="pk__ln" id="fl-l2" x="-16" y="-1" width="26" height="3" rx="1.5"/><rect class="pk__ln" x="-16" y="6" width="20" height="3" rx="1.5"/>';
      h += '<g class="pk__fn" transform="translate(' + (rtl ? -23 : 23) + ',-16)"><circle r="8"/><path class="pk__v" d="m-3.5 0 2.5 2.5 4.5-5"/><path class="pk__x" d="m-3-3 6 6m0-6-6 6"/></g></g></g></g>';
      h += '<g id="fl-bb"><g transform="scale(' + s + ')"><path class="bb__shape" d="M-17-20h34a6 6 0 0 1 6 6v10a6 6 0 0 1-6 6h-14l-8 7v-7h-12a6 6 0 0 1-6-6v-10a6 6 0 0 1 6-6z" transform="translate(0,2)"/><circle class="bb__dot" cx="-8" cy="-9" r="2"/><circle class="bb__dot" cx="0" cy="-9" r="2"/><circle class="bb__dot" cx="8" cy="-9" r="2"/></g></g>';
      h += '<circle class="vd" id="fl-vd" r="' + (4 * G.k) + '" cx="' + vx + '" cy="' + G.yr + '"/></g>';
      stage.innerHTML = '<svg viewBox="0 0 ' + G.W + ' ' + G.H + '" style="--fs:' + G.fs + 'px" preserveAspectRatio="xMidYMid meet" focusable="false">' + h + '</svg>';
      var svg = stage.firstChild; mainEl = $('.fl-base', svg); retEl = $('.fl-ret', svg);
      els = { svg: svg, tm: $('#fl-tm', svg), tr: $('#fl-tr', svg), pk: $('#fl-pk', svg), card: $('#fl-card', svg), l2: $('#fl-l2', svg), bb: $('#fl-bb', svg), vd: $('#fl-vd', svg), voice: $('.fl-voice', svg), fx: $$('.fx', svg), nodes: {}, vx: vx, vy: vyEnd };
      $$('.fn', svg).forEach(function (n) { els.nodes[n.getAttribute('data-n')] = n; });
      els.mainLen = mainEl.getTotalLength(); els.retLen = retEl.getTotalLength();
      cache = {};
    }

    function dist(t) {
      var d = D.you;
      for (var i = 0; i < LEGS.length; i++) {
        var l = LEGS[i], f = D[l[2]], to = D[l[3]];
        if (t >= l[1]) d = to; else if (t >= l[0]) { d = f + (to - f) * ease((t - l[0]) / (l[1] - l[0])); break; } else break;
      }
      return d;
    }
    function maxDist(t) {
      var m = 0;
      for (var i = 0; i < LEGS.length; i++) {
        var l = LEGS[i]; if (t < l[0]) break;
        var f = D[l[2]], to = D[l[3]]; m = Math.max(m, f, t >= l[1] ? to : f + (to - f) * ease((t - l[0]) / (l[1] - l[0])));
      }
      return m;
    }
    function retDist(t) {
      if (t < 13.7) return 0;
      if (t < 15.0) return g.Vd * ease((t - 13.7) / 1.3);
      if (t < 15.7) return g.Vd;
      return g.Vd + (g.R - g.Vd) * ease((t - 15.7) / 1.3);
    }
    function setCls(n, c) { if (cache[n.getAttribute('data-n') || n.id] !== c) { cache[n.getAttribute('data-n') || n.id] = c; n.setAttribute('class', c); } }
    function render(t, still) {
      var G = g, fade = still ? 1 : t < 0.3 ? t / 0.3 : t > 17.3 ? clamp(1 - (t - 17.3) / 0.5) : 1;
      var d = dist(t), mp, onMain = t < 13.1 || still;
      if (still) { t = 12.8; d = D.word; }
      var bad = t >= 6.9 && t < 9.0, ok = t >= 10.6, cardK = still ? 1 : clamp((t - 4.9) / 0.5);
      els.fx.forEach(function (f) { f.style.opacity = String(fade); });
      /* trails */
      var m = still ? D.word : maxDist(t), bm = t >= 13.1 ? Math.max(m, D.word + (D.revise - D.word) * ease((t - 13.1) / 0.6)) : m;
      els.tm.style.strokeDasharray = (still ? D.word : bm) + ' 99999'; els.tr.style.strokeDasharray = (still ? 0 : retDist(t)) + ' 99999';
      /* packet */
      var pt = mainEl.getPointAtLength(Math.min(d, els.mainLen)), dotOn = still ? 0 : (t < 13.1 ? 1 : 0);
      els.pk.setAttribute('transform', 'translate(' + pt.x.toFixed(1) + ',' + pt.y.toFixed(1) + ')');
      var parked = t >= 13.1 || still;
      els.pk.querySelector('.pk__dot').style.opacity = String(dotOn);
      els.pk.querySelector('.pk__halo').style.opacity = String(dotOn);
      var cardOn = cardK > 0 && t < 17.4;
      els.card.style.opacity = String(cardOn ? cardK : 0);
      els.card.style.transform = 'scale(' + (0.7 + 0.3 * cardK) + ')'; els.card.style.transformBox = 'fill-box'; els.card.style.transformOrigin = '50% 100%';
      if (parked) { var wp = mainEl.getPointAtLength(D.word); els.pk.setAttribute('transform', 'translate(' + wp.x.toFixed(1) + ',' + wp.y.toFixed(1) + ')'); }
      var rw = t >= 8.6 && t < 9.3; els.l2.style.opacity = rw ? String(0.35 + 0.35 * Math.sin((t - 8.6) * 12)) : '1';
      var pkc = 'pk' + (bad ? ' pk--bad' : ok ? ' pk--ok' : ''); if (cache.pk !== pkc) { cache.pk = pkc; els.pk.setAttribute('class', pkc); }
      /* comment bubble, then the dot into the voice store */
      var bOn = still ? 0 : (t >= 12.6 && t < 17.2), bp;
      if (bOn) {
        var bs = ease((t - 12.6) / 0.3);
        if (t < 13.1) bp = mainEl.getPointAtLength(D.word);
        else if (t < 13.7) bp = mainEl.getPointAtLength(D.word + (D.revise - D.word) * ease((t - 13.1) / 0.6));
        else bp = retEl.getPointAtLength(Math.min(retDist(t), els.retLen));
        var o = t < 13.1 ? 1 : t < 13.7 ? 1 - ease((t - 13.1) / 0.6) : 0, dir = root.dir === 'rtl' ? -1 : 1;
        els.bb.setAttribute('transform', 'translate(' + (bp.x + dir * (G.r + 12) * o).toFixed(1) + ',' + (bp.y - G.r * 0.7 * o).toFixed(1) + ') scale(' + (t < 13.1 ? bs : 1) + ')');
        els.bb.style.opacity = String(t > 16.7 ? clamp(1 - (t - 16.7) / 0.5) : 1);
      } else els.bb.style.opacity = '0';
      var vdu = clamp((t - 15.0) / 0.7);
      els.vd.style.opacity = (!still && t >= 15.0 && t < 16.4) ? '1' : '0';
      els.vd.setAttribute('cy', (G.yr + (els.vy - G.yr) * ease(vdu)).toFixed(1));
      /* nodes */
      var cur = {}, k;
      if (!still) {
        if (t >= 0.3 && t < 1.6) cur.you = 1;
        LEGS.forEach(function (l, i) { var nx = LEGS[i + 1], end = nx ? nx[0] + 0.5 : 14.6; if (t >= l[1] && t < end) cur[l[3]] = 1; });
        if (t >= 15.0 && t < 16.4) cur.voice = 1;
        if (t >= 17.0 && t < 17.6) cur.draft = 1;
      }
      Object.keys(els.nodes).forEach(function (n) {
        var c = 'fn' + (n === 'voice' ? ' fn--voice' : '');
        if (still || t >= ARRIVE[n]) c += ' is-done'; if (cur[n] && !still) c += ' is-cur';
        if (n === 'auditor') { if (bad && !still) c += ' is-bad'; else if (ok || still) c += ' is-ok'; }
        setCls(els.nodes[n], c);
      });
      var vl = still || t >= 15.3 ? 'fl-voice is-lit' : 'fl-voice'; if (cache.vl !== vl) { cache.vl = vl; els.voice.setAttribute('class', vl); }
    }

    function tick(ts) {
      raf = 0;
      var dt = Math.min(0.1, (ts - last) / 1000); last = ts;
      T = (T + dt) % LOOP; render(T);
      if (visible && !paused) raf = requestAnimationFrame(tick);
    }
    function go() { if (reduceMQ.matches || paused || !visible || raf) return; last = performance.now(); raf = requestAnimationFrame(tick); }
    function stop() { if (raf) cancelAnimationFrame(raf); raf = 0; }
    function refresh() { build(); if (reduceMQ.matches) render(0, true); else { render(T); go(); } }
    if (btn) btn.addEventListener('click', function () {
      paused = !paused; btn.setAttribute('aria-pressed', String(paused)); labelPause();
      if (paused) stop(); else go();
    });
    if ('IntersectionObserver' in window) new IntersectionObserver(function (es) { visible = es[0].isIntersecting; if (visible) go(); else stop(); }, { threshold: 0.15 }).observe(host);
    else { visible = true; }
    reduceMQ.addEventListener && reduceMQ.addEventListener('change', function () { stop(); refresh(); });
    mql.addEventListener && mql.addEventListener('change', refresh);
    refresh();
    return { restart: refresh };
  });
  function labelPause() { var b = $('#flow-pause'); if (!b) return; $('.pause__t', b).textContent = t(b.getAttribute('aria-pressed') === 'true' ? 'play' : 'pause'); }


  /* ---------- film fallback ---------- */
  (function () {
    var v = $('#film-video'), sec = $('#film'); if (!v) return;
    var fail = function () { sec.classList.add('film--fail'); };
    v.addEventListener('error', fail);
    var srcs = $$('source', v); if (srcs.length) srcs[srcs.length - 1].addEventListener('error', fail);
  })();

  /* ---------- gate diagram: reveal observer handles .in ---------- */

  /* ---------- how it works: an auto-playing Cowork-style window (about 15 s, then loops) ---------- */
  var howApi = safe(function () {
    var sec = $('#hw'); if (!sec) return null;
    var playB = $('#hw-play', sec), phBtns = $$('.hw__phase', sec), PH = [0, 3, 10, 15], END = 15, LOOP = 17;
    var T = 0, running = true, inView = !('IntersectionObserver' in window), raf = 0, last = 0;
    var typed = [], states = [], counts = [], fills = [];
    function num(s) { return parseFloat(s); }
    $$('[data-type]', sec).forEach(function (el) {
      var p = el.getAttribute('data-type').split(','), code = $('code', el);
      typed.push({ el: el, code: code, full: code.textContent, a: num(p[0]), b: num(p[1]), n: -1, s: '' });
    });
    $$('[data-st],[data-ss]', sec).forEach(function (el) {
      var raw = el.getAttribute('data-st') || el.getAttribute('data-ss');
      var steps = raw.split(',').map(function (x) { var q = x.split(':'); return { t: num(q[0]), s: q[1] }; });
      states.push({ el: el, steps: steps, cur: null });
    });
    $$('[data-count]', sec).forEach(function (el) { var p = el.getAttribute('data-count').split(','); counts.push({ el: el, a: num(p[0]), b: num(p[1]), max: num(p[2]), v: -1 }); });
    $$('[data-fill]', sec).forEach(function (el) { var p = el.getAttribute('data-fill').split(','); fills.push({ el: el, a: num(p[0]), b: num(p[1]), v: -1 }); });
    function clamp01(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
    function render(now) {
      typed.forEach(function (x) {
        var n = Math.floor(x.full.length * clamp01((now - x.a) / (x.b - x.a)) + 0.0001);
        if (n !== x.n) { x.n = n; x.code.textContent = x.full.slice(0, n); }
        var s = now < x.a ? '' : now < x.b + 0.35 ? 'typing' : 'done';
        if (s !== x.s) { x.s = s; if (s) x.el.setAttribute('data-state', s); else x.el.removeAttribute('data-state'); }
      });
      states.forEach(function (x) {
        var s = '';
        for (var i = 0; i < x.steps.length; i++) if (now >= x.steps[i].t) s = x.steps[i].s;
        if (s !== x.cur) { x.cur = s; if (s) x.el.setAttribute('data-state', s); else x.el.removeAttribute('data-state'); }
      });
      counts.forEach(function (x) { var v = Math.round(x.max * clamp01((now - x.a) / (x.b - x.a))); if (v !== x.v) { x.v = v; x.el.textContent = v; } });
      fills.forEach(function (x) { var v = Math.round(clamp01((now - x.a) / (x.b - x.a)) * 200) / 200; if (v !== x.v) { x.v = v; x.el.style.setProperty('--f', v); } });
      phBtns.forEach(function (b, i) {
        b.lastElementChild.style.setProperty('--f', clamp01((now - PH[i]) / (PH[i + 1] - PH[i])));
        b.classList.toggle('is-on', now >= PH[i] && now < PH[i + 1]);
        b.classList.toggle('is-done', now >= PH[i + 1]);
      });
    }
    function labelPlay() {
      if (!playB) return;
      var paused = !running; playB.setAttribute('aria-pressed', String(paused));
      $('.hw__playt', playB).textContent = t(paused ? 'play' : 'pause');
    }
    function active() { return running && inView && !d.hidden && !reduceMQ.matches; }
    function frame(ts) {
      raf = 0; if (!active()) return;
      T += Math.min(0.1, (ts - last) / 1000); last = ts;
      if (T >= LOOP) T = 0;
      render(T); raf = requestAnimationFrame(frame);
    }
    function go() { sec.classList.toggle('is-paused', !running || !inView); if (active() && !raf) { last = performance.now(); raf = requestAnimationFrame(frame); } }
    function setStatic() {
      var st = reduceMQ.matches; sec.classList.toggle('is-static', st);
      if (st) { T = END; render(END); } else if (T >= END) { T = 0; render(0); }
      go();
    }
    sec.classList.add('is-live');
    if (playB) playB.addEventListener('click', function () { running = !running; labelPlay(); go(); });
    phBtns.forEach(function (b, i) { b.addEventListener('click', function () { if (reduceMQ.matches) return; T = PH[i]; render(T); go(); }); });
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (es) {
        var e = es[es.length - 1];
        inView = e.isIntersecting && (e.intersectionRatio >= 0.5 || e.intersectionRect.height >= window.innerHeight * 0.5);
        go();
      }, { threshold: [0, 0.25, 0.5, 0.75, 1] }).observe($('.hw__win', sec));
    }
    d.addEventListener('visibilitychange', go);
    reduceMQ.addEventListener && reduceMQ.addEventListener('change', setStatic);
    render(0); labelPlay(); setStatic();
    return { update: labelPlay };
  });

  /* ---------- top bar over the hero: transparent on the dark hero, solid after ---------- */
  safe(function () {
    var hero = $('#top'), bar = $('#bar'); if (!hero || !bar || !('IntersectionObserver' in window)) return;
    var h = bar.offsetHeight || 56;
    new IntersectionObserver(function (es) { root.classList.toggle('over-hero', es[0].isIntersecting); },
      { rootMargin: '-' + h + 'px 0px 0px 0px', threshold: 0 }).observe(hero);
  });

  /* ---------- init ---------- */
  if (lang === 'he') applyLang('he', false); else { setThemeLabel(); labelPause(); d.title = t('doc_title'); }
  if (howApi) howApi.update();
  if (flowApi) flowApi.restart();
})();

/* round 4: FAQ is an exclusive accordion; name="faq" does it natively, this covers browsers without it */
(function () {
  var all = document.querySelectorAll('.faq__list details');
  Array.prototype.forEach.call(all, function (el) {
    el.addEventListener('toggle', function () {
      if (!el.open) return;
      Array.prototype.forEach.call(all, function (o) { if (o !== el && o.open) o.open = false; });
    });
  });
})();
