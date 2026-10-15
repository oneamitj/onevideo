# stage.js runtime API

Read this before writing `comp/index.html`. The runtime is plain JavaScript with no dependencies. Every frame must be a pure function of time, because `render.py` jumps to arbitrary times (and runs several browsers on different chunks).

## Contents
1. Page structure
2. Scenes and transitions
3. Tweens: from, to, fromTo, set
4. Properties and units
5. Easing and stagger
6. Text: reveal, type, count, split
7. Drawing, camera, cursor, classes, video, custom frames
8. Sound cues from animation
9. Languages, formats, safe areas
10. Determinism rules
11. QA hints and preview
12. Pitfalls
13. Stage utilities
14. timeline.json fields

## 1. Page structure

```html
<!doctype html>
<html lang="en">                      <!-- lang drives RTL, number formats, word splitting -->
<head>
  <meta charset="utf-8">
  <link rel="stylesheet" href="runtime/stage.css">
  <link rel="stylesheet" href="assets/fonts/fonts.css">
  <style> /* your design */ </style>
</head>
<body>
<div id="stage">
  <section class="scene" id="hook"> ... </section>
  <section class="scene" id="reveal"> ... </section>
</div>
<script src="timeline.js"></script>   <!-- written from timeline.json by every script -->
<script src="strings.js"></script>    <!-- strings/<lang>.json, may be null -->
<script src="captions.js"></script>   <!-- from voice.py, may be null -->
<script src="runtime/stage.js"></script>
<script>
  Stage.scene('hook', s => { /* tweens, times relative to the scene start */ });
  Stage.scene('reveal', s => { ... });
  Stage.start();                      // last line, exactly once
</script>
</body>
</html>
```

Scene ids in `timeline.json` must match `<section class="scene" id="...">`. Put scene content inside `<div class="safe">` (respects platform UI) or `<div class="fill">` (full bleed). Builders run after fonts load, so measuring text inside them is safe.

ES modules (three.js) are fine: put `Stage.scene(...)` and `Stage.start()` inside the module script. Modules need http, so preview with `render.py COMP --serve`.

## 2. Scenes and transitions

Timing lives in `timeline.json`:

```json
"scenes": [
  {"id": "hook", "dur": 2.5, "energy": 0.4},
  {"id": "reveal", "dur": 3.0, "transition": "dip"},
  {"id": "feature", "dur": 3.0, "transition": {"type": "slide", "dur": 0.5, "dir": "forward"}}
]
```

A transition belongs to the incoming scene and starts at its `start`. Types:

| type | what happens | default dur |
|---|---|---|
| cut | hard cut | 0 |
| fade | crossfade (both scenes visible) | 0.5 |
| dip | old fades out, then new fades in; `color` sets the dip colour | 0.6 |
| slide | new slides in, old drifts and fades | 0.6 |
| push | new pushes old out of frame | 0.6 |
| wipe | clip-path reveal | 0.6 |
| zoom | new scales down into place, old scales away | 0.55 |
| blur | blurred crossfade | 0.5 |
| iris | circle reveal; `at: "30% 60%"` sets the centre | 0.7 |
| whip | very fast push with motion blur | 0.4 |
| flash | cut under a white (or `color`) flash | 0.25 |

`dir` is `forward` (default), `back`, `up` or `down`. Forward follows reading direction, so it flips automatically in right-to-left languages. Crossfading two busy layouts makes a muddy double exposure: use `dip`, or animate the old content out before the cut.

Inside a builder, `s.dur` is the scene length, `s.start` its absolute start, `s.root` its element, `s.W`, `s.H`, `s.U` the stage size and unit, `s.rtl` the direction, and `s.beat(n)` the length of n beats at the soundtrack tempo.

## 3. Tweens

```js
s.from(targets, fromVars, opts)          // animate from these values to the element's resting state
s.to(targets, toVars, opts)              // from the current value to these
s.fromTo(targets, fromVars, toVars, opts)
s.set(targets, vars, at)                 // jump at time `at`
```

`targets`: a selector (scoped to the scene), an element, or an array. `opts`: `{at: 0, dur: 0.6, ease: 'outCubic', stagger, sfx}`. Times are seconds from the scene start. Values may be functions `(i, el) => value` for per-element variation.

Several tweens on the same property chain in time order: a later `to` starts from where the earlier one ended. Before its first tween an element shows the first tween's starting value, so `from({opacity: 0})` keeps it hidden until it enters.

```js
s.from('.title', {y: 40, opacity: 0}, {at: 0.2, dur: 0.6});
s.to('.title', {scale: 1.04}, {at: 1.2, dur: 2.5, ease: 'linear'});      // slow drift while held
s.to('.title', {opacity: 0, y: -20}, {at: s.dur - 0.4, dur: 0.35, ease: 'inCubic'});
s.fromTo('.bar', {scaleX: 0}, {scaleX: 1}, {at: 0.5, dur: 0.8, ease: 'outExpo'});  // set transform-origin in CSS
```

## 4. Properties and units

| property | notes |
|---|---|
| `x`, `y`, `z` | px numbers, or `'50%'` (of the element), `'10u'` (u = 1% of short side), `'5sw'`, `'5sh'` (stage width/height %) |
| `scale`, `scaleX`, `scaleY`, `rotate`, `rotateX`, `rotateY`, `skewX`, `skewY` | degrees for rotations; add `perspective` on the parent for 3D flips |
| `opacity` | resting value respects your CSS (a 0.7 subtitle rests at 0.7) |
| `blur`, `brightness`, `contrast`, `saturate`, `grayscale`, `hueRotate` | composed into `filter` |
| `draw` | 0..1 of an SVG stroke drawn (see `s.draw`) |
| any CSS property in camelCase | `clipPath`, `backgroundPosition`, `letterSpacing`, `width`, `borderRadius`, `boxShadow`... numbers inside strings interpolate when both values have the same shape |
| colours | `color`, `backgroundColor`, `fill`, `stroke`, `borderColor`: any CSS colour; mixed in OKLab |
| `'--custom'` | CSS variables (unitless numbers or strings); drive gradients, masks and more from CSS |
| `attr: {r: 40}` | SVG/HTML attributes |

The runtime writes `transform` and `filter` inline, so an element animated with x/y/scale should not also carry a CSS transform. Wrap it instead: outer div positioned with CSS, inner div animated.

## 5. Easing and stagger

Names (case and dashes don't matter): `linear`, `in/out/inOut` + `Quad`, `Cubic`, `Quart`, `Quint`, `Sine`, `Expo`, `Circ`, `Back`, `Elastic`, `Bounce`; plus `smooth`, `snappy`, `swift`, `gentle`, `anticipate`, `spring`, or `'cubic-bezier(.2,.8,.2,1)'`. `out` = outCubic.

Use `outCubic`/`outQuart`/`outExpo` for entrances, `inCubic` for exits, `inOutCubic`/`inOutSine` for moves and camera, `outBack` sparingly for playful pops.

```js
s.from('.card', {y: 60, opacity: 0}, {at: 0.3, stagger: 0.08});
s.from('.dot', {scale: 0}, {at: 0.3, stagger: {each: 0.04, from: 'center'}});   // start|end|center|edges|random|index
```

## 6. Text

```js
s.reveal('.title', {by: 'words', preset: 'rise', at: 0.2});   // by: chars | words | lines
// presets: rise, fade, blur, pop, slide, drop, mask (lines or words slide up from behind a clip)
s.reveal('.lead', {by: 'lines', preset: 'mask', at: 0.6, stagger: 0.12, dur: 0.7});
s.type('.cmd', {at: 0.3, cps: 24, caret: true, sfx: 'type'}); // typewriter, natural rhythm, any script
s.count('.num', {from: 0, to: 12500, at: 0.5, dur: 1.4, prefix: '$', suffix: '+', decimals: 0});
s.count('.pct', {to: 0.42, format: {style: 'percent'}});      // Intl.NumberFormat options, locale from <html lang>
const words = s.split('.title', 'words');                     // spans you can tween yourself
```

Splitting uses `Intl.Segmenter`, so it works for Chinese, Japanese and Thai (no spaces). Arabic, Persian, Urdu and Indic scripts are never split into characters (letters join and would break); `chars` falls back to `words` there. In right-to-left text, embedded left-to-right runs (a brand name, a URL) stay together as one unit.

## 7. Drawing, camera, cursor, classes, video, custom frames

```js
s.draw('svg .route', {at: 0.4, dur: 1.2});                    // stroke draws on; needs stroke, no fill
s.camera({scale: [1, 1.06], x: [0, '-2sw']});                 // slow push across the whole scene
s.camera({scale: [1.1, 1]}, {origin: '30% 40%', ease: 'outCubic'});  // pull back from a detail
s.cursor([                                                    // simulated pointer with a click ripple
  {at: 0.4, x: '70sw', y: '80sh'},
  {at: 1.3, to: '.buy', click: true},                         // glides to the element centre, then clicks
  {at: 2.4, to: '.toast', dx: 40, dy: 10, move: 0.5}
]);
s.cls('.buy', 'is-pressed', {at: 1.3, until: 1.5});           // class toggled by time (style the state in CSS)
s.video('video.demo', {at: 0.2, rate: 1});                     // <video muted src="assets/demo.mp4">, seeked per frame
s.frame((t, info) => { /* draw to a canvas; t = seconds since scene start */ });
Stage.onFrame(t => { /* global, absolute time */ });
```

`Stage.global(s => {...})` gives a builder in absolute time for elements that live across scenes (a persistent logo, a progress bar).

## 8. Sound cues from animation

Any tween or helper takes `sfx: 'pop'` or `sfx: {type: 'pop', gain: -6}` (gain in dB), plus `sfxEvery: 3` to thin a stagger and `sfxOffset: -0.05` to lead the motion slightly. `s.type(..., {sfx: 'type'})` makes key ticks, `s.cursor` clicks make `click`. `s.sfx('whoosh', at, {gain: -3})` adds a cue directly. `render.py COMP --cues` writes them to `cues.json` and `music.py` turns them into sounds tuned to the song's key, so motion and sound land together. Names: whoosh, swoosh, swipe, riser, downlifter, impact, boom, hit, pop, click, tap, type, tick, ding, chime, sparkle, success, error, notify, glitch, shutter, bubble, thud, snap, crash, stinger.

## 9. Languages, formats, safe areas

- Strings: put copy in `strings/<lang>.json` and mark elements `data-i18n="key"` (add `data-i18n-html` for markup). `Stage.str('key')` reads one in JS. Render a translation with `render.py COMP --lang he`; direction switches to RTL for ar, he, fa, ur, yi, ps, sd, ug, dv, ckb.
- Formats: `landscape` 1920x1080, `vertical` 1080x1920, `square` 1080x1080, `portrait` 1080x1350, `wide` 2560x1080, or `WxH`. `<html>` gets `fmt-landscape|fmt-vertical|...` and `is-wide|is-tall|is-square`; write layout rules for each format you deliver.
- CSS variables: `--u` (1% of the short side; size everything with it), `--sw`, `--sh`, `--W`, `--H`, `--safe-t/r/b/l`.
- `.safe.sym` uses the larger side inset on both sides, so centred layouts look centred in vertical video, where the right-hand UI column is wider than the left margin.
- Safe area profiles: `social` (default for vertical: about 14% top, 35% bottom, 8% left, 15% right are covered by app UI), `clean` (5% margins, default otherwise), `none`. Override with `render.py --safe` or timeline `"safe"`.
- Captions from voice.py are burned in with class `.ptv-captions` (restyle the inner `span`). They sit in a band of height `--cap-band` at the bottom of the safe area; `<html>` gets `has-captions` and `.safe` stops above the band, so content laid out in `.safe` never collides with them. Turn them off with timeline `"captions": {"burn": false}` or for single lines with `"caption": false` on the voice line.

## 10. Determinism rules

- Animate only through the Stage API, CSS animations, or `frame` callbacks that read `t`.
- `Math.random()` gives a different frame on every render: use `Stage.random(seed)()` (seeded) and `Stage.noise(x, seed)` (smooth -1..1).
- No `setTimeout`, `setInterval`, `Date`, `performance.now()` for visuals.
- CSS `transition` is disabled inside the stage. CSS `@keyframes` loops are fine: all animations are paused and seeked to the global time (use them for ambient loops like a rotating gradient, not for sequenced entrances).
- Media: only `<video>` through `s.video` (seeked each frame) and images in `<img>` (decoded before frame 0). No audio elements: sound is mixed separately.
- Everything the page loads lives inside `comp/` with relative paths. No CDNs.

## 11. QA hints and preview

`render.py --qa` finds text blocks automatically (headings, paragraphs, list items, any element with its own text). Tune it with attributes:

| attribute | meaning |
|---|---|
| `data-decor` | decorative or background text: skip all checks |
| `data-lint="noread"` | no reading-time check (UI labels inside a mockup, ticker texture) |
| `data-lint="small-ok"` | allow small type (fine print you accept) |
| `data-lint="overlap-ok"` | intentional overlap |
| `data-read` | treat this element as one reading unit |

Live preview: `render.py COMP --serve`, open the URL. Space plays, arrows step a frame (shift: 1 s), the bar scrubs, `safe` toggles the safe-area overlay, the selector switches formats. Query params: `?format=vertical&lang=he&t=4.2&safe=social&audio=audio/soundtrack.wav`.

`window.__stage.info()` returns duration, scenes, warnings and errors; `window.__stage.seek(t)` jumps.

## 12. Pitfalls

- A CSS transform on an element you also tween with x/y/scale gets replaced. Wrap it.
- Scenes without an opaque background show the previous scene through crossfades.
- `from()` on an element hidden by your own CSS (`opacity: 0`) animates to that hidden value: drop the CSS opacity and let the tween hide it.
- Long words in German or Finnish overflow fixed-width boxes: use `max-width` in `ch`, `overflow-wrap: anywhere` for URLs, `text-wrap: balance` for headlines, and re-run QA per language.
- Text drawn into images or canvas is invisible to QA and translation. Keep text in the DOM.
- A selector that matches nothing logs a warning in `info().warnings`; read them.

## 13. Stage utilities

| name | what it is |
|---|---|
| `Stage.W`, `Stage.H`, `Stage.U` | stage size in px and the `--u` unit |
| `Stage.lang`, `Stage.dir` | current language and `ltr`/`rtl` |
| `Stage.duration`, `Stage.fps`, `Stage.rendering` | timeline length, frame rate, true while render.py captures |
| `Stage.qa` | true while `render.py --qa` samples text layout: skip expensive canvas drawing then (product3d.js does) |
| `Stage.bpm`, `Stage.beat(n)` | soundtrack tempo and the length of n beats |
| `Stage.ease(name)` | an easing function, e.g. to shape values inside `frame` callbacks |
| `Stage.easings`, `Stage.bezier(x1, y1, x2, y2)` | all named easings; a custom curve |
| `Stage.lerp(a, b, p)`, `Stage.clamp(v, a, b)`, `Stage.map(v, a, b, c, d)` | small maths helpers |
| `Stage.random(seed)` | seeded generator: `const r = Stage.random(7); r()` gives the same sequence on every render |
| `Stage.noise(x, seed)` | smooth noise in -1..1 for drift, shake, flicker |
| `Stage.split(el, by)` | split text yourself (words, chars, lines) |
| `Stage.str(key)` | a string from `strings/<lang>.json` |

## 14. timeline.json fields

```json
{
  "title": "Tidepool launch",
  "format": "landscape",                 // default render format; render.py --format overrides
  "fps": 30,
  "lang": "en",                          // render.py --lang overrides
  "background": "#0f1115",               // stage colour behind scenes (and dips)
  "safe": "social",                      // social | clean | none
  "captions": {"burn": true},
  "scenes": [
    {"id": "hook", "dur": 2.5, "energy": 0.4, "music": "build",
     "transition": {"type": "dip", "dur": 0.6, "color": "#000", "dir": "forward", "ease": "inOutCubic"}}
  ],
  "music": {"style": "uplifting", "seed": 3, "bpm": 112, "key": "D", "mode": "major", "ending": "sting",
            "sting_at": 17.5, "lead": true, "brightness": 1.0, "auto_sfx": true, "gain_db": 0,
            "track": {"file": "assets/song.mp3", "offset": 0, "gain_db": 0}},
  "sfx": [{"scene": "reveal", "at": 0.2, "type": "impact", "gain": -3}, {"t": 9.4, "type": "whoosh", "pan": -0.5}],
  "voice": {"engine": "auto", "lang": "en-us", "voice": "af_heart", "speed": 1.0, "model": null,
            "lines": [{"id": "l1", "scene": "hook", "at": 0.3, "text": "...", "speed": 1.0, "caption": true}]}
}
```

`start` and `beats` on scenes, `duration` and `music.bpm` are filled in by `timeline.py --snap`; leave them alone unless you mean to override. `music.sting_at` moves the final hit (default: the last scene's start). `brightness` above 1 makes pads and plucks brighter, below 1 darker. Comments above are for reading only; JSON files can't contain them.
