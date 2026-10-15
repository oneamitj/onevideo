# Storyboards by subject

Pick the archetype that matches the brief, then bend it. These are starting shapes, not templates. Durations assume a 20 s cut; scale for longer pieces by adding beats, not by slowing everything down.

## Contents
- Hooks that work
- 1. Physical product launch
- 2. App, SaaS or code project
- 3. Idea or concept explainer
- 4. Announcement or event
- 5. Short social ad (6 s and 15 s)
- 6. Data story
- 7. Brand story or manifesto
- 8. Tutorial or how-to
- 9. Place, venue or service
- 10. Personal: portfolio, thank-you, celebration
- Endings and calls to action
- Planning template

## Hooks that work

The first 2 seconds decide whether anyone keeps watching. Plan the hook before anything else and make it visual as well as verbal.

| pattern | example | when |
|---|---|---|
| The problem, shown | a phone at 1% battery, then the product | everyday products |
| Bold specific claim | "Brews tea in 4 minutes. On the move." | when the user gave a real number |
| Question | "Who carries the taxis?" | absurd or surprising ideas |
| Before / after | split screen wipes from messy to clean | tools, cleaning, design, fitness |
| Object in motion | the product drops into frame and lands on a beat | physical products |
| Number reveal | counter rolls to the key stat | data, milestones |
| Pattern interrupt | an unexpected visual (upside-down type, a hard cut to colour) | crowded feeds, playful tone |
| The result first | the finished output, then "how?" | apps, creative tools, recipes |

Avoid: logo first, "Introducing...", a slow fade from black, generic stock-like abstract motion.

## 1. Physical product launch

What viewers need: what it is, what it looks like, the one or two things that make it better, price/availability, where to get it.

| beat | time | content | visual ideas |
|---|---|---|---|
| Hook | 0 to 2.5 | the problem or the object in motion | product drops in, light sweep across it, macro detail |
| Reveal | 2.5 to 5.5 | name + one-line promise | 3D turntable or hero illustration, name in big type |
| Detail 1 | 5.5 to 8.5 | best feature, shown | callout line from the feature to a label, exploded view, cutaway |
| Detail 2 | 8.5 to 11.5 | second feature or material | material swatch, scale comparison, in-use silhouette |
| Proof / spec | 11.5 to 15 | real numbers only (capacity, weight, battery, price) | spec strip counting up, icons |
| CTA | 15 to 20 | name, price/date, URL | product + name lockup, sting on the beat |

Showing the product without photos (see visual-toolkit.md):
- Rotationally symmetric things (bottles, cups, lamps, cans, jars, candles, vases): 3D lathe in `product3d.js`.
- Boxy things (speakers, phones, boxes, books, chargers): rounded boxes in 3D or layered CSS/SVG.
- Anything organic or complex (shoes, clothing, food): stylised SVG illustration, silhouettes, or ask for photos. Real photos beat drawings for these.
- With user photos: cut out the background, place on a designed set, add shadow, parallax and macro crops.

Never show a feature, colour or accessory the user didn't describe.

## 2. App, SaaS or code project

Show the product working, not a landing page describing it.

| beat | time | content | visual ideas |
|---|---|---|---|
| Hook | 0 to 2.5 | the pain or the result | the messy "before", or the finished output |
| Reveal | 2.5 to 5 | name + what it does | logo lockup over the real UI |
| Flow 1 | 5 to 9 | entry and key action | cursor clicks, typing, drag and drop in a recreated UI |
| Flow 2 | 9 to 13 | the result | output appears item by item, success toast |
| Proof | 13 to 16 | real users/stars/numbers if given, or a second feature | counter, short quote only if real |
| CTA | 16 to 20 | URL, "free", platform badges given by the user | lockup |

From a codebase: read the main page, styles (exact colours, fonts), README and the main routes; reuse real components and copy. Skip build output, lock files, `.env*`, keys, credentials and anything gitignored for secrecy. Replace real user names, emails and data with plausible fictional stand-ins, and say so. From a URL: fetch it (render with the browser if it is a JS app), take copy, colours, fonts and screenshots; rebuild the key UI in HTML rather than panning over screenshots.

Code-centric pieces (libraries, CLIs, APIs): terminal typing with syntax colours, a diff that resolves, a benchmark bar race (real numbers only), the install command as the CTA.

## 3. Idea or concept explainer

| beat | time | content | visual ideas |
|---|---|---|---|
| Hook | 0 to 3 | the tension: what's broken or curious | a metaphor object, a contradiction in type |
| Insight | 3 to 7 | the idea in one sentence | kinetic type, one strong image |
| Mechanism | 7 to 13 | how it works, 2 or 3 steps | diagram that builds piece by piece, arrows drawing on |
| Example | 13 to 17 | one concrete case | a tiny story with a character icon |
| Takeaway | 17 to 20 | what to do or remember | single line, calm hold |

Metaphor beats abstraction: "a library card for your data" turns into a card being stamped. Diagrams should build in the order you'd explain them aloud. If there is a voiceover, the screen shows the keyword, not the sentence.

## 4. Announcement or event

| beat | content |
|---|---|
| Hook | the big news word ("We're hiring", "Doors open") or a countdown |
| What | the event/product/change in one line |
| When / where | date, time, place, as large type; a map pin drawing on (abstract map, no tile services) |
| Why come / what you get | 2 or 3 quick reasons |
| CTA | URL or "link in bio", date repeated |

Dates and times: format with `Intl.DateTimeFormat` for the video's language, and double-check them against the brief.

## 5. Short social ad

- 6 s bumper: product or result in the first second, one line, logo + CTA. Three scenes at most.
- 15 s: hook (0 to 2), problem/benefit (2 to 7), proof (7 to 11), CTA (11 to 15).
- Design for sound-off viewing: the story must work from text and picture alone. Burn in captions if there is voice.
- Vertical first for Reels, TikTok and Shorts; keep text in the safe area.

## 6. Data story

One number per scene, and say what it means. Count up only to numbers the user gave (or from data they provided), show the unit and the time period, and cite the source in small type if they gave one. Chart types: a bar growing with a counter, a line drawing on with an annotation at the turning point, a single big number with a comparison object ("the weight of 3 elephants") only if the comparison is accurate.

## 7. Brand story or manifesto

Kinetic typography carries it. Short lines (2 to 6 words), a strong typeface, rhythm locked to the music (cut on beats, one line per bar), a few textures or photographs if the user provides them, and a final line that lands on the sting. Restraint reads as confidence: fewer words, longer holds.

## 8. Tutorial or how-to

Number the steps, show each action (cursor, hand icon, or close-up), keep one action per scene, and recap at the end. Voiceover helps here; at 30 to 90 s it is often worth asking for. Put the step title on screen even with voice.

## 9. Place, venue or service

Restaurants, studios, shops, rentals, clinics. Lead with the experience (an atmosphere image, a signature dish, the view), then what makes it different, then practical info (address, hours, booking). Photos from the user matter most here; without them, use illustration and type, never stock photos presented as the real place.

## 10. Personal: portfolio, thank-you, celebration

Use the person's own words and images. Portfolio: 3 to 5 pieces, one per scene, name and role at the end. Thank-you or milestone: the number or moment first, then the people (as names, not faces, unless photos are given), then a warm closing line.

## Endings and calls to action

- The ending lands on the music's sting (scene `"music": "sting"` or the default ending), holds 2 to 3 s, and stays postable as a still.
- One CTA, not three. Use the exact URL or handle the user gave. If none, end on the name and the promise.
- Loopable endings (for feeds and website heroes): make the last frame lead back into the first.

## Planning template (plan.md)

```markdown
# <title>
Angle: <one sentence: the creative idea that makes this video specific>
Audience: <who> | Takeaway: <the one thing they remember> | Platform: <where> | Format: <16:9 + 9:16> | Length: <s>
Tone: <preset + freeform direction> | Music: <style, seed> | Voice: <none / lang + voice>
Facts allowed on screen: <list exactly what the user gave>
Assumptions: <defaults you chose and why>

| # | scene id | dur | energy | on-screen text (exact) | visual + motion | transition | sound |
|---|---|---|---|---|---|---|---|
| 1 | hook | 2.5 | 0.4 | "..." | ... | - | riser into reveal |
...
Poster frame: <scene + moment>
Share copy draft: <1 to 3 lines>
```
