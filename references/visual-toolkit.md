# Visual toolkit

Recipes for showing the subject well with free tools. Snippets assume the stage.js API (runtime-api.md) and sizes in `--u`.

## Contents
1. Backgrounds and texture
2. Physical products: 3D studio, illustration, user photos
3. Device mockups and UI
4. Code and terminals
5. Charts and numbers
6. Maps and routes
7. Icons and logos
8. Reusable moments: lower third, split screen, before/after, checklist, countdown, confetti
9. Free asset sources and licences
10. Generated images

## 1. Backgrounds and texture

```css
.bg-mesh { position:absolute; inset:-10%; background:
  radial-gradient(40% 50% at 20% 30%, #ffd1b3 0, transparent 70%),
  radial-gradient(45% 55% at 80% 70%, #b9d7ff 0, transparent 70%), #f6efe7; }
.grain { position:absolute; inset:0; pointer-events:none; opacity:.06; mix-blend-mode:multiply;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E"); }
.vignette { position:absolute; inset:0; pointer-events:none; background:radial-gradient(120% 90% at 50% 45%, transparent 55%, rgba(0,0,0,.35)); }
.grid { position:absolute; inset:0; background-image:linear-gradient(rgba(255,255,255,.06) 1px, transparent 1px),
  linear-gradient(90deg, rgba(255,255,255,.06) 1px, transparent 1px); background-size: calc(var(--u)*6) calc(var(--u)*6); }
@keyframes drift { to { transform: translate(-3%, 2%) scale(1.06); } }   /* ambient loop: allowed */
.bg-mesh { animation: drift 12s ease-in-out infinite alternate; }
```

Light sweep across a hero object: a skewed white gradient band animated with `s.fromTo('.sweep', {x: '-120%'}, {x: '220%'}, {at: 0.6, dur: 1.1, ease: 'inOutSine'})` inside an `overflow:hidden` wrapper, `mix-blend-mode: overlay`.

## 2. Physical products

### 3D studio (no photos needed)

Best for rotationally symmetric or boxy products. Fetch three.js once (`new_video.py OUT --3d` does it), then:

```html
<script type="importmap">{"imports":{"three":"./assets/vendor/three/build/three.module.js","three/addons/":"./assets/vendor/three/examples/jsm/"}}</script>
<script type="module">
import { studio, lathe, cylinder, box, mat, profiles, turn, float } from './assets/recipes/product3d.js';
const s3 = studio(document.querySelector('#hero canvas'), { background: '#ece5da' });   // match the scene colour
const body = lathe(profiles.bottle(0.42), mat.glass('#e6f5ff'));
const tea  = lathe([[0,-0.97],[0.38,-0.97],[0.38,0.2],[0,0.2]], mat.liquid('#b8742f'));
const lid  = cylinder(0.24, 0.3, mat.wood('#c49a6c')); lid.position.y = 1.0;
s3.add(body, tea, lid);
Stage.scene('hero', s => s.frame(t => {
  s3.root.rotation.y = turn(t, 28, 20);          // 28 deg/s turntable, starting at 20 deg
  s3.root.position.y = float(t, 0.03);           // gentle hover
  lid.position.y = 1.0 + Math.max(0, 0.5 - t) * 0.6; // lid settles in the first half second
  s3.render();
}));
Stage.start();
</script>
```

- Profiles are `[radius, y]` pairs from bottom to top, about 2 units tall. Ready-made: bottle, cup, jar, vase, can, candle, lid. Edit numbers to match the described shape.
- Materials: `glass` (refractive, slower), `glassFast`, `frosted`, `metal(color, roughness)`, `plastic`, `matte`, `ceramic`, `rubber`, `wood`, `liquid`.
- Labels and logos on a product: draw them on a 2D canvas, use it as a `CanvasTexture` on a slightly larger lathe or a plane.
- Exploded view: offset parts along y with a tween-like function of t inside `frame`, then bring them back.
- Callouts that follow the product: `const p = s3.point(lid, [0.24, 0.1, 0]);` gives stage pixels; set an SVG line's `x1/y1` to it every frame and put the label at the other end.
- Speed: without a GPU each 3D frame costs 0.2 to 1.5 s (refractive glass is the expensive part, about 3x). Size the canvas to the product, keep 3D to the scenes that need it, and render in the background. `glassFast` is much cheaper but reads as faint, barely-there glass; use it for drafts (`render.py --param glass=fast` with a switch in your page) and the refractive `glass` for the final.

### Illustrated product (SVG)

For shapes 3D primitives can't do (shoes, garments, food, tools). Draw with layered SVG: a base shape with a vertical gradient, a darker side shape for volume, one or two highlight shapes with white at 30 to 60% opacity, a soft ellipse shadow underneath. Keep the style flat-but-dimensional and consistent across scenes. Animate parts separately (laces drawing on, a cap lifting).

### User photos

Photos the user owns are the strongest material. Cut out the background with rembg (MIT; models download from GitHub releases):

```bash
pip install "rembg[cpu,cli]"
rembg i -m u2net comp/assets/raw/product.jpg comp/assets/product.png     # always pass -m: the default model is not free for commercial use
```

Then place the PNG on a designed set: soft shadow (`filter: drop-shadow(...)` or a blurred ellipse), a slow push with `s.camera`, parallax between layers, macro crops (`object-position` + scale) for detail scenes. Never alter a photo so the product looks different from reality.

## 3. Device mockups and UI

```html
<div class="phone"><div class="screen"> ...recreated app UI... </div></div>
<style>
.phone { position:relative; width:calc(var(--u)*34); aspect-ratio:9/19.5; border-radius:calc(var(--u)*5);
  background:#0c0c0e; padding:calc(var(--u)*1.2); box-shadow:0 calc(var(--u)*3) calc(var(--u)*8) rgba(0,0,0,.35), inset 0 0 0 2px #2a2a2e; }
.phone .screen { width:100%; height:100%; border-radius:calc(var(--u)*4); overflow:hidden; background:#fff; }
.browser { border-radius:calc(var(--u)*1.4); overflow:hidden; box-shadow:0 calc(var(--u)*2) calc(var(--u)*6) rgba(0,0,0,.25); }
.browser .bar { height:calc(var(--u)*4); background:#eceef1; display:flex; align-items:center; gap:calc(var(--u)*.8); padding-inline:calc(var(--u)*1.5); }
.browser .bar i { width:calc(var(--u)*1.2); height:calc(var(--u)*1.2); border-radius:50%; background:#d0d3d8; }
</style>
```

Recreate UI in HTML with the product's real colours, fonts and copy (from the codebase or site). Use `data-lint="noread"` on small UI labels that are texture rather than message. Interactions: `s.cursor` to click, `s.cls` for pressed/selected states, `s.type` into inputs, items arriving with stagger, a toast sliding in. A slight 3D tilt (`rotateX: 8, rotateY: -12` on a wrapper with `perspective`) adds depth.

## 4. Code and terminals

```html
<pre class="term"><code><span class="p">$</span> <span class="cmd" data-lint="noread">npx create-thing my-app</span>
<span class="out o1">✓ Created my-app in 2.1s</span></code></pre>
```

Type the command with `s.type('.cmd', {at: .3, cps: 26, sfx: 'type'})`, then reveal output lines with `s.from('.out', {opacity: 0, y: 8}, {at: 1.6, stagger: .12})`. Colour tokens by hand with spans (keyword, string, comment). Use real commands and output from the project. Big code is unreadable on a phone: show 3 to 6 lines, 3u type or larger.

## 5. Charts and numbers

```html
<svg viewBox="0 0 600 300" class="chart">
  <rect class="b" x="40" y="60" width="90" height="240" fill="var(--accent)"/>
  <rect class="b" x="170" y="140" width="90" height="160" fill="#c9c3b8"/>
</svg>
```

```js
s.from('.chart .b', {scaleY: 0}, {at: .3, dur: .8, ease: 'outExpo', stagger: .1});   // CSS: .b {transform-box: fill-box; transform-origin: bottom}
s.count('.big', {to: 48, at: .3, dur: 1.2, suffix: '%'});
s.draw('.chart .line', {at: .5, dur: 1.4});                                      // polyline with stroke
```

Label axes in words, put the unit next to the number, annotate the one point that matters. Numbers must come from the user.

## 6. Maps and routes

No tile services. Draw an abstract map: a few muted shapes for land or blocks, roads as strokes, a route as a path that draws on, a pin that drops with `outBack` and a pulse ring. For real geography the user cares about, ask for the place names and keep shapes schematic.

## 7. Icons and logos

- `fetch_assets.py icons COMP leaf zap shield` (Lucide, ISC) or `--set tabler` (MIT); `search-icons <word>` finds names. Inline the SVG markup so you can colour it with `currentColor` and draw strokes on with `s.draw`.
- The user's logo (SVG preferred) goes in `assets/`. Never recreate another company's logo or use it to imply endorsement.
- No logo? Build a wordmark: the name in the display font, one detail (a coloured dot, a custom letter, tight tracking).
- Logo reveal ideas: mask reveal by line, stroke draw then fill, letters popping on beats, a shape morph into the mark, light sweep across.

## 8. Reusable moments

- Lower third: name + role in a bar that slides in from the start side, holds 2 s, slides out.
- Split screen: two `.fill` halves, the divider wiping across (`clipPath` from `inset(0 100% 0 0)` to `inset(0 50% 0 0)`).
- Before / after: same frame twice, the after layer revealed with a clip-path wipe and a handle line following it.
- Checklist: items arrive with stagger, a check path draws on each (`s.draw`) with `sfx: 'tick'`.
- Countdown: big numbers swapping with `s.set` per second, scale pop on each, `sfx: 'tick'`.
- Confetti or particles: a `<canvas>` drawn in `s.frame`, positions computed from `t` and `Stage.random(seed)` (spawn once, then position = start + velocity * t + gravity * t * t / 2).
- End card: product or logo, name, one line, URL. Hold at least 2 s; land it on the sting.

## 9. Free asset sources and licences

Prefer, in order: what the user provides, things you draw (CSS, SVG, canvas, 3D), then openly licensed assets. Record every downloaded asset in `comp/assets/LICENSES.json` (fetch_assets.py does this for fonts, icons and npm packages) and add required credits to the share text.

| need | source | licence | notes |
|---|---|---|---|
| fonts | Fontsource via `fetch_assets.py fonts` | mostly OFL-1.1 | works through the npm registry |
| icons | Lucide (`lucide-static`), Tabler | ISC, MIT | via `fetch_assets.py icons` |
| 3D, charts, utilities | three.js, d3 (via `fetch_assets.py npm`) | MIT, ISC | bundle locally, no CDN |
| photos | Openverse API (no key, ~100 requests/day) | filter `license_type=commercial,modification` | keep the attribution it returns |
| photos | Wikimedia Commons | per file | send a descriptive User-Agent |
| photos/video | Pexels, Unsplash | free licence; API key from the user | Unsplash API requires hotlinking and credit |
| music | generated by music.py | yours | user tracks: the user confirms rights |

Never scrape image search results, never use photos of real people as if they were customers or endorsers, and don't present stock photos as the user's product, team or venue.

## 10. Generated images

Local image models (for example FastSD CPU with SD-Turbo or SDXS) can run on a laptop, but check each model's licence (several restrict commercial use) and label AI imagery honestly. A connected image-generation tool may cost money: say so and ask before using it. For products that exist, prefer the user's real photos; illustrations must not show features the product lacks.
