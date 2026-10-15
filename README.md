# onevideo

An agent skill that turns a prompt into a finished short video, rendered on your own machine with free tools. Describe a product, an app, an idea or an event; get back an MP4 with motion, an original soundtrack, sound effects, optional voiceover and captions, a poster frame and a caption to post with it.

No paid APIs, no stock subscriptions, no watermark. The music is composed fresh for every video, so there's nothing to license.

## What it makes

Product launches (physical products as 3D renders or from your photos), app and code demos, explainers, announcements, social ads, data stories, kinetic type. 16:9, 9:16, 1:1 and 4:5. Any language the browser can draw, right-to-left included; natural voiceover in eight languages, English and Spanish among them.

## How it works

The video is a web page. Each scene is a section, and a small runtime (`stage.js`) makes every frame a pure function of time. `render.py` opens the page in headless Chromium, jumps to each frame, screenshots it and pipes the frames into FFmpeg. A single `timeline.json` drives everything with a clock: scene timing, the soundtrack (`music.py` writes an original score in one of nine styles, with cuts on the beat and effects tuned to the song's key), the voice (`voice.py`, local Kokoro text-to-speech) and the mix (`assemble.py`: ducking, -14 LUFS, AAC).

Before the expensive render, the skill looks at a contact sheet of key frames and runs a QA pass that measures what the viewer will see: text that isn't on screen long enough to read, text clipped by the frame or hidden by app UI, overlaps, tiny type, low contrast (measured on real pixels) and flashing.

The idea came from [latent-spaces/brag](https://github.com/latent-spaces/brag), which makes launch videos from a codebase. This skill takes the same approach (Claude directs, a browser renders, FFmpeg encodes) and widens it to any subject, any language, with its own music engine instead of bundled tracks.

## Install

Needs Node 18+ (for the installer), Python 3.9+, FFmpeg, and a Chromium browser Playwright can drive.

**Claude Code**

```bash
npx onevideo            # copies the skill to ~/.claude/skills/onevideo
npx onevideo setup      # pip install playwright numpy + Chromium (add --full for scipy, kokoro-onnx voice)
npx onevideo doctor     # check Python, FFmpeg, browser, fonts, voice
```

Restart Claude Code and ask for a video. Use `--project` to install into `./.claude/skills` instead.

**Claude Desktop (and claude.ai)**

```bash
npx onevideo desktop    # writes ~/Downloads/onevideo.zip
```

Then Settings > Capabilities > Skills > Upload skill, pick the zip. Code execution has to be on. The Claude Code tab inside Desktop uses the Claude Code install above.

**Other agents** (Codex, Gemini CLI, Cursor and more): `npx onevideo --agents` installs to `~/.agents/skills`. `npx onevideo --all` does Claude Code plus the Desktop zip in one go.

Or straight from GitHub: `npx skills add oneamitj/onevideo`.

Remove with `npx onevideo uninstall`.

## Try it

> Make a 20 second launch video for Tidepool, a glass bottle with a built-in tea infuser. 750 ml, bamboo lid, $34, ships November 1. Calm and premium, for Instagram and YouTube.

> Turn this repo into a 25 second demo video for X.

> A 30 second vertical explainer in Spanish about the two-minute rule, with a voiceover.

The skill asks up to four quick questions (platform, feel, voice, assets) or picks sensible defaults if you say "just make it".

## Good to know

- Without a GPU, 3D scenes render at roughly a second per frame. Expect a few minutes for a 3D-heavy 20 second video on a laptop CPU, much faster with a GPU. Flat 2D motion renders at 5 to 15 frames per second.
- Fonts, icons and three.js come from the npm registry; the voice model (about 190 MB) downloads once from GitHub.
- Voices for Hebrew, Arabic, German and many other languages aren't covered by the free natural engine; those videos use captions, your own recording, or a heavier open model.
- Facts in the video come only from what you tell it. It won't invent prices, stats or testimonials.

## Licence

MIT for this skill. Generated music and effects are yours. Kokoro voice weights are Apache-2.0; fonts fetched from Fontsource are mostly OFL; every downloaded asset is recorded in the project's `assets/LICENSES.json`.
