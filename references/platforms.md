# Platforms, formats and deliverables

Numbers checked October 2026. Platforms change limits often; when a user depends on an exact limit, look it up.

## Formats

| format | size | render flag | use |
|---|---|---|---|
| landscape 16:9 | 1920x1080 | `--format landscape` | YouTube, websites, presentations, LinkedIn, X |
| vertical 9:16 | 1080x1920 | `--format vertical` | Reels, TikTok, Shorts, Stories |
| square 1:1 | 1080x1080 | `--format square` | feeds (LinkedIn, X, Facebook), carousels |
| portrait 4:5 | 1080x1350 | `--format portrait` | Instagram and Facebook feed |
| wide 21:9 | 2560x1080 | `--format wide` | website hero banners |

## Platform notes

| platform | best format | sweet-spot length | limits | captions |
|---|---|---|---|---|
| YouTube | 16:9 | 30 s to 2 min for promos | 15 min unverified, 12 h verified | upload SRT or VTT |
| YouTube Shorts | 9:16 | 15 to 45 s | up to 3 min | burn in |
| Instagram Reels | 9:16 | 15 to 30 s | up to 20 min | burn in |
| TikTok | 9:16 | 15 to 35 s | 10 min via API | burn in |
| LinkedIn | 1:1, 4:5 or 16:9 | 20 to 45 s | posts about 15 min | upload SRT (desktop) |
| X | 16:9 or 1:1 | 15 to 45 s | 140 s free, longer with Premium | upload SRT (web) |
| Facebook | 4:5 or 9:16 | 15 to 40 s | every video posts as a Reel | upload SRT named like `name.en_US.srt` |
| Website hero | 16:9 or 21:9, often silent and looping | 6 to 15 s | keep under ~5 MB | none (silent) |
| Slides / talks | 16:9 | 10 to 60 s | | burn in if voiced |

Vertical safe zone: app UI covers roughly the top 14%, bottom 35%, 8% on the left and 15% on the right. The `social` safe profile (default for vertical) keeps `.safe` inside that. Backgrounds and decoration can bleed under the UI; text and faces can't.

## Encoding (what the scripts produce)

- H.264 High profile, yuv420p, BT.709 colour, 30 fps (set `fps` in the timeline for 24 or 60), GOP 2 s, CRF 17, `+faststart`.
- AAC-LC 192 kbps, 48 kHz stereo, -14 LUFS integrated, -1 dBTP.
- Frame 0 is the poster (`render.py --poster-at T`), because Slack, X, Discord and most players show frame 0 as the thumbnail. For looping vertical platforms (Reels, TikTok, Shorts) render with `--no-bake` and upload the poster JPG as the cover instead, otherwise every loop flashes the title for one frame. YouTube, Instagram, TikTok, Facebook and LinkedIn all accept an uploaded cover.
- Captions: `captions.srt` and `.vtt` from voice.py.

## Deliverables

Default for "make a video": one master in the format the user named (16:9 if unsure) plus the poster frame and a share text. Offer the other formats rather than rendering everything unasked, unless they said "for all platforms".

For "all platforms" or a launch: 16:9 master, 9:16 cut, 1:1 or 4:5 cut, poster per format, SRT if voiced, a 480 px GIF preview for docs and email, share text per platform (X short, LinkedIn a few lines, Instagram with line breaks and up to 5 relevant hashtags).

Name files `<slug>-16x9.mp4`, `<slug>-9x16.mp4`, `<slug>-1x1.mp4`, `<slug>-poster.jpg`, `<slug>.srt`, `share.txt`; add `-<lang>` for translations (`tidepool-9x16-he.mp4`).

A 6 s bumper is a cheap win for ads: hook, product, logo. Make it as a separate short timeline, not by trimming the long one.
