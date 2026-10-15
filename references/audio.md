# Sound: music, effects, voice, mix

Sound carries half the feeling of a short video. Everything here is free: the music is composed fresh for each video by `music.py`, effects are synthesised in the song's key, and voices come from local text-to-speech.

## Contents
- Music styles
- Scoring to the picture
- Sound effects
- Voiceover
- Mixing and loudness
- Using the user's own music
- Licences at a glance

## Music styles

| style | sounds like | tempo | fits |
|---|---|---|---|
| uplifting | bright pop: plucks, warm pads, claps, a hook at the peak | 100 to 124 | product launches, apps, playful and default tones |
| tech | minor-key electronic, four-on-the-floor, offbeat bass, sidechain pump | 116 to 128 | developer tools, AI, fintech, bold |
| cinematic | strings, taiko hits, booms, long reverb | 78 to 100 | big claims, trailers, nature, ideas |
| lofi | swung drums, jazzy 7th chords, electric piano, vinyl crackle | 72 to 88 | cosy, personal, study, food, techy-chill |
| ambient | glassy pads, bells, very soft shaker | 68 to 88 | premium, wellness, calm explainers, deadpan |
| chiptune | square leads, triangle bass, noise drums | 124 to 150 | games, retro, playful |
| acoustic | strummed plucked strings, shaker, soft claps | 90 to 112 | handmade, outdoors, warm, food |
| hype | trap: 808 bass, hat rolls, halftime claps | 136 to 150 | bold, chaotic, sports, drops |
| piano | solo piano arpeggios over a soft pad | 68 to 92 | emotional, thank-you, nonprofit, minimal |
| none | no music (effects and voice only) | | deadpan bits, voice-led tutorials |

Same style, different song: change `music.seed`. Key and mode can be set (`"key": "D", "mode": "minor"`), otherwise the style picks one from the seed.

## Scoring to the picture

`timeline.json` drives the score:

```json
"music": {"style": "uplifting", "seed": 4, "ending": "sting", "lead": true, "gain_db": 0},
"scenes": [
  {"id": "hook", "dur": 2.5, "energy": 0.35, "music": "build"},
  {"id": "reveal", "dur": 3.0, "energy": 0.7, "music": "drop"},
  {"id": "pause", "dur": 1.5, "music": "stop"},
  {"id": "cta", "dur": 4.0, "energy": 0.6}
]
```

- `energy` 0 to 1 sets density: under 0.3 pads only, around 0.5 bass and light drums, 0.6+ arps, 0.78+ full drums and a melodic hook (the hook is off automatically when there is a voiceover). Unset energies follow a gentle arc.
- Scene hints: `build` (riser and snare roll into the next scene), `drop` (impact and crash at the scene start), `hit` (crash only), `stop` (music drops out: a dramatic pause before a punchline), `soft` (caps energy), `sting` (the final hit lands at this scene's start).
- A jump in energy of 0.25 or more adds a build and a crash automatically.
- Endings: `sting` (default: final chord, crash and impact land on the last scene, then ring out), `ringout` (gentle final chord; default for ambient and piano), `fade`, `button` (short stab on the last beat), `cut`.
- Run `timeline.py COMP --snap` before music so every cut sits on a beat. Then align big visual moments inside scenes with `at: s.beat(n)`.
- Transitions add their own effects unless `"auto_sfx": false`: whip gets a whoosh, slide/push/zoom a swoosh, flash a hit, wipe a swipe.

## Sound effects

Add cues three ways: `sfx` on tweens and helpers in the page (`render.py --cues` collects them), `timeline.sfx` entries (`{"scene": "reveal", "at": 0.2, "type": "impact", "gain": -3}` or `{"t": 7.5, ...}`), and transition defaults.

| moment | effect |
|---|---|
| element pops in | pop (consecutive pops climb the scale), bubble, tick |
| typing | type (thinned to stay natural) |
| cursor click, toggle | click, tap |
| big reveal, logo | impact, boom, stinger, crash |
| whip or slide | whoosh, swoosh, swipe |
| build into a moment | riser; downlifter after it |
| success, checkmarks | success, ding, sparkle, chime, notify |
| failure, wrong answer | error, glitch |
| photo, capture | shutter |
| weight, landing | thud, hit |

Density by tone: premium 2 to 4 effects in total, playful 6 to 12, bold dense but never on every frame. Repeated small sounds stay quiet (they are mixed low by default). Effects are tuned to the song's key and share its reverb, so they sound like part of the music.

## Voiceover

Use one when it adds information the picture can't (explainers, tutorials, longer ads) or when the user asks. Social cuts under 20 s usually work better with on-screen text and music only.

Writing for the ear:
- About 2.5 words per second in English (150 wpm); Spanish and Italian voices run nearer 3 words per second, Japanese and Mandarin are better counted in characters. Measure instead of guessing: `voice.py --say "the line" --lang es --out work/test.wav` prints the length. Leave 0.3 s of air at scene starts.
- The voice says what the screen doesn't: on screen "4-minute brew", voice "Drop in the leaves and walk; it's ready before you are."
- First line is the hook. Last line is the call to action, said once.
- Short sentences, contractions, no lists of more than three things, no URLs read aloud unless short.
- Only facts the user gave.

Engines (voice.py picks the first that supports the language):

| engine | languages | quality | licence and notes |
|---|---|---|---|
| kokoro (default) | English US/UK, Spanish, French, Hindi, Italian, Brazilian Portuguese, Japanese, Mandarin | natural | Apache-2.0 weights; `pip install kokoro-onnx`; ~190 MB downloaded once from GitHub; Japanese and Mandarin are weaker |
| piper | 40+ languages | good | GPL code; each voice has its own licence and many are non-commercial (including the Hebrew one); needs `voice.model` |
| espeak-ng | 100+ | robotic | GPL; last resort |
| macOS `say` | many | good | Apple's licence limits system voices to personal, non-commercial use |
| Windows SAPI | installed voices | ok | check before commercial use |

Kokoro voices (prefix = language, f/m = female/male): `af_heart`, `af_bella`, `af_nicole`, `am_michael`, `am_fenrir`, `am_puck` (US); `bf_emma`, `bf_isabella`, `bm_george`, `bm_fable` (UK); `ef_dora`, `em_alex` (es); `ff_siwis` (fr); `hf_alpha`, `hm_omega` (hi); `if_sara`, `im_nicola` (it); `pf_dora`, `pm_alex` (pt-br); `jf_alpha`, `jm_kumo` (ja); `zf_xiaobei`, `zm_yunjian` (zh). `voice.py --list` shows all 54.

No free, commercially safe natural voice for the language (Hebrew, Arabic, German, Russian and many more)? Options, in order: captions and on-screen text only; the user records the lines (save as `comp/audio/voice.wav`, 48 kHz, timed to the video); Chatterbox Multilingual (MIT, 23 languages including Hebrew and Arabic, but a heavy PyTorch install that wants a GPU); espeak-ng if a robotic voice is acceptable. Never clone or imitate a real person's voice.

Workflow: write `voice.lines` with `scene` and `at`, run `voice.py COMP`, read its report (lines that overrun their scene), lengthen scenes or trim words, re-snap, re-run voice and then music (music thins out under the voice and `assemble.py` ducks it about 9 dB, effects about 4 dB).

Per line options: `"speed": 1.1`; `"caption": false` (spoken but not captioned, for example when the same words are already big on screen); `"caption": "shorter text"` (caption differs from speech). `comp/voice.json` lists each line's start and end and per-word timings (`words: [{start, end, text}]`), so visuals can land on a spoken word: `at: wordStart - scene.start`.

## Mixing and loudness

`assemble.py` does the mix: music ducks about 9 dB under the voice (`--duck`), effects about 4 dB (`--sfx-duck`), and the result is normalised to -14 LUFS integrated with peaks under -1 dBTP (what YouTube, Spotify and most apps play back at). Adjust with `--music-gain`, `--sfx-gain`, `--voice-gain` (dB). `--silent` exports without audio; `--no-music` keeps voice and effects.

## Using the user's own music

Only with a track they own or have licensed. Analyse it, snap the timeline to its tempo, and point the timeline at it:

```bash
python3 SKILL_DIR/scripts/music.py --analyze comp/assets/song.mp3      # -> bpm, first_beat
python3 SKILL_DIR/scripts/timeline.py comp --snap --bpm 122
```

```json
"music": {"bpm": 122, "track": {"file": "assets/song.mp3", "offset": 31.2, "gain_db": -1}}
```

Choose `offset` so a strong downbeat (a chorus start) lands where the video needs energy, and make it `first_beat` plus a whole number of beats so cuts stay on the grid. Effects still come from music.py; the track fades out at the end.

## Licences at a glance

- Generated music and effects: original output of your run, free to use.
- Kokoro voice output: Apache-2.0 model, fine for commercial use.
- macOS voices: personal use only. Piper voices: check each voice card.
- User-supplied music, voice and photos: the user is responsible for rights; ask if unclear.
