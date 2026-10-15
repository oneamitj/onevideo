# Any language, any script, any machine

## Contents
- Choosing the video language
- Fonts per script
- Right-to-left (Hebrew, Arabic, Persian, Urdu)
- CJK, Thai and Indic scripts
- Numbers, dates, currency
- Translating a finished video
- Voice and captions per language
- Cultural checks
- Running on Windows, macOS, Linux and other agents

## Choosing the video language

Make the video in the language of the prompt unless the user says otherwise or the audience clearly speaks another one (ask when it's ambiguous, for example a Hebrew prompt about a product sold in the US). Brand names, URLs and code stay as they are. Put every visible string in `strings/<lang>.json` from the start, so a translation later is a new JSON file and a re-render.

## Fonts per script

`new_video.py --lang xx` adds a matching Noto font. Pick a display face with real character for the script too (all on Fontsource, OFL):

| script | body / safe | display options |
|---|---|---|
| Latin, Cyrillic, Greek | Inter, Noto Sans | Inter Tight, Manrope, Space Grotesk, Fraunces, Playfair Display, Anton, Rubik |
| Hebrew | Noto Sans Hebrew, Assistant | Rubik, Heebo, Secular One, Suez One, Frank Ruhl Libre |
| Arabic, Persian, Urdu | Noto Sans Arabic, Noto Naskh Arabic | Cairo, Tajawal, Almarai, Readex Pro, Amiri |
| Devanagari (Hindi, Marathi, Nepali) | Noto Sans Devanagari, Mukta | Hind, Poppins |
| Bengali, Tamil, Telugu | Noto Sans Bengali / Tamil / Telugu | Hind Siliguri, Mukta Malar |
| Thai | Noto Sans Thai, Sarabun | Prompt, Kanit |
| Japanese | Noto Sans JP | Zen Kaku Gothic New, M PLUS 1p, Kosugi Maru |
| Chinese | Noto Sans SC / TC | Noto Serif SC |
| Korean | Noto Sans KR | Black Han Sans, Gowun Dodum |

Put the script font in the stack after the Latin one: `font-family: 'Rubik', 'Noto Sans Hebrew', sans-serif;` so mixed text (Hebrew with an English brand name) uses the right glyphs for each. Check the contact sheet for tofu (empty boxes) or a fallback face that looks wrong.

## Right-to-left

- `<html lang="he" dir="rtl">` (new_video.py and `--lang` set it). Reading order, flex rows and text alignment follow automatically when the CSS uses logical properties: `margin-inline-start`, `padding-inline`, `inset-inline-start`, `text-align: start`. Avoid `left`/`right` for layout that should mirror.
- Motion follows reading direction: transitions with `dir: forward` and `reveal` presets flip automatically. Your own x tweens don't: use `s.rtl ? -1 : 1` as a sign.
- Mirror direction-bearing icons (arrows, progress, "next"): `[dir=rtl] .arrow { transform: scaleX(-1); }`. Don't mirror logos, clocks, checkmarks, media play buttons or numbers.
- Mixed text: English words and numbers inside RTL text are kept as one unit by the splitter. For a standalone LTR string (URL, code, phone number) add `dir="ltr"` on its element.
- Arabic letters connect: never animate Arabic per character. The runtime prevents it; prefer `words` or `lines` with `mask` or `fade`.

## CJK, Thai and Indic scripts

- Line breaking: `word-break: keep-all` for Korean, `line-break: strict` for Japanese; `text-wrap: balance` helps headlines in all of them.
- Keep caption and title lines to about 13 to 16 characters for Chinese and Japanese.
- Splitting uses `Intl.Segmenter`, so word reveals and reading-time QA work without spaces.
- Indic conjuncts and Thai clusters break if split by character: reveal by words or lines.

## Numbers, dates, currency

Format with the video's locale rather than by hand:

```js
new Intl.NumberFormat(Stage.lang).format(12500)                                // 12,500 / 12.500 / 12 500
new Intl.NumberFormat(Stage.lang, {style: 'currency', currency: 'EUR'}).format(34)
new Intl.DateTimeFormat(Stage.lang, {day: 'numeric', month: 'long'}).format(new Date('2026-11-01'))
s.count('.price', {to: 34, format: {style: 'currency', currency: 'ILS'}})
```

Arabic can use Arabic-Indic digits (`numberingSystem: 'arab'`); ask which the audience expects. Keep the currency the user gave; never convert prices.

## Translating a finished video

1. Copy `strings/en.json` to `strings/<lang>.json` and translate every value (keep keys). Translate meaning and tone, not word for word; keep lines short.
2. Voice lines written as `"text": "@key"` read the same file; otherwise add translated lines.
3. `render.py COMP --lang <lang> --stills auto --sheet work/sheet-<lang>.png` and `--qa --lang <lang>`: German, Finnish and Russian run 20 to 40% longer and overflow first; RTL needs a mirrored check.
4. `voice.py COMP --lang <lang>` if a voice exists for it, then `music.py` (voice timing changes the mix), render, assemble to `<slug>-<format>-<lang>.mp4`.
5. Ask a native speaker to check if the video will be published; machine translation of slogans goes wrong easily.

## Voice and captions per language

Natural free voices (Kokoro): English, Spanish, French, Hindi, Italian, Brazilian Portuguese, Japanese, Mandarin. Elsewhere: captions only, a voice the user records, a heavier open model (Chatterbox Multilingual covers 23 languages including Hebrew and Arabic), or robotic espeak-ng. See audio.md. Captions burn in with the video's fonts and direction.

## Cultural checks

Colours, gestures, animals and numbers carry different meanings across markets (white for mourning in parts of East Asia, the thumbs-up and OK gestures, the number 4 in Chinese, Japanese and Korean contexts). Holidays and calendars differ (week starts, date formats, Hijri and Hebrew calendars). Maps and borders are political: keep them schematic. When a video targets a market you're unsure about, say so and suggest a local review.

## Running on Windows, macOS, Linux and other agents

- Commands: `python3` on macOS and Linux, `python` (or `py`) on Windows. Paths in examples use `/`; PowerShell accepts them.
- Browser: Playwright's Chromium if installed, otherwise installed Chrome or Edge is found automatically (`ONEVIDEO_BROWSER=/path/to/chrome` forces one).
- ffmpeg: system install (`winget install ffmpeg`, `brew install ffmpeg`, `apt install ffmpeg`) or `pip install imageio-ffmpeg`.
- Fonts: macOS and Windows ship fonts for most scripts; on Linux install `fonts-noto` or fetch web fonts.
- No GPU (most cloud sandboxes): WebGL works in software, slower; prefer 2D/CSS motion, small 3D canvases.
- Network-restricted sandboxes: the npm registry, PyPI and GitHub releases are usually reachable (fonts, icons, three.js, kokoro-onnx and its models); Google Fonts, CDNs, Hugging Face and image APIs often aren't. `doctor.py` reports what works.
- Agents: the skill follows the Agent Skills format (SKILL.md plus scripts, references and assets), so Claude Code, Claude.ai, Codex, Gemini CLI, Cursor, Copilot, opencode and others can load it from their skills folder. The Claude API code-execution container has no network and may lack a browser, so use it there only with assets and a browser already present.
