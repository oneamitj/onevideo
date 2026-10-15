# Motion design rules

Craft notes for making the video look designed rather than generated. Read once per video before building, and again when the contact sheet looks off.

## Contents
- Tones
- Layout per format
- Type
- Colour and contrast
- Motion timing
- Transitions
- Readability
- Depth and texture
- Accessibility
- Failure modes and fixes

## Tones

Presets are defaults; the user's own words ("like a 2016 Series A launch", "museum exhibit") refine or override them. Pick the music style with the same row.

| tone | feel | scenes per 20 s | transitions | type | music style |
|---|---|---|---|---|---|
| playful | warm, bright, a little cheeky | 5 to 6 | slide, pop, iris | rounded or chunky sans, mixed sizes | uplifting, chiptune, acoustic |
| premium | calm, confident, lots of space | 3 to 4 | slow fade, dip, mask reveals | light/medium weights, wide tracking, serif accents | ambient, piano |
| bold | loud, fast, high contrast | 6 to 8 | hard cut, whip, flash (not more than one per second) | heavy condensed caps, tilted words | hype, tech |
| cinematic | epic, trailer scale | 4 to 5 | dip to black, slow zoom, wipe | big caps, generous letter spacing | cinematic |
| techy | precise, clean, systematic | 4 to 6 | push, wipe, cut on beat | grotesk + mono for data | tech, lofi |
| warm | human, cosy, handmade | 4 to 5 | fade, slide | humanist sans or soft serif | acoustic, lofi, piano |
| deadpan | dry, still, the pause is the joke | 3 to 4 | slow fade, hard cut | plain sans, small, centred | ambient at low level, or "stop" scenes |
| chaotic | maximal, overproduced | 7 to 9 | flash, whip, zoom | caps, stacked, rotated | hype, chiptune |

## Layout per format

- Landscape 16:9: horizontal compositions, text left and visual right (mirrored in RTL), generous margins. Headline up to about 16 characters per line at full size.
- Vertical 9:16: stack vertically, larger type (about 1.2x the landscape `--u` multiple), important things in the middle of the frame. App UI covers the bottom third; captions take a band just above it (`.safe` already stops above that band when captions exist), so lay content out inside `.safe` and let decoration fill the rest.
- Square 1:1 and portrait 4:5: centred stacks, tighter copy.
- Write layout rules per format with `.fmt-vertical ...` selectors and check stills for each format you deliver.
- Keep a consistent grid: one margin, one gutter, one baseline step (multiples of `--u`).

## Type

- Two families at most (display + body), plus mono for code or data.
- Size with `--u`: display 7u to 14u, subhead 4u to 6u, body 3u to 4u, small labels at least 2u (about 22 px at 1080). Anything smaller is unreadable on a phone.
- Tight leading for big type (1.0 to 1.1), letter spacing slightly negative for heavy display weights, positive for small caps labels.
- `text-wrap: balance` on headlines, `max-width` in `ch` to keep lines short.
- One emphasis device per line (colour or weight or italic, not all three).
- Fonts: fetch with `fetch_assets.py fonts`. Good free display faces: Inter Tight, Space Grotesk, Sora, Manrope, Fraunces, Playfair Display, DM Serif Display, Bricolage Grotesque, Archivo, Anton (condensed caps), Rubik. For non-Latin scripts see global.md.

## Colour and contrast

- Build the palette from the brand if there is one (exact hex from their site or logo); otherwise choose one dominant background, one ink colour and one accent. Roughly 60 / 30 / 10.
- Text contrast: 4.5:1 for body, 3:1 for large display text. `render.py --qa` measures it on the real frame.
- Over photos or 3D: add a scrim (gradient from the text side), a blurred panel, or move the text.
- Dark backgrounds feel premium and hide compression artefacts; light backgrounds feel fresh but show banding in gradients (add grain).

## Motion timing

| motion | duration | easing |
|---|---|---|
| micro (icon pop, tick, small fade) | 0.15 to 0.3 s | outCubic, outBack for playful |
| element entrance | 0.4 to 0.7 s | outCubic, outQuart, outExpo |
| exit | 0.25 to 0.4 s (faster than entrances) | inCubic |
| move on screen | 0.5 to 0.9 s | inOutCubic |
| scene transition | 0.4 to 0.7 s (0.25 for bold cuts) | inOutCubic |
| camera drift | the whole scene | linear or inOutSine, 2 to 6% scale |
| stagger between items | 0.04 to 0.1 s (chars 0.02 to 0.035) | |

Principles: one thing leads, the rest follows (overlap entrances by 40 to 60%); things enter from the direction they are going; big things move slower than small things; settle, then hold. A held frame stays alive with a slow camera drift, a breathing glow or a looping background, never with text jitter.

Sync to music: cut on beats (`timeline.py --snap` does it), land big reveals on downbeats with `at: s.beat(n)`, and let sequences of items tick with the beat only when each item is not something to read (icons, dots). Readable lines get at least the reading floor, even if that means every other beat.

## Transitions

Use one or two transition types per video, matched to tone. Motivate them: a slide continues the direction of motion, a dip marks a change of topic, a hard cut on a beat adds energy. Busy-to-busy crossfades look muddy; animate the old content out first, or dip. Save the flashiest transition for the biggest moment.

## Readability

- Reading time once fully on screen and settled: about 0.3 s per word, at least 0.8 s for 1 to 3 words and 1.2 s for a sentence. QA checks it.
- On-screen words per scene: at most (scene duration - 0.6) / 0.3. A 3 s scene carries about 8 words. Cut copy rather than speed up.
- Fast in, then hold. Never fast in, then gone.
- With a voiceover, show keywords on screen, not the sentence being spoken.

## Depth and texture

- Layers: background (gradient, texture), midground (subject), foreground (type, particles). Move them at different speeds for parallax.
- Grain at 3 to 6% opacity removes the sterile CG look and hides banding.
- Soft shadows under objects (large blur, low opacity, offset down), light sweeps across hero objects, a subtle vignette.
- Real materials read better than flat fills: gradients with a highlight, a 1 px inner border, a little noise.

## Accessibility

- No more than three flashes in any one second (WCAG 2.3.1). `render.py` warns when it detects rapid luminance flips. Avoid full-frame red flashes entirely.
- Captions for anything spoken; sound-off viewers are the majority on social.
- Contrast as above; avoid red/green as the only difference between two states.
- Respect the content's reading direction for motion (RTL videos move start-to-end from right to left).

## Failure modes and fixes

| what you see | fix |
|---|---|
| looks like a slideshow | add motion inside scenes: camera drift, sequential reveals, cursor or hand interaction |
| looks generic | use the subject's real copy, colours, objects and numbers; cut abstract shapes that could be in any video |
| everything moves at once | stagger, lead with one element, give the eye one place to look |
| text is cramped or tiny | fewer words, bigger type, split the scene |
| muddy transitions | dip or animate-out before the cut |
| dead air at the end | land the CTA on the sting and hold; or shorten the last scene |
| cluttered vertical cut | stack, enlarge, drop secondary elements for that format |
| music fights the edit | re-snap with `timeline.py --snap`, raise energy where the visuals peak, add a `stop` before the punchline |
