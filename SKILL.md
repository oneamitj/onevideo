---
name: onevideo
description: Make a polished short video from just a prompt. Product launches (physical or digital), app and code demos, explainers for an idea, announcements, ads, reels, trailers, data stories and kinetic type. Writes the story and storyboard, animates it in HTML/CSS/SVG/WebGL, composes an original soundtrack with sound effects, adds optional voiceover and captions in many languages (right-to-left too), and renders MP4s for YouTube, Reels, TikTok, LinkedIn or X. Runs locally with free tools (headless Chromium, FFmpeg, Python), so no paid APIs, stock subscriptions or watermarks. Use it whenever someone wants a video, promo, teaser, reel, short, motion graphic or animated explainer made, even if they only describe the thing to show.
license: MIT
compatibility: Needs Python 3.9+ with numpy, ffmpeg, and a Chromium browser driven by Playwright (pip install playwright; Chrome or Edge also work). Optional scipy (better audio), kokoro-onnx (voiceover). Works offline once fonts and models are cached.
metadata:
  version: "1.0.2"
---

# OneVideo

You are the director, designer, editor and composer. From a prompt (plus anything the user can share: photos, a logo, a codebase, a URL), make a short video that feels made for this exact subject, then render it on this machine with free tools.

How it works. The video is a web page: one `<section class="scene">` per scene, animated by `stage.js` so that every frame is a pure function of time. `render.py` serves the page, seeks it frame by frame in headless Chromium and pipes the screenshots into FFmpeg. `timeline.json` holds all timing; `music.py` composes an original score to it (cuts on beats, builds, a final sting) plus key-matched sound effects, `voice.py` speaks lines with local text-to-speech and writes captions, and `assemble.py` ducks, masters to -14 LUFS and muxes. Nothing costs money and nothing leaves the machine.

`SKILL_DIR` below means the folder containing this file. Use `python3` (Windows: `python`). Every script has `--help`.

## The run

1. Check the machine
2. Understand the brief (ask or assume)
3. Plan
4. Build the composition (voice first, when there is one)
5. Look and lint
6. Music and effects
7. Render and deliver

Keep the user informed with short updates (plan ready, draft ready), not a running commentary.

## 1. Check the machine

```bash
python3 SKILL_DIR/scripts/doctor.py
```

If `ready` is false, run the commands in `fix` (usually `pip install playwright`, and `python3 -m playwright install chromium` when no Chrome or Edge is installed). Note three things for later: `browser.gpu` (false means WebGL runs in software, so keep 3D small), `network` (npm registry gives fonts, icons and three.js; GitHub releases give the voice model), and `voice.kokoro` (natural voiceover available or installable with `pip install kokoro-onnx`).

## 2. Understand the brief

Work out:
- **Subject type**: physical product, app/software/code, website, idea or concept, event or announcement, data, brand or person, place or service, tutorial. Read the matching section of `references/storyboards.md`.
- **Facts**: list every concrete fact the user gave (names, prices, dates, specs, numbers, claims, URLs, quotes). Only these may appear as facts in the video. Tone, jokes and framing are yours to invent; facts are not.
- **Sources**: a codebase or URL means inspecting it first (real copy, colours, fonts, UI flows; never secrets, tokens, internal URLs or real customer data). Photos or a logo from the user beat anything you draw.

Ask once, only what would change the video, at most four questions, each with a recommended default (use the ask-user tool if there is one):
1. Where will it be posted? (sets format and length)
2. What feel? (offer three tones that suit this subject, see the tone table in `references/motion-design.md`)
3. Voiceover? (none, or which language)
4. Assets and must-haves: logo, photos, brand colours, the call to action, two or three key facts.

Skip what the prompt already answers. If the user says "just make it", is away, or answers vaguely, use the defaults and state them in one line:

| decision | default |
|---|---|
| format | 16:9 1920x1080; 9:16 first if they mention Reels, TikTok, Shorts or Stories |
| length | about 20 s (15 to 30) for promos; 30 to 60 s for explainers and tutorials |
| tone | inferred from the subject and how the user writes |
| music | on, style from the tone |
| voice | off, unless asked or the piece is an explainer/tutorial over 30 s |
| language | the prompt's language |

Offer one or two improvements when they would clearly help, briefly and without blocking: a 9:16 cut for social, real product photos instead of illustrations, a voiceover for a long explainer, a translated version, a 6 s bumper for ads, captions for sound-off viewing.

## 3. Plan

Write `OUT/plan.md` using the template at the end of `references/storyboards.md`: the angle (one sentence that makes this video specific), audience, the single takeaway, the hook (first 2 seconds), a scene table (id, duration, energy, exact on-screen text, visual and motion, transition, sound), voice lines if any, the poster moment and a share-copy draft. Check the reading budget: a scene holds about (duration - 0.6) / 0.3 words. With a voiceover, size scenes from the real speech: `python3 SKILL_DIR/scripts/voice.py --say "line" --lang es --out OUT/work/l1.wav` prints its length (speaking rates differ a lot between languages and voices). If the user asked to approve the plan, show a short summary and wait; otherwise keep going.

## 4. Build the composition

```bash
python3 SKILL_DIR/scripts/new_video.py OUT --title "Tidepool launch" --format landscape --lang en [--fonts "Fraunces" "Inter"] [--3d]
```

This creates `OUT/comp/` (runtime, starter page, timeline, strings, fonts) and `OUT/work/`. Then:

1. Edit `comp/timeline.json`: scenes (`id`, `dur`, `energy` 0 to 1, `transition`, music hint), `music` (style, seed, ending), `sfx`, `voice.lines`. The full field list is at the end of `references/runtime-api.md`.
2. `python3 SKILL_DIR/scripts/timeline.py comp --snap` picks a tempo and moves every cut onto a beat. Run it again whenever durations change.
3. Voiceover, when there is one: `python3 SKILL_DIR/scripts/voice.py comp`. It writes the voice track, captions and per-word timings (`comp/voice.json`) and reports lines that run past their scene. Lengthen those scenes or cut words, snap again, re-run. Captions burn into a band at the bottom of the safe area and `.safe` shrinks to stay clear of it, so do this before laying out the page.
4. Write `comp/index.html` and `comp/strings/<lang>.json`. Read `references/runtime-api.md` first. For visuals use `references/visual-toolkit.md` (3D products, illustrated products, user photos, mockups, code, charts, maps, icons); for layout, type, colour and motion use `references/motion-design.md`.

Rules for the page, because the renderer depends on them:
- Animate only from time: the Stage API, CSS keyframe loops, or `frame(t)` callbacks. `Stage.random(seed)` instead of `Math.random()`; no timers, no `Date`.
- Everything the page loads sits inside `comp/` with relative paths (fonts, images, three.js). No CDNs.
- Text stays real DOM text (not baked into images) so QA, captions and translation work.
- Size with `var(--u)`, keep text inside `.safe`, give each scene an opaque background, and write layout rules for every format you will deliver (`.fmt-vertical ...`).

## 5. Look and lint

This gate catches most problems before an expensive render.

```bash
python3 SKILL_DIR/scripts/render.py OUT/comp --stills auto --sheet OUT/work/sheet.png
```

Open the sheet image and look at every frame as a viewer would: is the subject clear in the first frame, is anything clipped, colliding, too small, low-contrast or empty, and does any transition frame look muddy? Fix and repeat. Then:

```bash
python3 SKILL_DIR/scripts/render.py OUT/comp --qa
```

QA reports text held too briefly to read, text off-frame or outside the safe area, overflow, overlaps (captions included), tiny type, low contrast (measured on the real pixels) and runtime warnings. Fix every error and every warning you can't justify. Re-run both until clean. For vertical or translated versions run the same two commands with `--format` and `--lang`.

## 6. Music and effects

```bash
python3 SKILL_DIR/scripts/render.py OUT/comp --cues      # sound cues from the animation (pops, typing, clicks)
python3 SKILL_DIR/scripts/music.py OUT/comp              # score + effects -> comp/audio/
```

Keep big hits (impact, stinger, crash) out of spoken words: move them into gaps between lines. For a different song in the same style, change `music.seed`; for a different mood, `music.style`. Styles, scene hints, effects, voices and languages are in `references/audio.md`. With the user's own track, follow "Using the user's own music" there.

## 7. Render and deliver

```bash
python3 SKILL_DIR/scripts/render.py OUT/comp --out OUT/work/video.mp4 --poster-at 6.2 --poster OUT/<slug>-poster.jpg
python3 SKILL_DIR/scripts/assemble.py OUT/comp --video OUT/work/video.mp4 --out OUT/<slug>-16x9.mp4
```

`--poster-at` is the time of the strongest settled frame (title fully in, not mid-transition). It becomes frame 0, which is the thumbnail Slack, X, Discord and most players show. For Reels, TikTok and Shorts, which loop and let you upload a cover, add `--no-bake`: the JPG is still saved but frame 0 stays the real first frame, so the loop doesn't flash the title. `render.py` prints an ETA; for long or 3D-heavy pieces, render a `--quality draft` first and show it. Shell tools often stop commands after about 10 minutes, and 3D on a machine without a GPU costs around a second per frame, so start long renders in the background and poll the log:

```bash
nohup python3 SKILL_DIR/scripts/render.py OUT/comp --out OUT/work/video.mp4 --poster-at 6.2 > OUT/work/render.log 2>&1 &
tail -n 3 OUT/work/render.log     # repeat until the JSON result appears
```

Other formats: `--format vertical|square|portrait` (check stills for that format first). Translations: `--lang xx` with `strings/xx.json`, see `references/global.md`. Add `--gif OUT/<slug>.gif` to assemble for a small preview.

Deliver in `OUT/`: the MP4(s), the poster JPG, `<slug>.srt` if there is a voice (copy of `comp/captions.srt`), and `share.txt` (one to three lines in the video's language, postable as-is, specific, no "excited to share"). Then tell the user where the files are, the creative angle in one sentence, and one or two next steps (a vertical cut, another music seed or style, a different hook, a translation, a voiceover). `references/platforms.md` has specs, safe zones and deliverable sets.

## Creative laws

- **Hook in 2 seconds.** Plan it first. Something visual happens in frame 1; never open on a logo or a slow fade from black.
- **Show the thing.** The product, the UI in use, the idea as an image. Abstract shapes that could belong to any video are filler.
- **Specific.** Use the subject's own words, colours, objects and numbers. Banned: "streamline your workflow", "unlock the power", "revolutionize", "next-level", "seamless", "game-changer".
- **One idea per scene,** and one place for the eye to land.
- **Readable.** Fast in, then hold: about 0.3 s per word fully settled, at least 0.8 s for one to three words. Cut words before cutting holds.
- **Alive.** Sequential reveals, simulated clicks and typing, camera drift, parallax. Nothing sits frozen for more than two seconds.
- **Sound and picture are one piece.** Cuts on beats, hits on reveals, silence on purpose.
- **Every frame is postable.** Any paused frame should look designed.
- **Short.** 15 to 30 s for social, up to 60 s for explainers. Never pad.
- **Honest.** No invented facts, numbers, testimonials, awards or partner logos. Illustrations must not show features the product lacks.

## Rights and safety

- Real people: no fabricated likeness or voice. Use photos or recordings only when the user supplies them and has the rights.
- No other companies' logos, products or characters, and nothing that implies an endorsement that wasn't given.
- Music is generated per video and free to use. A user-supplied track needs the user's confirmation that they may use it.
- Downloaded assets get their licence recorded in `comp/assets/LICENSES.json`; required credits go into the share text.
- Health, finance and legal claims: only what the user provided, phrased as their claim.
- Flashing: no more than three flashes per second; `render.py` warns when it detects them.

## When something breaks

| symptom | fix |
|---|---|
| page never ready | read the printed console errors; a typo in a builder or a missing `Stage.start()` |
| "selector matched nothing" | the element is in another scene or the class name differs |
| wrong or missing font | check `assets/fonts/fonts.css` and the family name fetch_assets printed; add the script font for non-Latin text |
| 3D slow or blank | `doctor.py` gpu false: smaller canvas, `mat.glassFast`, or 2D/SVG instead; ES modules need `render.py --serve` to preview |
| no voice for the language | captions only, a recording from the user, or another engine (audio.md) |
| music too loud or quiet | `assemble.py --music-gain -3`, or lower scene `energy` |
| ffmpeg lacks libx264 | `pip install imageio-ffmpeg` |
| render too slow | `--quality draft` while iterating; `--workers` on machines with more cores |

## Reference files

- `references/runtime-api.md`: the stage.js API. Read before writing `index.html`.
- `references/storyboards.md`: hooks, beat sheets per subject, endings, the plan template.
- `references/motion-design.md`: tones, layout per format, type, colour, timing, transitions, readability.
- `references/visual-toolkit.md`: 3D and illustrated products, user photos, mockups, code, charts, maps, icons, free asset sources and licences.
- `references/audio.md`: music styles and scoring hints, sound effects, voice engines and languages, mixing, user music.
- `references/platforms.md`: formats, lengths, safe zones, captions, encoding, deliverables.
- `references/global.md`: languages and scripts, RTL, fonts, translation, other operating systems and agents.
