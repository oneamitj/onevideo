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

Pick your app. Python 3.9+ is the only thing to have first; Claude can install the rest (a bundled FFmpeg and a browser) for you.

### Claude Desktop (one click)

1. Download [`onevideo.mcpb`](https://github.com/oneamitj/onevideo/releases/latest/download/onevideo.mcpb) from the latest release.
2. Double-click it (or drag it into Settings > Extensions) and press **Install**.
3. Start a chat: "Make a 20 second launch video for ..." (or pick the *make_video* prompt). The first time, Claude runs the one-time setup itself.

Videos land in a folder called `onevideo` in your home folder (change it in the extension's settings). Claude can open it for you.

From a terminal instead: `npx onevideo desktop` builds the extension and opens it in Claude Desktop.

### Claude Code (plugin)

```text
/plugin marketplace add oneamitj/onevideo
/plugin install onevideo@onevideo
```

Then `/onevideo:onevideo` or just ask for a video. The Plugins menu in Claude Code (terminal, VS Code, or the Code tab in Desktop) does the same by clicking.

### Claude Code (npx)

```bash
npx onevideo            # copies the skill to ~/.claude/skills/onevideo, gives you /onevideo
npx onevideo setup      # pip install playwright numpy ffmpeg + Chromium (--full adds scipy, kokoro-onnx voice)
npx onevideo doctor     # check Python, FFmpeg, browser, fonts, voice
```

Restart Claude Code and ask for a video. `--project` installs into `./.claude/skills` instead.

You can also paste this into Claude Code running **on your own machine** (terminal or VS Code, not a cloud or sandboxed session):

> Install the onevideo skill: run `npx -y onevideo`, then `npx onevideo setup` and `npx onevideo doctor`, fix anything doctor reports, then tell me to restart.

### claude.ai and other agents

- claude.ai (web): download `onevideo.skill` from the release (or `npx onevideo desktop --zip`), then Settings > Capabilities > Skills > Upload skill. Code execution has to be on.
- Codex, Gemini CLI, Cursor and more: `npx onevideo --agents`, or `npx skills add oneamitj/onevideo`.

Remove with `npx onevideo uninstall` (npx install) or from the Extensions / Plugins menu.

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
