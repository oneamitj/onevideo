/*! stage.js - onevideo runtime. MIT License.
 *
 * Every frame is a pure function of time. The renderer calls
 * window.__stage.seek(t) for each frame and screenshots the page, so nothing
 * here may depend on wall-clock time, Math.random() or event order.
 *
 * Authoring API (see references/runtime-api.md for the full list):
 *   Stage.config({...})                 optional overrides
 *   Stage.scene('id', s => { ... })     tweens relative to the scene start
 *   Stage.global(s => { ... })          tweens in absolute time
 *   Stage.onFrame(t => { ... })         canvas / WebGL drawing
 *   Stage.start()                       call once, last
 */
(function () {
  'use strict';

  // ------------------------------------------------------------------ utils
  const clamp = (v, a, b) => (v < a ? a : v > b ? b : v);
  const lerp = (a, b, p) => a + (b - a) * p;
  const isNum = (v) => typeof v === 'number' && isFinite(v);
  const toArr = (v) => (v == null ? [] : Array.isArray(v) ? v : (v instanceof NodeList || v instanceof HTMLCollection) ? Array.from(v) : [v]);
  const kebab = (s) => s.replace(/[A-Z]/g, (m) => '-' + m.toLowerCase());
  const params = new URLSearchParams(location.search);

  function mulberry32(seed) {
    let a = (seed >>> 0) || 0x9e3779b9;
    return function () {
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function hash1(i, seed) {
    let h = Math.imul((i | 0) ^ (seed | 0) ^ 0x27d4eb2d, 0x165667b1);
    h = Math.imul(h ^ (h >>> 15), 0x85ebca6b);
    h ^= h >>> 13;
    return ((h >>> 0) % 100000) / 100000;
  }
  // smooth 1D value noise in [-1, 1]
  function noise(x, seed = 1) {
    const i = Math.floor(x), f = x - i;
    const u = f * f * (3 - 2 * f);
    return lerp(hash1(i, seed), hash1(i + 1, seed), u) * 2 - 1;
  }

  // ----------------------------------------------------------------- easing
  const P = Math.pow, S = Math.sin, C = Math.cos, PI = Math.PI, SQ = Math.sqrt;
  const c1 = 1.70158, c2 = c1 * 1.525, c3 = c1 + 1, c4 = (2 * PI) / 3, c5 = (2 * PI) / 4.5;
  function bounceOut(x) {
    const n1 = 7.5625, d1 = 2.75;
    if (x < 1 / d1) return n1 * x * x;
    if (x < 2 / d1) return n1 * (x -= 1.5 / d1) * x + 0.75;
    if (x < 2.5 / d1) return n1 * (x -= 2.25 / d1) * x + 0.9375;
    return n1 * (x -= 2.625 / d1) * x + 0.984375;
  }
  function bezier(x1, y1, x2, y2) {
    const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
    const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
    const sx = (t) => ((ax * t + bx) * t + cx) * t;
    const sy = (t) => ((ay * t + by) * t + cy) * t;
    const dx = (t) => (3 * ax * t + 2 * bx) * t + cx;
    return function (x) {
      if (x <= 0) return 0;
      if (x >= 1) return 1;
      let t = x;
      for (let i = 0; i < 8; i++) {
        const e = sx(t) - x;
        if (Math.abs(e) < 1e-6) return sy(t);
        const d = dx(t);
        if (Math.abs(d) < 1e-6) break;
        t -= e / d;
      }
      let lo = 0, hi = 1;
      t = x;
      for (let i = 0; i < 30; i++) {
        const v = sx(t);
        if (Math.abs(v - x) < 1e-6) break;
        if (x > v) lo = t; else hi = t;
        t = (lo + hi) / 2;
      }
      return sy(t);
    };
  }
  const EASE = {
    linear: (t) => t,
    inquad: (t) => t * t, outquad: (t) => 1 - (1 - t) * (1 - t), inoutquad: (t) => (t < 0.5 ? 2 * t * t : 1 - P(-2 * t + 2, 2) / 2),
    incubic: (t) => t * t * t, outcubic: (t) => 1 - P(1 - t, 3), inoutcubic: (t) => (t < 0.5 ? 4 * t * t * t : 1 - P(-2 * t + 2, 3) / 2),
    inquart: (t) => t * t * t * t, outquart: (t) => 1 - P(1 - t, 4), inoutquart: (t) => (t < 0.5 ? 8 * t * t * t * t : 1 - P(-2 * t + 2, 4) / 2),
    inquint: (t) => t * t * t * t * t, outquint: (t) => 1 - P(1 - t, 5), inoutquint: (t) => (t < 0.5 ? 16 * P(t, 5) : 1 - P(-2 * t + 2, 5) / 2),
    insine: (t) => 1 - C((t * PI) / 2), outsine: (t) => S((t * PI) / 2), inoutsine: (t) => -(C(PI * t) - 1) / 2,
    inexpo: (t) => (t === 0 ? 0 : P(2, 10 * t - 10)), outexpo: (t) => (t === 1 ? 1 : 1 - P(2, -10 * t)),
    inoutexpo: (t) => (t === 0 ? 0 : t === 1 ? 1 : t < 0.5 ? P(2, 20 * t - 10) / 2 : (2 - P(2, -20 * t + 10)) / 2),
    incirc: (t) => 1 - SQ(1 - t * t), outcirc: (t) => SQ(1 - P(t - 1, 2)),
    inoutcirc: (t) => (t < 0.5 ? (1 - SQ(1 - P(2 * t, 2))) / 2 : (SQ(1 - P(-2 * t + 2, 2)) + 1) / 2),
    inback: (t) => c3 * t * t * t - c1 * t * t, outback: (t) => 1 + c3 * P(t - 1, 3) + c1 * P(t - 1, 2),
    inoutback: (t) => (t < 0.5 ? (P(2 * t, 2) * ((c2 + 1) * 2 * t - c2)) / 2 : (P(2 * t - 2, 2) * ((c2 + 1) * (t * 2 - 2) + c2) + 2) / 2),
    outelastic: (t) => (t === 0 ? 0 : t === 1 ? 1 : P(2, -10 * t) * S((t * 10 - 0.75) * c4) + 1),
    inoutelastic: (t) => (t === 0 ? 0 : t === 1 ? 1 : t < 0.5 ? -(P(2, 20 * t - 10) * S((20 * t - 11.125) * c5)) / 2 : (P(2, -20 * t + 10) * S((20 * t - 11.125) * c5)) / 2 + 1),
    outbounce: bounceOut, inbounce: (t) => 1 - bounceOut(1 - t),
    // design-system curves
    smooth: bezier(0.4, 0, 0.2, 1),
    snappy: bezier(0.2, 0.9, 0.1, 1),
    swift: bezier(0.55, 0, 0.1, 1),
    gentle: bezier(0.25, 0.1, 0.25, 1),
    anticipate: bezier(0.38, -0.4, 0.88, 0.65),
  };
  EASE.in = EASE.incubic; EASE.out = EASE.outcubic; EASE.inout = EASE.inoutcubic;
  // a lightly underdamped spring, normalised to settle at t = 1
  EASE.spring = (t) => (t >= 1 ? 1 : 1 - Math.exp(-6.5 * t) * C(9.5 * t * (1 - 0.15 * t)));
  function getEase(e) {
    if (typeof e === 'function') return e;
    if (Array.isArray(e) && e.length === 4) return bezier(e[0], e[1], e[2], e[3]);
    if (typeof e === 'string') {
      const m = e.match(/^cubic-bezier\(([^)]+)\)$/);
      if (m) { const v = m[1].split(',').map(Number); return bezier(v[0], v[1], v[2], v[3]); }
      const k = e.toLowerCase().replace(/[-_\s.]/g, '').replace(/^ease/, '');
      if (EASE[k]) return EASE[k];
      if (EASE['out' + k]) return EASE['out' + k];
      warn('unknown ease "' + e + '", using outCubic');
    }
    return EASE.outcubic;
  }

  // ------------------------------------------------------------------ state
  const RTL = new Set(['ar', 'he', 'iw', 'fa', 'ur', 'yi', 'ps', 'sd', 'ug', 'dv', 'ckb', 'syr', 'nqo', 'ks']);
  const FORMATS = { landscape: [1920, 1080], vertical: [1080, 1920], square: [1080, 1080], portrait: [1080, 1350], wide: [2560, 1080] };
  const st = {
    cfg: { fps: 30, format: 'landscape', lang: null, safe: null, background: null, captions: null, audio: null },
    W: 1920, H: 1080, U: 10.8, fps: 30, duration: 0, lang: 'en', dir: 'ltr',
    render: params.get('render') === '1',
    stage: null, scenes: [], sceneById: {}, builders: [], globalBuilders: [], frameFns: [],
    tweens: [], tracks: [], els: new Map(), specials: [], cursors: [], cls: [], cues: [],
    ready: false, errors: [], warnings: [], strings: null, lastT: -1, captions: [],
    playing: false, t: 0,
  };
  function warn(msg) { st.warnings.push(String(msg)); try { console.warn('[stage] ' + msg); } catch (e) {} }
  function fail(msg) { st.errors.push(String(msg)); try { console.error('[stage] ' + msg); } catch (e) {} }
  window.addEventListener('error', (e) => fail((e.message || 'error') + (e.filename ? ' @ ' + e.filename.split('/').pop() + ':' + e.lineno : '')));
  window.addEventListener('unhandledrejection', (e) => fail('unhandled rejection: ' + (e.reason && e.reason.message || e.reason)));

  // ----------------------------------------------------------------- values
  const IDENT = { opacity: 1, x: 0, y: 0, z: 0, scale: 1, scaleX: 1, scaleY: 1, rotate: 0, rotateX: 0, rotateY: 0, skewX: 0, skewY: 0,
    blur: 0, brightness: 1, contrast: 1, saturate: 1, grayscale: 0, hueRotate: 0, draw: 1 };
  const TF = new Set(['x', 'y', 'z', 'scale', 'scaleX', 'scaleY', 'rotate', 'rotateX', 'rotateY', 'skewX', 'skewY']);
  const FL = new Set(['blur', 'brightness', 'contrast', 'saturate', 'grayscale', 'hueRotate']);
  const NUMRE = /-?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?/gi;

  function lenToPx(v, axis) {
    // our own units: u = 1% of min(W,H), sw = 1% stage width, sh = 1% stage height
    if (isNum(v)) return v;
    const m = String(v).trim().match(/^(-?[\d.]+(?:e-?\d+)?)(u|sw|sh|px)?$/i);
    if (!m) return null;
    const n = parseFloat(m[1]);
    switch ((m[2] || 'px').toLowerCase()) {
      case 'u': return n * st.U;
      case 'sw': return (n * st.W) / 100;
      case 'sh': return (n * st.H) / 100;
      default: return n;
    }
  }
  function isColor(v) {
    return typeof v === 'string' && !/^-?[\d.]/.test(v.trim()) && (/^(#|rgb|hsl|hwb|lab|lch|oklab|oklch|color\(|color-mix)/i.test(v.trim()) || (window.CSS && CSS.supports('color', v)));
  }
  const LENRE = /^(-?(?:\d+\.?\d*|\.\d+)(?:e[-+]?\d+)?)([a-z%]*)$/i;
  function parseLen(v) {
    if (isNum(v)) return { n: v, u: '' };
    if (typeof v !== 'string') return null;
    const m = v.trim().match(LENRE);
    return m ? { n: parseFloat(m[1]), u: m[2].toLowerCase() } : null;
  }
  // interpolate any pair of values: numbers, lengths, colours, or strings
  // with the same shape (numbers inside are interpolated, e.g. clip-path)
  function interp(prop, a, b, p) {
    if (p <= 0) return a;
    if (p >= 1 && !(isColor(a) && isColor(b))) return b;
    if (isNum(a) && isNum(b)) return a + (b - a) * p;
    const la = parseLen(a), lb = parseLen(b);
    if (la && lb) {
      const own = (u) => u === '' || u === 'px' || u === 'u' || u === 'sw' || u === 'sh';
      if (la.u === lb.u) return la.u ? +(la.n + (lb.n - la.n) * p).toFixed(4) + la.u : la.n + (lb.n - la.n) * p;
      if (la.n === 0 && la.u === '') return +(lb.n * p).toFixed(4) + lb.u;
      if (lb.n === 0 && lb.u === '') return +(la.n * (1 - p)).toFixed(4) + la.u;
      if (own(la.u) && own(lb.u)) { const pa = lenToPx(a), pb = lenToPx(b); return pa + (pb - pa) * p; }
      return p < 0.5 ? a : b;
    }
    const sa = String(a), sb = String(b);
    if (isColor(sa) && isColor(sb)) {
      if (p >= 1) return sb;
      return 'color-mix(in oklab, ' + sa + ' ' + ((1 - p) * 100).toFixed(3) + '%, ' + sb + ')';
    }
    const ta = sa.replace(NUMRE, '#'), tb = sb.replace(NUMRE, '#');
    if (ta === tb) {
      const na = sa.match(NUMRE) || [], nb = sb.match(NUMRE) || [];
      let i = 0;
      return sb.replace(NUMRE, () => {
        const x = parseFloat(na[i]), y = parseFloat(nb[i]);
        i++;
        return String(+(x + (y - x) * p).toFixed(4));
      });
    }
    return p < 0.5 ? a : b;
  }

  // per-element render state
  function elState(el) {
    let s = st.els.get(el);
    if (!s) {
      s = { el, v: {}, base: {}, touched: new Set() };
      st.els.set(el, s);
    }
    return s;
  }
  function baseValue(el, prop) {
    const s = elState(el);
    if (prop in s.base) return s.base[prop];
    if (prop === 'opacity') {
      // respect authored opacity (e.g. a 0.7 subtitle) as the resting value
      const o = parseFloat(getComputedStyle(el).opacity);
      return (s.base.opacity = isFinite(o) ? o : 1);
    }
    if (prop in IDENT) return IDENT[prop];
    let v;
    if (prop.startsWith('attr:')) v = el.getAttribute(prop.slice(5));
    else if (prop.startsWith('--')) v = getComputedStyle(el).getPropertyValue(prop).trim();
    else v = getComputedStyle(el).getPropertyValue(kebab(prop)).trim();
    if (v != null && v !== '' && !isNaN(+v)) v = +v;
    s.base[prop] = v;
    return v;
  }
  function flush(s) {
    const el = s.el, v = s.v, style = el.style;
    let tf = null, fl = null;
    for (const prop of s.touched) {
      if (TF.has(prop)) { tf = tf || {}; tf[prop] = v[prop]; continue; }
      if (FL.has(prop)) { fl = fl || {}; fl[prop] = v[prop]; continue; }
      const val = v[prop];
      if (prop === 'opacity') style.opacity = val;
      else if (prop === 'draw') applyDraw(el, val);
      else if (prop.startsWith('attr:')) el.setAttribute(prop.slice(5), val);
      else if (prop.startsWith('--')) style.setProperty(prop, isNum(val) ? String(val) : val);
      else style.setProperty(kebab(prop), isNum(val) && !UNITLESS.has(prop) ? val + 'px' : String(val));
    }
    if (tf) {
      const has = (k) => k in tf;
      const x = has('x') ? tf.x : 0, y = has('y') ? tf.y : 0, z = has('z') ? tf.z : 0;
      const px = (q) => (isNum(q) ? q + 'px' : (lenToPx(q) != null ? lenToPx(q) + 'px' : q));
      let t = '';
      if (x !== 0 || y !== 0 || z !== 0) t += 'translate3d(' + px(x) + ',' + px(y) + ',' + px(z) + ') ';
      if (has('rotate') && tf.rotate) t += 'rotate(' + tf.rotate + 'deg) ';
      if (has('rotateY') && tf.rotateY) t += 'rotateY(' + tf.rotateY + 'deg) ';
      if (has('rotateX') && tf.rotateX) t += 'rotateX(' + tf.rotateX + 'deg) ';
      const sc = has('scale') ? tf.scale : 1;
      const sx = sc * (has('scaleX') ? tf.scaleX : 1), sy = sc * (has('scaleY') ? tf.scaleY : 1);
      if (sx !== 1 || sy !== 1) t += 'scale(' + sx + ',' + sy + ') ';
      if ((has('skewX') && tf.skewX) || (has('skewY') && tf.skewY)) t += 'skew(' + (tf.skewX || 0) + 'deg,' + (tf.skewY || 0) + 'deg) ';
      style.transform = t || 'none';
    }
    if (fl) {
      let f = '';
      if (fl.blur) f += 'blur(' + fl.blur + 'px) ';
      if ('brightness' in fl && fl.brightness !== 1) f += 'brightness(' + fl.brightness + ') ';
      if ('contrast' in fl && fl.contrast !== 1) f += 'contrast(' + fl.contrast + ') ';
      if ('saturate' in fl && fl.saturate !== 1) f += 'saturate(' + fl.saturate + ') ';
      if (fl.grayscale) f += 'grayscale(' + fl.grayscale + ') ';
      if (fl.hueRotate) f += 'hue-rotate(' + fl.hueRotate + 'deg) ';
      style.filter = f || 'none';
    }
  }
  const UNITLESS = new Set(['opacity', 'zIndex', 'fontWeight', 'lineHeight', 'flexGrow', 'order', 'fillOpacity', 'strokeOpacity', 'stopOpacity']);
  const drawLen = new WeakMap();
  function applyDraw(el, frac) {
    let L = drawLen.get(el);
    if (L == null) {
      try { L = el.getTotalLength ? el.getTotalLength() : 0; } catch (e) { L = 0; }
      drawLen.set(el, L);
      el.style.strokeDasharray = L + ' ' + L;
    }
    el.style.strokeDashoffset = String(L * (1 - clamp(frac, 0, 1)));
  }

  // ---------------------------------------------------------------- targets
  function resolve(targets, root) {
    if (typeof targets === 'string') {
      const list = Array.from((root || document).querySelectorAll(targets));
      if (!list.length) warn('selector matched nothing: "' + targets + '"' + (root && root.id ? ' in #' + root.id : ''));
      return list;
    }
    return toArr(targets).filter(Boolean);
  }
  function staggerOffsets(n, stagger) {
    if (!stagger) return new Array(n).fill(0);
    const o = isNum(stagger) ? { each: stagger } : stagger;
    const each = o.each != null ? o.each : o.total != null ? o.total / Math.max(1, n - 1) : 0.05;
    const from = o.from || 'start';
    let order = [...Array(n).keys()];
    if (from === 'end') order = order.map((i) => n - 1 - i);
    else if (from === 'center') order = order.map((i) => Math.abs(i - (n - 1) / 2));
    else if (from === 'edges') order = order.map((i) => (n - 1) / 2 - Math.abs(i - (n - 1) / 2));
    else if (from === 'random') {
      const r = mulberry32(o.seed || 7), idx = [...Array(n).keys()];
      for (let i = n - 1; i > 0; i--) { const j = Math.floor(r() * (i + 1)); [idx[i], idx[j]] = [idx[j], idx[i]]; }
      order = new Array(n); idx.forEach((v, k) => (order[v] = k));
    } else if (isNum(from)) order = order.map((i) => Math.abs(i - from));
    return order.map((k) => k * each);
  }

  // ---------------------------------------------------------------- builder
  class Builder {
    constructor(scene) {
      this._scene = scene; // null for global
      this.root = scene ? scene.el : st.stage;
      this.start = scene ? scene.start : 0;
      this.dur = scene ? scene.dur : st.duration;
      this.id = scene ? scene.id : null;
      this.W = st.W; this.H = st.H; this.U = st.U;
      this.lang = st.lang; this.dir = st.dir; this.rtl = st.dir === 'rtl';
      this.bpm = st.bpm;
    }
    // seconds of n beats at the soundtrack tempo (scenes start on beats after timeline.py --snap)
    beat(n) { return st.bpm ? (n * 60) / st.bpm : n * 0.5; }
    q(sel) { return resolve(sel, this.root); }
    q1(sel) { return this.q(sel)[0]; }
    _abs(at) { return this.start + (at || 0); }
    _add(targets, from, to, o) {
      o = o || {};
      const els = resolve(targets, this.root);
      const offs = staggerOffsets(els.length, o.stagger);
      const dur = o.dur != null ? o.dur : 0.6;
      const ease = getEase(o.ease || 'outCubic');
      els.forEach((el, i) => {
        const start = this._abs(o.at) + offs[i];
        const f = typeof from === 'function' ? from(i, el) : from;
        const t = typeof to === 'function' ? to(i, el) : to;
        const keys = new Set([...Object.keys(f || {}), ...Object.keys(t || {})]);
        for (let k of keys) {
          if (k === 'attr' || k === 'css') {
            const fa = (f && f[k]) || {}, ta = (t && t[k]) || {};
            for (const ak of new Set([...Object.keys(fa), ...Object.keys(ta)])) {
              const pk = k === 'attr' ? 'attr:' + ak : ak;
              pushTween(el, pk, ak in fa ? val(fa[ak], i, el) : undefined, ak in ta ? val(ta[ak], i, el) : undefined, start, dur, ease, this.id);
            }
            continue;
          }
          pushTween(el, k, f && k in f ? val(f[k], i, el) : undefined, t && k in t ? val(t[k], i, el) : undefined, start, dur, ease, this.id);
        }
        if (o.sfx && (!o.sfxEvery || i % o.sfxEvery === 0)) addCue(o.sfx, start + (o.sfxOffset || 0), o);
      });
      return this;
    }
    from(t, vars, o) { return this._add(t, vars, null, o); }
    to(t, vars, o) { return this._add(t, null, vars, o); }
    fromTo(t, a, b, o) { return this._add(t, a, b, o); }
    set(t, vars, at) { return this._add(t, null, vars, { at: isNum(at) ? at : (at && at.at) || 0, dur: 0 }); }
    cls(targets, name, o) {
      o = o || {};
      resolve(targets, this.root).forEach((el) => st.cls.push({ el, name, a: this._abs(o.at), b: o.until != null ? this._abs(o.until) : Infinity }));
      return this;
    }
    sfx(type, at, extra) { addCue(type, this._abs(at), extra || {}); return this; }
    frame(fn) { st.frameFns.push({ fn, scene: this._scene }); return this; }
    split(target, by) { return resolve(target, this.root).map((el) => split(el, by || 'words')); }
    // text reveal: by chars | words | lines, preset rise | fade | blur | pop | slide | mask | drop
    reveal(targets, o) {
      o = Object.assign({ by: 'words', preset: 'rise', at: 0, dur: 0.55, stagger: null, ease: null }, o || {});
      resolve(targets, this.root).forEach((el) => {
        const units = split(el, o.by, o.preset === 'mask');
        const n = units.length;
        const stg = o.stagger != null ? o.stagger : o.by === 'chars' ? Math.min(0.035, 0.9 / Math.max(1, n)) : o.by === 'lines' ? 0.12 : Math.min(0.08, 1.2 / Math.max(1, n));
        const side = st.dir === 'rtl' ? -1 : 1;
        const pr = o.preset;
        let from, ease = o.ease;
        if (pr === 'fade') from = { opacity: 0 };
        else if (pr === 'blur') from = { opacity: 0, blur: 14 };
        else if (pr === 'pop') { from = { opacity: 0, scale: 0.4 }; ease = ease || 'outBack'; }
        else if (pr === 'slide') from = { opacity: 0, x: side * 0.7 * parseFloat(getComputedStyle(el).fontSize) };
        else if (pr === 'drop') from = { opacity: 0, y: -0.6 * parseFloat(getComputedStyle(el).fontSize) };
        else if (pr === 'mask') { from = { y: '110%' }; ease = ease || 'outQuart'; }
        else from = { opacity: 0, y: 0.55 * parseFloat(getComputedStyle(el).fontSize) };
        const targetsU = pr === 'mask' ? units.map((u) => u.querySelector('.ptv-u') || u) : units;
        if (pr === 'mask') targetsU.forEach((u) => (u.style.display = 'inline-block'));
        this._add(targetsU, from, null, { at: o.at, dur: o.dur, ease: ease || 'outCubic', stagger: o.stagger ? o.stagger : { each: stg, from: o.from || 'start' }, sfx: o.sfx, sfxEvery: o.sfxEvery });
        el.setAttribute('data-lint-split', '1');
      });
      return this;
    }
    // typewriter. Works for every script (slices grapheme clusters).
    type(targets, o) {
      o = Object.assign({ at: 0, cps: 22, caret: true, jitter: 0.35, seed: 3, sfx: null }, o || {});
      resolve(targets, this.root).forEach((el) => {
        const text = el.getAttribute('data-text') || el.textContent;
        el.setAttribute('data-text', text);
        const g = graphemes(text);
        const r = mulberry32(o.seed);
        const times = [];
        let acc = this._abs(o.at);
        for (let i = 0; i < g.length; i++) {
          let d = (1 / o.cps) * (1 + (r() * 2 - 1) * o.jitter);
          const prev = g[i - 1] || '';
          if (/[.!?。！？؟۔]/.test(prev)) d *= 3.2; else if (/[,;:、،]/.test(prev)) d *= 1.8;
          acc += d;
          times.push(acc);
        }
        let caret = null;
        if (o.caret) {
          caret = document.createElement('span');
          caret.className = 'ptv-caret';
          caret.setAttribute('aria-hidden', 'true');
        }
        const txt = document.createTextNode('');
        el.textContent = '';
        el.appendChild(txt);
        if (caret) el.appendChild(caret);
        st.specials.push({ kind: 'type', el, txt, caret, g, times, scene: this._scene, startAbs: this._abs(o.at) });
        if (o.sfx) {
          let last = -1;
          times.forEach((tt, i) => { if (!/\s/.test(g[i]) && tt - last > 0.055) { addCue(o.sfx, tt, { gain: o.sfxGain }); last = tt; } });
        }
      });
      return this;
    }
    count(targets, o) {
      o = Object.assign({ from: 0, to: 100, at: 0, dur: 1.2, ease: 'outExpo', decimals: 0, prefix: '', suffix: '', format: null }, o || {});
      resolve(targets, this.root).forEach((el) => {
        const fmt = new Intl.NumberFormat(o.locale || st.lang, Object.assign({ minimumFractionDigits: o.decimals, maximumFractionDigits: o.decimals }, o.format || {}));
        st.specials.push({ kind: 'count', el, o, fmt, ease: getEase(o.ease), a: this._abs(o.at), scene: this._scene });
      });
      return this;
    }
    draw(targets, o) {
      o = Object.assign({ at: 0, dur: 1, ease: 'inOutCubic', from: 0, to: 1 }, o || {});
      return this._add(targets, { draw: o.from }, { draw: o.to }, o);
    }
    // slow camera move over the scene. o.origin sets the zoom centre, e.g. '30% 40%'
    camera(vars, o) {
      o = Object.assign({ at: 0, ease: 'inOutSine' }, o || {});
      if (o.dur == null) o.dur = this.dur + 0.6;
      let cam = this.root.querySelector(':scope > .cam');
      if (!cam) {
        cam = document.createElement('div');
        cam.className = 'cam';
        while (this.root.firstChild) cam.appendChild(this.root.firstChild);
        this.root.appendChild(cam);
      }
      if (o.origin) cam.style.transformOrigin = o.origin;
      const from = {}, to = {};
      for (const k in vars) { const v = vars[k]; if (Array.isArray(v)) { from[k] = v[0]; to[k] = v[1]; } else to[k] = v; }
      return this._add(cam, from, to, o);
    }
    // simulated pointer. points: [{at, x, y} | {at, to: '.selector', dx, dy}, click: true, move: 0.6]
    cursor(points, o) {
      o = Object.assign({ el: null, size: 1, sfx: 'click', start: null }, o || {});
      let el = o.el ? resolve(o.el, this.root)[0] : null;
      if (!el) {
        el = document.createElement('div');
        el.className = 'ptv-cursor';
        el.innerHTML = '<svg viewBox="0 0 32 32" width="100%" height="100%"><path d="M5 3 L5 26 L11 20.5 L15.5 30 L19.5 28.2 L15.2 18.8 L23 18.8 Z" fill="#111" stroke="#fff" stroke-width="2" stroke-linejoin="round"/></svg><span class="ptv-ripple"></span>';
        el.style.width = el.style.height = 3.4 * st.U * o.size + 'px';
        this.root.appendChild(el);
      }
      const pts = points.map((p) => Object.assign({ move: 0.6 }, p, { at: this._abs(p.at) }));
      pts.forEach((p) => { if (p.click && o.sfx) addCue(o.sfx, p.at, {}); });
      st.cursors.push({ el, pts, scene: this._scene, rip: el.querySelector('.ptv-ripple') });
      return this;
    }
    // play a <video> inside the scene from `at` (seconds into the scene)
    video(target, o) {
      o = Object.assign({ at: 0, offset: 0, rate: 1, loop: false }, o || {});
      resolve(target, this.root).forEach((v) => { v.muted = true; v.playsInline = true; v.preload = 'auto'; st.specials.push({ kind: 'video', el: v, o, a: this._abs(o.at), scene: this._scene }); });
      return this;
    }
  }

  function val(v, i, el) { return typeof v === 'function' ? v(i, el) : v; }
  function pushTween(el, prop, from, to, start, dur, ease, sceneId) {
    st.tweens.push({ el, prop, from, to, start, dur, ease, scene: sceneId, order: st.tweens.length });
  }
  function addCue(type, t, extra) {
    if (!type) return;
    const c = typeof type === 'object' ? Object.assign({}, type) : { type };
    c.t = +t.toFixed(4);
    if (extra && extra.gain != null) c.gain = extra.gain;
    st.cues.push(c);
  }

  // ------------------------------------------------------------------ text
  const segG = typeof Intl !== 'undefined' && Intl.Segmenter ? new Intl.Segmenter(undefined, { granularity: 'grapheme' }) : null;
  function graphemes(s) { return segG ? Array.from(segG.segment(s), (x) => x.segment) : Array.from(s); }
  // scripts whose letters join or form clusters across graphemes: never split by character
  const COMPLEX = /[؀-ۿ܀-ࣿﭐ-﷿ﹰ-﻿ऀ-෿฀-໿ༀ-࿿က-႟ក-៿᠀-᢯ꠀ-꯿߀-߿]/;
  const RTLCH = /[֐-ࣿיִ-﷿ﹰ-﻿]/;
  const LTRCH = /[A-Za-zÀ-ɏͰ-ϿЀ-ԯ԰-֏Ⴀ-ჿḀ-῿぀-ヿ㐀-鿿가-힯]/;
  function wordDir(w) { return RTLCH.test(w) ? 'rtl' : LTRCH.test(w) ? 'ltr' : null; }
  function split(el, by, mask) {
    if (el.__ptvSplit) return el.__ptvSplit;
    const lang = (el.closest('[lang]') || document.documentElement).getAttribute('lang') || st.lang;
    const text = el.textContent;
    if (by === 'chars' && COMPLEX.test(text)) { by = 'words'; }
    const segW = Intl.Segmenter ? new Intl.Segmenter(lang, { granularity: 'word' }) : null;
    const paraDir = getComputedStyle(el).direction || st.dir;
    const units = [];
    const mk = (cls, content) => { const s = document.createElement('span'); s.className = cls; if (content != null) s.textContent = content; return s; };
    const wrapUnit = (span) => {
      if (!mask) return span;
      const m = mk('ptv-m'); const u = mk('ptv-u'); u.appendChild(span); m.appendChild(u); return m;
    };
    const walk = (node) => {
      for (const child of Array.from(node.childNodes)) {
        if (child.nodeType === 1) { walk(child); continue; }
        if (child.nodeType !== 3 || !child.nodeValue) continue;
        const s = child.nodeValue;
        const frag = document.createDocumentFragment();
        const segs = segW ? Array.from(segW.segment(s)) : s.split(/(\s+)/).map((x) => ({ segment: x, isWordLike: /\S/.test(x) }));
        // group: word + trailing punctuation; merge runs whose direction is opposite to the paragraph
        const groups = [];
        for (const g of segs) {
          const isSpace = /^\s+$/.test(g.segment);
          if (isSpace) { groups.push({ space: true, text: g.segment }); continue; }
          const last = groups[groups.length - 1];
          const d = wordDir(g.segment);
          if (last && !last.space && (!g.isWordLike || !last.word)) { last.text += g.segment; last.word = last.word || g.isWordLike; last.dir = last.dir || d; continue; }
          groups.push({ text: g.segment, word: !!g.isWordLike, dir: d });
        }
        // merge opposite-direction runs (e.g. an English brand name inside Hebrew text)
        const merged = [];
        for (let i = 0; i < groups.length; i++) {
          const g = groups[i];
          if (!g.space && g.dir && g.dir !== paraDir) {
            let j = i, txt = g.text;
            while (j + 2 < groups.length && groups[j + 1].space && !groups[j + 2].space && (groups[j + 2].dir === g.dir || groups[j + 2].dir == null && /\d/.test(groups[j + 2].text))) { txt += groups[j + 1].text + groups[j + 2].text; j += 2; }
            merged.push({ text: txt, dir: g.dir }); i = j; continue;
          }
          merged.push(g);
        }
        for (const g of merged) {
          if (g.space) { frag.appendChild(document.createTextNode(g.text)); continue; }
          const w = mk('ptv-w');
          if (g.dir && g.dir !== paraDir) w.setAttribute('dir', g.dir);
          if (by === 'chars' && !(g.dir && g.dir !== paraDir)) {
            for (const ch of graphemes(g.text)) { const c = mk('ptv-c', ch); w.appendChild(c); units.push(wrapUnit(c)); if (mask) w.appendChild(units[units.length - 1]); }
            if (mask) { /* chars were appended inside wrappers */ }
          } else {
            w.textContent = g.text;
            if (by !== 'lines') units.push(w);
          }
          frag.appendChild(by === 'words' && mask ? wrapUnit(w) : w);
        }
        child.replaceWith(frag);
      }
    };
    walk(el);
    let out = units;
    if (by === 'lines') {
      const words = Array.from(el.querySelectorAll('.ptv-w'));
      const lines = [];
      let curTop = null, cur = null;
      for (const w of words) {
        const top = Math.round(w.offsetTop);
        if (curTop === null || Math.abs(top - curTop) > 2) { cur = []; lines.push(cur); curTop = top; }
        cur.push(w);
      }
      out = lines.map((ws) => {
        const ln = mk('ptv-ln');
        ws[0].parentNode.insertBefore(ln, ws[0]);
        let node = ws[0];
        const last = ws[ws.length - 1];
        while (node) { const next = node.nextSibling; ln.appendChild(node); if (node === last) break; node = next; }
        if (mask) { const m = mk('ptv-m ptv-mline'); const u = mk('ptv-u'); ln.parentNode.insertBefore(m, ln); u.appendChild(ln); m.appendChild(u); return m; }
        return ln;
      });
    }
    el.__ptvSplit = out;
    el.setAttribute('data-split', by);
    return out;
  }

  // ---------------------------------------------------------------- scenes
  function normTransition(tr) {
    if (!tr) return { type: 'cut', dur: 0 };
    if (typeof tr === 'string') tr = { type: tr };
    const d = { cut: 0, fade: 0.5, dip: 0.6, slide: 0.6, push: 0.6, wipe: 0.6, zoom: 0.55, blur: 0.5, iris: 0.7, flash: 0.25, whip: 0.4 };
    const type = tr.type || 'fade';
    return Object.assign({ dur: d[type] != null ? d[type] : 0.5, dir: 'forward' }, tr, { type });
  }
  function buildScenes() {
    const tl = st.cfg;
    const domScenes = Array.from(st.stage.querySelectorAll('.scene'));
    let list = [];
    if (tl.scenes && tl.scenes.length) {
      let t = 0;
      list = tl.scenes.map((s) => {
        const el = document.getElementById(s.id);
        if (!el) fail('timeline scene "' + s.id + '" has no <section class="scene" id="' + s.id + '">');
        const start = s.start != null ? +s.start : t;
        const dur = +s.dur;
        t = start + dur;
        return { id: s.id, el, start, dur, tr: normTransition(s.transition), meta: s };
      }).filter((s) => s.el);
      domScenes.forEach((el) => { if (!list.find((s) => s.el === el)) warn('scene #' + el.id + ' is not in the timeline; it will never show'); });
    } else {
      let t = 0;
      list = domScenes.map((el) => {
        const start = el.dataset.start != null ? +el.dataset.start : t;
        const dur = +(el.dataset.dur || 3);
        t = start + dur;
        return { id: el.id || 'scene' + domScenes.indexOf(el), el, start, dur, tr: normTransition(el.dataset.transition), meta: {} };
      });
    }
    list.sort((a, b) => a.start - b.start);
    st.scenes = list;
    list.forEach((s, i) => { st.sceneById[s.id] = s; s.index = i; s.el.style.zIndex = String(10 + i); });
    const end = list.length ? list[list.length - 1].start + list[list.length - 1].dur : 0;
    st.duration = tl.duration ? +tl.duration : end;
    // visibility windows + transition tweens (owned by the incoming scene)
    list.forEach((s, i) => {
      const next = list[i + 1];
      s.from = s.start;
      s.until = st.duration;
      if (next) {
        const tr = next.tr;
        s.until = (tr.type === 'cut' || tr.type === 'dip' || tr.type === 'flash') ? next.start : next.start + tr.dur;
      }
      const prev = list[i - 1];
      if (prev) transitionTweens(prev, s, s.tr);
    });
  }
  function transitionTweens(a, b, tr) {
    const t0 = b.start, d = tr.dur, rtl = st.dir === 'rtl';
    const ease = getEase(tr.ease || 'inOutCubic');
    let side = tr.dir === 'back' ? -1 : 1;
    if (rtl) side = -side;
    const add = (el, prop, f, t, start, dur, e) => pushTween(el, prop, f, t, start, dur, e || ease, null);
    switch (tr.type) {
      case 'cut': break;
      case 'fade':
        add(b.el, 'opacity', 0, 1, t0, d, getEase('inOutSine'));
        add(a.el, 'opacity', 1, 0, t0, d, getEase('inOutSine'));
        break;
      case 'dip':
        add(a.el, 'opacity', 1, 0, t0 - d / 2, d / 2, getEase('inSine'));
        add(b.el, 'opacity', 0, 1, t0, d / 2, getEase('outSine'));
        if (tr.color) st.dipColors.push({ t0: t0 - d / 2, t1: t0 + d / 2, color: tr.color });
        break;
      case 'slide': case 'push': {
        const ax = tr.dir === 'up' || tr.dir === 'down' ? 'y' : 'x';
        const sgn = tr.dir === 'down' ? -1 : tr.dir === 'up' ? 1 : side;
        const size = ax === 'x' ? st.W : st.H;
        add(b.el, ax, sgn * size, 0, t0, d);
        add(a.el, ax, 0, -sgn * size * (tr.type === 'push' ? 1 : 0.3), t0, d);
        if (tr.type === 'slide') add(a.el, 'opacity', 1, 0.0, t0, d, getEase('inQuad'));
        break;
      }
      case 'wipe': {
        const dir = tr.dir === 'up' ? 'up' : tr.dir === 'down' ? 'down' : side > 0 ? 'left' : 'right';
        const from = { left: 'inset(0% 0% 0% 100%)', right: 'inset(0% 100% 0% 0%)', up: 'inset(100% 0% 0% 0%)', down: 'inset(0% 0% 100% 0%)' }[dir];
        add(b.el, 'clipPath', from, 'inset(0% 0% 0% 0%)', t0, d);
        add(b.el, 'clipPath', 'inset(0% 0% 0% 0%)', 'none', t0 + d, 0);
        break;
      }
      case 'zoom':
        add(b.el, 'scale', 1.12, 1, t0, d, getEase('outCubic'));
        add(b.el, 'opacity', 0, 1, t0, d * 0.8, getEase('outSine'));
        add(a.el, 'scale', 1, 0.94, t0, d, getEase('inCubic'));
        add(a.el, 'opacity', 1, 0, t0, d, getEase('inSine'));
        break;
      case 'blur':
        add(b.el, 'opacity', 0, 1, t0, d, getEase('inOutSine'));
        add(b.el, 'blur', 24, 0, t0, d, getEase('outCubic'));
        add(a.el, 'opacity', 1, 0, t0, d, getEase('inOutSine'));
        add(a.el, 'blur', 0, 24, t0, d, getEase('inCubic'));
        break;
      case 'iris': {
        const at = tr.at || '50% 50%';
        add(b.el, 'clipPath', 'circle(0% at ' + at + ')', 'circle(150% at ' + at + ')', t0, d, getEase('inOutCubic'));
        add(b.el, 'clipPath', 'circle(150% at ' + at + ')', 'none', t0 + d, 0);
        break;
      }
      case 'whip': {
        add(b.el, 'x', side * st.W, 0, t0, d, getEase('outExpo'));
        add(b.el, 'blur', 30, 0, t0, d, getEase('outExpo'));
        add(a.el, 'x', 0, -side * st.W, t0, d, getEase('inExpo'));
        add(a.el, 'blur', 0, 30, t0, d, getEase('inExpo'));
        break;
      }
      case 'flash':
        st.flashes.push({ t0, d, color: tr.color || '#fff' });
        break;
      default: warn('unknown transition "' + tr.type + '"');
    }
  }
  st.dipColors = []; st.flashes = [];

  // ------------------------------------------------------------ evaluation
  function buildTracks() {
    const map = new Map();
    for (const tw of st.tweens) {
      let m = map.get(tw.el);
      if (!m) { m = new Map(); map.set(tw.el, m); }
      let arr = m.get(tw.prop);
      if (!arr) { arr = []; m.set(tw.prop, arr); }
      arr.push(tw);
    }
    st.tracks = [];
    for (const [el, m] of map) {
      const owner = el.closest ? el.closest('.scene') : null;
      const ownerScene = owner ? st.scenes.find((s) => s.el === owner) : null;
      for (const [prop, arr] of m) {
        arr.sort((a, b) => a.start - b.start || a.order - b.order);
        let prev = baseValue(el, prop);
        for (const tw of arr) {
          if (tw.from === undefined) tw.from = prev;
          if (tw.to === undefined) tw.to = baseValue(el, prop);
          prev = tw.to;
        }
        const isSceneRoot = el.classList && el.classList.contains('scene');
        st.tracks.push({ el, prop, arr, scene: isSceneRoot ? null : ownerScene });
        elState(el).touched.add(prop);
      }
    }
  }
  function trackValue(tr, t) {
    const arr = tr.arr;
    if (t < arr[0].start) return arr[0].from;
    let k = 0;
    for (let i = arr.length - 1; i >= 0; i--) if (arr[i].start <= t) { k = i; break; }
    const tw = arr[k];
    const p = tw.dur > 0 ? clamp((t - tw.start) / tw.dur, 0, 1) : 1;
    return interp(tr.prop, tw.from, tw.to, tw.ease(p));
  }
  function sceneVisible(s, t) { return t >= s.from && t < s.until; }

  function apply(t) {
    st.t = t;
    // 1. scenes
    for (const s of st.scenes) {
      const vis = sceneVisible(s, t) || (s.index === st.scenes.length - 1 && t >= s.from);
      if (vis !== s.vis) { s.vis = vis; s.el.classList.toggle('is-visible', vis); s.el.style.visibility = vis ? 'visible' : 'hidden'; }
    }
    // 2. tweens
    for (const tr of st.tracks) {
      if (tr.scene && !tr.scene.vis) continue;
      elState(tr.el).v[tr.prop] = trackValue(tr, t);
    }
    for (const s of st.els.values()) {
      const owner = s.el.closest ? s.el.closest('.scene') : null;
      if (owner && owner !== s.el && owner.style.visibility === 'hidden') continue;
      flush(s);
    }
    // 3. class toggles
    for (const c of st.cls) c.el.classList.toggle(c.name, t >= c.a && t < c.b);
    // 4. specials
    for (const sp of st.specials) {
      if (sp.scene && !sp.scene.vis && sp.kind !== 'video') continue;
      if (sp.kind === 'type') {
        let k = 0;
        while (k < sp.times.length && sp.times[k] <= t) k++;
        sp.txt.nodeValue = sp.g.slice(0, k).join('');
        const typing = k < sp.g.length;
        sp.el.toggleAttribute('data-typing', typing);
        if (sp.caret) {
          const idle = !typing || t < sp.startAbs;
          sp.caret.style.opacity = idle ? (Math.floor(t * 1.9) % 2 === 0 ? '1' : '0') : '1';
        }
      } else if (sp.kind === 'count') {
        const p = sp.o.dur > 0 ? clamp((t - sp.a) / sp.o.dur, 0, 1) : 1;
        const v = sp.o.from + (sp.o.to - sp.o.from) * sp.ease(p);
        sp.el.textContent = sp.o.prefix + sp.fmt.format(v) + sp.o.suffix;
      }
    }
    // 5. CSS animations and Web Animations: seek to global time
    try {
      for (const a of document.getAnimations()) {
        if (a.playState !== 'paused') a.pause();
        a.currentTime = t * 1000;
      }
    } catch (e) {}
    // 6. cursors (after layout-affecting changes)
    for (const c of st.cursors) applyCursor(c, t);
    // 7. frame callbacks
    for (const f of st.frameFns) {
      if (f.scene) { if (!f.scene.vis) continue; f.fn(t - f.scene.start, { t, dur: f.scene.dur, p: (t - f.scene.start) / f.scene.dur, el: f.scene.el, W: st.W, H: st.H, U: st.U }); }
      else f.fn(t, { t, dur: st.duration, p: t / st.duration, el: st.stage, W: st.W, H: st.H, U: st.U });
    }
    // 8. overlays: dip colour, flash, captions
    let dip = null;
    for (const d of st.dipColors) if (t >= d.t0 && t < d.t1) dip = d.color;
    st.stage.style.backgroundColor = dip || st.bg || '';
    if (st.flashEl) {
      let a = 0;
      for (const f of st.flashes) if (t >= f.t0 - f.d / 2 && t < f.t0 + f.d) { const p = t < f.t0 ? (t - (f.t0 - f.d / 2)) / (f.d / 2) : 1 - (t - f.t0) / f.d; a = Math.max(a, p); st.flashEl.style.background = f.color; }
      st.flashEl.style.opacity = String(clamp(a, 0, 1));
    }
    if (st.capEl) {
      let cur = '';
      for (const c of st.captions) if (t >= c.start && t < c.end) { cur = c.text; break; }
      if (st.capEl.__cur !== cur) { st.capEl.__cur = cur; st.capEl.firstChild.textContent = cur; st.capEl.style.visibility = cur ? 'visible' : 'hidden'; }
    }
  }

  function stagePoint(el, dx, dy) {
    const sr = st.stage.getBoundingClientRect();
    const k = sr.width / st.W;
    const r = el.getBoundingClientRect();
    return { x: (r.left + r.width / 2 - sr.left) / k + (dx || 0), y: (r.top + r.height / 2 - sr.top) / k + (dy || 0) };
  }
  function applyCursor(c, t) {
    if (c.scene && !c.scene.vis) return;
    const pts = c.pts;
    const pos = (p) => {
      if (p.to) { const el = resolve(p.to, c.scene ? c.scene.el : st.stage)[0]; if (el) return stagePoint(el, lenToPx(p.dx || 0), lenToPx(p.dy || 0)); }
      return { x: lenToPx(p.x != null ? p.x : st.W / 2), y: lenToPx(p.y != null ? p.y : st.H / 2) };
    };
    let x, y;
    if (t <= pts[0].at) { ({ x, y } = pos(pts[0])); }
    else {
      let i = 0;
      while (i < pts.length - 1 && pts[i + 1].at - pts[i + 1].move <= t) i++;
      const a = pos(pts[i]);
      if (i === pts.length - 1) { x = a.x; y = a.y; }
      else {
        const b = pts[i + 1], bp = pos(b);
        const s0 = Math.max(pts[i].at, b.at - b.move);
        const p = getEase('inOutCubic')(clamp((t - s0) / Math.max(0.001, b.at - s0), 0, 1));
        const mx = (a.x + bp.x) / 2, my = (a.y + bp.y) / 2;
        const nx = -(bp.y - a.y) * 0.12, ny = (bp.x - a.x) * 0.12; // gentle arc
        const q = 1 - p;
        x = q * q * a.x + 2 * q * p * (mx + nx) + p * p * bp.x;
        y = q * q * a.y + 2 * q * p * (my + ny) + p * p * bp.y;
      }
    }
    let press = 1, ripple = 0, rippleOn = false;
    for (const p of pts) {
      if (!p.click) continue;
      const dt = t - p.at;
      if (dt >= -0.06 && dt < 0.2) press = 1 - 0.16 * Math.sin(clamp((dt + 0.06) / 0.26, 0, 1) * PI);
      if (dt >= 0 && dt < 0.5) { rippleOn = true; ripple = dt / 0.5; }
    }
    c.el.style.transform = 'translate(' + x + 'px,' + y + 'px) scale(' + press + ')';
    if (c.rip) { c.rip.style.opacity = rippleOn ? String(0.55 * (1 - ripple)) : '0'; c.rip.style.transform = 'translate(-50%,-50%) scale(' + (0.2 + 1.6 * ripple) + ')'; }
  }

  // ----------------------------------------------------------------- media
  async function syncMedia(t) {
    const waits = [];
    for (const sp of st.specials) {
      if (sp.kind !== 'video') continue;
      const v = sp.el;
      let target = (t - sp.a) * sp.o.rate + sp.o.offset;
      const dur = v.duration || 0;
      if (dur) target = sp.o.loop ? ((target % dur) + dur) % dur : clamp(target, 0, dur - 0.001);
      else target = Math.max(0, target);
      if (Math.abs(v.currentTime - target) > 0.0005) {
        waits.push(new Promise((res) => {
          const done = () => { v.removeEventListener('seeked', done); res(); };
          v.addEventListener('seeked', done);
          setTimeout(done, 3000);
          v.currentTime = target;
        }));
      }
    }
    if (waits.length) await Promise.all(waits);
  }
  const raf = () => new Promise((r) => requestAnimationFrame(() => r()));

  // ---------------------------------------------------------------- probes
  const cvs = document.createElement('canvas');
  cvs.width = cvs.height = 1;
  const cctx = cvs.getContext('2d', { willReadFrequently: true });
  function rgba(css) {
    cctx.clearRect(0, 0, 1, 1);
    cctx.fillStyle = '#000';
    cctx.fillStyle = css;
    cctx.fillRect(0, 0, 1, 1);
    const d = cctx.getImageData(0, 0, 1, 1).data;
    return [d[0], d[1], d[2], +(d[3] / 255).toFixed(3)];
  }
  function effOpacity(el) {
    let o = 1, n = el;
    while (n && n !== document.body) {
      const cs = getComputedStyle(n);
      if (cs.visibility === 'hidden' || cs.display === 'none') return 0;
      o *= parseFloat(cs.opacity);
      if (n === st.stage) break;
      n = n.parentElement;
    }
    return o;
  }
  let blockCache = null;
  function textBlocks() {
    if (blockCache) return blockCache;
    const out = [];
    const sel = 'h1,h2,h3,h4,h5,h6,p,li,blockquote,figcaption,button,label,[data-read],[data-split],[data-text]';
    const seen = new Set();
    const cand = [];
    const consider = (el) => {
      if (seen.has(el)) return; seen.add(el);
      if (el.closest('[data-decor],[data-lint="off"],.ptv-cursor,.ptv-hud,.ptv-captions')) return;
      if (!(el.getAttribute('data-text') || el.textContent).trim()) return;
      cand.push(el);
    };
    st.stage.querySelectorAll(sel).forEach(consider);
    if (st.capEl) { const sp = st.capEl.firstChild; sp.setAttribute('data-lint', 'captions'); seen.add(sp); cand.push(sp); }
    // any other element that directly holds text
    st.stage.querySelectorAll('*').forEach((el) => {
      if (seen.has(el) || el.closest('.ptv-w,.ptv-c,.ptv-m,.ptv-ln,.ptv-captions')) return;
      for (const n of el.childNodes) if (n.nodeType === 3 && n.nodeValue.trim()) { consider(el); break; }
    });
    // keep the outermost text block only (a <p> with a <strong> inside is one block)
    const set = new Set(cand);
    for (const el of cand) {
      let p = el.parentElement, nested = false;
      while (p && p !== st.stage) { if (set.has(p)) { nested = true; break; } p = p.parentElement; }
      if (!nested) out.push(el);
    }
    out.forEach((el, i) => el.setAttribute('data-lint-id', String(i)));
    blockCache = out;
    return out;
  }
  function fullText(el) {
    if (el.hasAttribute('data-text')) return el.getAttribute('data-text');
    const typed = el.querySelectorAll('[data-text]');
    if (!typed.length) return el.textContent;
    const c = el.cloneNode(true);
    c.querySelectorAll('[data-text]').forEach((n) => { n.textContent = n.getAttribute('data-text'); });
    return c.textContent;
  }
  const segWord = Intl.Segmenter ? new Intl.Segmenter(undefined, { granularity: 'word' }) : null;
  function countWords(s) {
    if (!segWord) return (s.trim().match(/\S+/g) || []).length;
    let n = 0;
    for (const x of segWord.segment(s)) if (x.isWordLike) n++;
    return n;
  }
  function probe() {
    const sr = st.stage.getBoundingClientRect();
    const k = sr.width / st.W || 1;
    const safe = st.safe;
    const blocks = [];
    for (const el of textBlocks()) {
      const scene = el.closest('.scene');
      if (scene && scene.style.visibility === 'hidden') continue;
      let op = effOpacity(el);
      const units = el.querySelectorAll('.ptv-w,.ptv-c,.ptv-ln');
      if (op > 0 && units.length) {
        let mn = 1;
        units.forEach((u) => { const o = effOpacity(u); if (o < mn) mn = o; });
        op = Math.min(op, mn);
      }
      if (op <= 0.02) continue;
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) continue;
      const x = (r.left - sr.left) / k, y = (r.top - sr.top) / k, w = r.width / k, h = r.height / k;
      const cs = getComputedStyle(el);
      const full = fullText(el);
      const cls = Array.from(el.classList).filter((c) => !c.startsWith('ptv-') && c !== 'is-visible').slice(0, 2);
      blocks.push({
        id: +el.getAttribute('data-lint-id'), scene: scene ? scene.id : null,
        tag: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (cls.length ? '.' + cls.join('.') : ''),
        text: full.trim().replace(/\s+/g, ' ').slice(0, 80), words: countWords(full),
        x: +x.toFixed(1), y: +y.toFixed(1), w: +w.toFixed(1), h: +h.toFixed(1), opacity: +op.toFixed(3),
        size: parseFloat(cs.fontSize), color: rgba(cs.color),
        typing: el.hasAttribute('data-typing') || !!el.querySelector('[data-typing]'), lint: el.getAttribute('data-lint') || '',
        overflow: cs.display !== 'inline' && el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 2,
        safe: x >= safe.l - 2 && y >= safe.t - 2 && x + w <= st.W - safe.r + 2 && y + h <= st.H - safe.b + 2,
        inStage: x >= -2 && y >= -2 && x + w <= st.W + 2 && y + h <= st.H + 2,
      });
    }
    return { t: st.t, blocks };
  }

  // ----------------------------------------------------------------- setup
  function setupStage() {
    let stage = document.getElementById('stage');
    if (!stage) {
      stage = document.createElement('div');
      stage.id = 'stage';
      while (document.body.firstChild) stage.appendChild(document.body.firstChild);
      document.body.appendChild(stage);
    }
    st.stage = stage;
    const cfg = st.cfg;
    let fmt = params.get('format') || cfg.format || 'landscape';
    let W, H;
    const m = String(fmt).match(/^(\d+)x(\d+)$/);
    if (m) { W = +m[1]; H = +m[2]; fmt = W > H ? 'landscape' : W < H ? 'vertical' : 'square'; }
    else { [W, H] = FORMATS[fmt] || FORMATS.landscape; }
    if (cfg.width && cfg.height && !params.get('format')) { W = cfg.width; H = cfg.height; }
    st.W = W; st.H = H; st.U = Math.min(W, H) / 100; st.format = fmt;
    st.fps = +(params.get('fps') || cfg.fps || 30);
    const profile = params.get('safe') || cfg.safe || (fmt === 'vertical' ? 'social' : 'clean');
    const safe = profile === 'social' && fmt === 'vertical'
      ? { t: H * 0.14, b: H * 0.35, l: W * 0.083, r: W * 0.148 }
      : profile === 'social'
        ? { t: H * 0.06, b: H * 0.12, l: W * 0.05, r: W * 0.05 }
        : profile === 'none' ? { t: 0, b: 0, l: 0, r: 0 } : { t: H * 0.05, b: H * 0.05, l: W * 0.05, r: W * 0.05 };
    st.safe = safe; st.safeProfile = profile;
    const root = document.documentElement;
    const vars = { '--W': W + 'px', '--H': H + 'px', '--u': st.U + 'px', '--sw': W / 100 + 'px', '--sh': H / 100 + 'px',
      '--cap-band': Math.round(H * (W < H ? 0.09 : 0.13)) + 'px',
      '--safe-t': safe.t + 'px', '--safe-b': safe.b + 'px', '--safe-l': safe.l + 'px', '--safe-r': safe.r + 'px' };
    for (const k in vars) root.style.setProperty(k, vars[k]);
    root.classList.add('fmt-' + fmt);
    root.classList.add(W > H ? 'is-wide' : W < H ? 'is-tall' : 'is-square');
    stage.style.width = W + 'px';
    stage.style.height = H + 'px';
    if (cfg.background) { st.bg = cfg.background; stage.style.backgroundColor = cfg.background; }
    // overlays
    if (!stage.querySelector('.ptv-flash')) { const f = document.createElement('div'); f.className = 'ptv-flash'; stage.appendChild(f); }
    st.flashEl = stage.querySelector('.ptv-flash');
    document.body.classList.add(st.render ? 'ptv-render' : 'ptv-preview');
  }
  function setupLang() {
    const cfg = st.cfg;
    const strings = window.STRINGS || cfg.strings || null;
    let lang = params.get('lang') || cfg.lang || document.documentElement.getAttribute('lang') || 'en';
    st.lang = lang;
    const base = lang.toLowerCase().split(/[-_]/)[0];
    st.dir = (strings && strings[lang] && strings[lang]._dir) || (RTL.has(base) ? 'rtl' : 'ltr');
    document.documentElement.setAttribute('lang', lang);
    document.documentElement.setAttribute('dir', st.dir);
    if (strings) {
      const table = strings[lang] || strings[base] || null;
      if (!table) warn('no strings for lang "' + lang + '"');
      st.strings = table || {};
      const fallback = strings.en || strings[Object.keys(strings)[0]] || {};
      document.querySelectorAll('[data-i18n]').forEach((el) => {
        const key = el.getAttribute('data-i18n');
        const v = st.strings[key] != null ? st.strings[key] : fallback[key];
        if (v == null) { warn('missing string "' + key + '" for ' + lang); return; }
        if (el.hasAttribute('data-i18n-html')) el.innerHTML = v; else el.textContent = v;
      });
    }
  }
  function setupCaptions() {
    // data: window.CAPTIONS (written by voice.py). Burned in unless timeline "captions": {"burn": false} or ?captions=0
    const conf = st.cfg.captions;
    const caps = Array.isArray(conf) ? conf : window.CAPTIONS || null;
    if (!caps || params.get('captions') === '0' || (conf && conf.burn === false)) return;
    const list = Array.isArray(caps) ? caps : caps[st.lang] || caps.items || null;
    if (!list || !list.length) return;
    st.captions = list;
    const el = document.createElement('div');
    el.className = 'ptv-captions';
    el.setAttribute('data-lint', 'captions');
    el.appendChild(document.createElement('span'));
    st.stage.appendChild(el);
    st.capEl = el;
    document.documentElement.classList.add('has-captions');
  }

  async function loadFonts() {
    try {
      const faces = Array.from(document.fonts || []);
      await Promise.all(faces.map((f) => f.load().catch(() => null)));
      await document.fonts.ready;
    } catch (e) { warn('font loading: ' + e.message); }
  }
  async function loadImages() {
    const imgs = Array.from(st.stage.querySelectorAll('img'));
    await Promise.all(imgs.map((i) => (i.complete && i.naturalWidth ? i.decode().catch(() => {}) : new Promise((r) => { i.addEventListener('load', () => i.decode().then(r, r)); i.addEventListener('error', () => { fail('image failed to load: ' + i.getAttribute('src')); r(); }); }))));
    const imgEls = Array.from(st.stage.querySelectorAll('image'));
    imgEls.forEach((i) => { /* SVG <image>: best effort */ });
    const vids = st.specials.filter((s) => s.kind === 'video').map((s) => s.el);
    await Promise.all(vids.map((v) => (v.readyState >= 2 ? null : new Promise((r) => { v.addEventListener('loadeddata', r, { once: true }); v.addEventListener('error', () => { fail('video failed to load: ' + v.currentSrc); r(); }, { once: true }); setTimeout(r, 8000); v.load(); }))));
  }

  // ---------------------------------------------------------------- preview
  function setupPreview() {
    const hud = document.createElement('div');
    hud.className = 'ptv-hud';
    hud.innerHTML = '<button data-a="play" title="space">&#9654;</button><span class="ptv-time">0.00</span><div class="ptv-bar"><div class="ptv-fill"></div></div>'
      + '<button data-a="safe" title="safe area">safe</button><select data-a="fmt"><option>landscape</option><option>vertical</option><option>square</option><option>portrait</option></select>';
    document.body.appendChild(hud);
    const bar = hud.querySelector('.ptv-bar');
    st.scenes.forEach((s) => { const m = document.createElement('i'); m.style.left = (s.start / st.duration) * 100 + '%'; m.title = s.id; bar.appendChild(m); });
    const fill = hud.querySelector('.ptv-fill'), time = hud.querySelector('.ptv-time'), playBtn = hud.querySelector('[data-a=play]');
    const sel = hud.querySelector('[data-a=fmt]');
    sel.value = st.format;
    sel.onchange = () => { params.set('format', sel.value); location.search = params.toString(); };
    const safeEl = document.createElement('div');
    safeEl.className = 'ptv-safe-overlay';
    st.stage.appendChild(safeEl);
    hud.querySelector('[data-a=safe]').onclick = () => safeEl.classList.toggle('on');
    let audio = null;
    const audioSrc = params.get('audio') || st.cfg.audio;
    if (audioSrc) { audio = new Audio(audioSrc); audio.preload = 'auto'; }
    const fit = () => {
      const k = Math.min((window.innerWidth - 32) / st.W, (window.innerHeight - 90) / st.H, 1);
      st.stage.style.transform = 'scale(' + k + ')';
      document.body.style.setProperty('--fitW', st.W * k + 'px');
      document.body.style.setProperty('--fitH', st.H * k + 'px');
    };
    window.addEventListener('resize', fit); fit();
    let t0 = 0, tStart = 0;
    const show = (t) => { apply(t); syncMedia(t); fill.style.width = (t / st.duration) * 100 + '%'; time.textContent = t.toFixed(2) + ' / ' + st.duration.toFixed(2); };
    const loop = () => {
      if (!st.playing) return;
      let t = tStart + (performance.now() - t0) / 1000;
      if (t >= st.duration) { t = 0; tStart = 0; t0 = performance.now(); if (audio) { audio.currentTime = 0; } }
      show(t);
      requestAnimationFrame(loop);
    };
    const play = () => { st.playing = !st.playing; playBtn.innerHTML = st.playing ? '&#10073;&#10073;' : '&#9654;'; if (st.playing) { tStart = st.t >= st.duration - 0.05 ? 0 : st.t; t0 = performance.now(); if (audio) { audio.currentTime = tStart; audio.play().catch(() => {}); } loop(); } else if (audio) audio.pause(); };
    playBtn.onclick = play;
    const scrub = (e) => { const r = bar.getBoundingClientRect(); const t = clamp((e.clientX - r.left) / r.width, 0, 1) * st.duration; st.playing = false; playBtn.innerHTML = '&#9654;'; if (audio) audio.pause(); show(t); };
    bar.addEventListener('mousedown', (e) => { scrub(e); const mv = (ev) => scrub(ev); window.addEventListener('mousemove', mv); window.addEventListener('mouseup', () => window.removeEventListener('mousemove', mv), { once: true }); });
    window.addEventListener('keydown', (e) => {
      if (e.code === 'Space') { e.preventDefault(); play(); }
      else if (e.code === 'ArrowRight' || e.code === 'ArrowLeft') { const d = (e.shiftKey ? 1 : 1 / st.fps) * (e.code === 'ArrowLeft' ? -1 : 1); show(clamp(st.t + d, 0, st.duration)); }
      else if (e.code === 'Home') show(0);
    });
    show(+(params.get('t') || 0));
  }

  // ------------------------------------------------------------------ main
  async function start() {
    try {
      const tl = window.TIMELINE || {};
      st.cfg = Object.assign({}, st.cfg, tl, st.userCfg || {});
      st.bpm = (st.cfg.music && +st.cfg.music.bpm) || null;
      setupLang();
      setupStage();
      setupCaptions();
      await loadFonts();
      buildScenes();
      for (const b of st.builders) {
        const s = st.sceneById[b.id];
        if (!s) { fail('Stage.scene("' + b.id + '") has no matching scene'); continue; }
        try { b.fn(new Builder(s)); } catch (e) { fail('scene "' + b.id + '": ' + (e.stack || e.message)); }
      }
      for (const fn of st.globalBuilders) { try { fn(new Builder(null)); } catch (e) { fail('global builder: ' + (e.stack || e.message)); } }
      for (const fn of st.onFrameFns || []) st.frameFns.push({ fn, scene: null });
      buildTracks();
      await loadImages();
      st.cues.sort((a, b) => a.t - b.t);
      apply(0);
      await syncMedia(0);
      st.ready = true;
      api.isReady = true;
      if (!st.render) setupPreview();
    } catch (e) {
      fail('start: ' + (e.stack || e.message));
      api.isReady = true;
    }
  }

  const Stage = {
    config(c) { st.userCfg = Object.assign(st.userCfg || {}, c); return Stage; },
    scene(id, fn) { st.builders.push({ id, fn }); return Stage; },
    global(fn) { st.globalBuilders.push(fn); return Stage; },
    onFrame(fn) { (st.onFrameFns = st.onFrameFns || []).push(fn); return Stage; },
    start() { if (st.started) return; st.started = true; if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start(); return Stage; },
    str(key, fallback) { return (st.strings && st.strings[key]) != null ? st.strings[key] : fallback != null ? fallback : key; },
    ease: getEase, easings: EASE, bezier, lerp, clamp, random: mulberry32, noise,
    map: (v, a, b, c, d) => c + ((v - a) / (b - a)) * (d - c),
    split: (el, by) => split(el, by),
    get W() { return st.W; }, get H() { return st.H; }, get U() { return st.U; }, get lang() { return st.lang; }, get dir() { return st.dir; },
    get duration() { return st.duration; }, get fps() { return st.fps; }, get rendering() { return st.render; },
    get bpm() { return st.bpm; }, beat: (n) => (st.bpm ? (n * 60) / st.bpm : n * 0.5),
    // true while render.py --qa samples text layout: expensive canvas/WebGL drawing may be skipped
    get qa() { return !!window.__onevideoQA; },
  };
  const api = {
    isReady: false,
    async seek(t) {
      apply(t);
      await syncMedia(t);
      if (st.render && params.get('raf') === '1') await raf();
      return t;
    },
    info() {
      return { width: st.W, height: st.H, fps: st.fps, duration: st.duration, format: st.format, lang: st.lang, dir: st.dir,
        safe: st.safe, safeProfile: st.safeProfile, scenes: st.scenes.map((s) => ({ id: s.id, start: s.start, dur: s.dur, transition: s.tr })),
        errors: st.errors, warnings: st.warnings, cues: st.cues };
    },
    probe,
    cues: () => st.cues,
  };
  window.Stage = Stage;
  window.__stage = api;
})();
