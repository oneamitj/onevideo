#!/usr/bin/env python3
"""Validate a composition timeline and snap scene cuts onto the musical beat grid.

  timeline.py COMP              validate, print the scene table, write timeline.js
  timeline.py COMP --snap       pick a tempo in the style's range (unless music.bpm is set)
                                and resize scenes so every cut lands exactly on a beat
  timeline.py COMP --snap --bpm 118

The timeline (COMP/timeline.json) is the single source of truth for scene timing.
stage.js, music.py and voice.py all read it, which keeps picture and sound in sync.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import die, load_timeline, log, normalize_timeline, scene_abs, sync_mirrors, write_json  # noqa: E402

STYLE_BPM = {
    "uplifting": (100, 124), "tech": (116, 128), "cinematic": (78, 100), "lofi": (72, 88), "ambient": (68, 88),
    "chiptune": (124, 150), "acoustic": (90, 112), "hype": (136, 150), "piano": (68, 92), "none": (90, 120),
}
TRANSITIONS = {"cut", "fade", "dip", "slide", "push", "wipe", "zoom", "blur", "iris", "flash", "whip"}


def check(tl: dict, comp: Path) -> list[str]:
    probs = []
    scenes = tl.get("scenes") or []
    if not scenes:
        probs.append("error: no scenes")
    ids = [s.get("id") for s in scenes]
    for i in set(ids):
        if ids.count(i) > 1:
            probs.append(f"error: duplicate scene id '{i}'")
    html = (comp / "index.html").read_text(encoding="utf-8") if (comp / "index.html").exists() else ""
    for s in scenes:
        sid = s.get("id")
        if not sid or not re.match(r"^[A-Za-z][\w-]*$", sid):
            probs.append(f"error: bad scene id {sid!r} (letters, digits, - or _)")
        if html and not re.search(r'id=["\']' + re.escape(sid or "") + r'["\']', html):
            probs.append(f"warn: scene '{sid}' has no <section class=\"scene\" id=\"{sid}\"> in index.html yet")
        d = float(s.get("dur", 0))
        if d < 0.8:
            probs.append(f"warn: scene '{sid}' is {d:.2f}s; under ~0.8s nothing can be read")
        if d > 9:
            probs.append(f"warn: scene '{sid}' is {d:.1f}s; long holds drag unless the scene has motion")
        tr = s.get("transition")
        if tr:
            typ = tr if isinstance(tr, str) else tr.get("type", "fade")
            if typ not in TRANSITIONS:
                probs.append(f"error: scene '{sid}' transition '{typ}' unknown ({', '.join(sorted(TRANSITIONS))})")
            td = 0.6 if isinstance(tr, str) else float(tr.get("dur", 0.6))
            if td > d * 0.6:
                probs.append(f"warn: scene '{sid}' transition ({td}s) eats most of the scene ({d}s)")
        e = s.get("energy")
        if e is not None and not (0 <= float(e) <= 1):
            probs.append(f"error: scene '{sid}' energy must be 0..1")
    for x in tl.get("sfx", []):
        try:
            scene_abs(tl, x)
        except SystemExit:
            probs.append(f"error: sfx {x} references an unknown scene")
    v = tl.get("voice") or {}
    for line in v.get("lines", []):
        if line.get("scene") and line["scene"] not in ids:
            probs.append(f"error: voice line {line.get('id')} references unknown scene '{line['scene']}'")
    dur = tl.get("duration", 0)
    if dur > 90:
        probs.append(f"warn: {dur:.0f}s is long for a social video; most land between 15 and 60s")
    style = (tl.get("music") or {}).get("style")
    if style and style not in STYLE_BPM:
        probs.append(f"error: music.style '{style}' unknown ({', '.join(STYLE_BPM)})")
    return probs


def snap(tl: dict, bpm_arg: str | None) -> dict:
    music = tl.setdefault("music", {})
    style = music.get("style", "uplifting")
    lo, hi = STYLE_BPM.get(style, (90, 128))
    fixed = bpm_arg if bpm_arg not in (None, "auto") else music.get("bpm") if bpm_arg != "auto" else None
    durs = [float(s["dur"]) for s in tl["scenes"]]
    target = sum(durs)
    cands = [float(fixed)] if fixed else [lo + i * 0.5 for i in range(int((hi - lo) * 2) + 1)]
    best = None
    mid = (lo + hi) / 2
    for bpm in cands:
        beat = 60.0 / bpm
        ks = [max(2, round(d / beat)) for d in durs]
        err = sum(abs(k * beat - d) for k, d in zip(ks, durs))
        total_err = abs(sum(ks) * beat - target)
        # prefer cuts on bar lines for the first and last cut, and a tempo near the middle of the range
        bar_pen = sum(0.02 for k in ks[:1] + ks[-1:] if k % 2)
        cost = err + 0.5 * total_err + 0.004 * abs(bpm - mid) + bar_pen
        if best is None or cost < best[0]:
            best = (cost, bpm, ks)
    _, bpm, ks = best
    beat = 60.0 / bpm
    t = 0.0
    for s, k in zip(tl["scenes"], ks):
        s["start"] = round(t, 4)
        s["dur"] = round(k * beat, 4)
        s["beats"] = k
        t += k * beat
    music["bpm"] = bpm
    tl["duration"] = round(t, 4)
    return tl


def table(tl: dict) -> str:
    bpm = (tl.get("music") or {}).get("bpm")
    beat = 60.0 / bpm if bpm else None
    rows = [f"{'scene':<14}{'start':>8}{'dur':>8}{'beat#':>7}  transition / energy / music"]
    for s in tl["scenes"]:
        tr = s.get("transition", "cut")
        trs = tr if isinstance(tr, str) else f"{tr.get('type')} {tr.get('dur', '')}"
        b = f"{s['start'] / beat:6.1f}" if beat else "     -"
        rows.append(f"{s['id']:<14}{s['start']:8.2f}{s['dur']:8.2f}{b:>7}  {trs} / {s.get('energy', '-')} / {s.get('music', '')}")
    rows.append(f"total {tl.get('duration', 0):.2f}s" + (f" at {bpm} bpm" if bpm else ""))
    return "\n".join(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comp")
    ap.add_argument("--snap", action="store_true", help="snap scene cuts to the beat grid")
    ap.add_argument("--bpm", help="tempo to snap to, or 'auto'")
    args = ap.parse_args()
    comp = Path(args.comp)
    tl = load_timeline(comp)
    if not tl:
        die(f"{comp}/timeline.json missing or empty")
    normalize_timeline(tl)
    if args.snap:
        snap(tl, args.bpm)
        write_json(comp / "timeline.json", tl)
    probs = check(tl, comp)
    sync_mirrors(comp)
    log(table(tl))
    for p in probs:
        log(p)
    print(json.dumps({"ok": not any(p.startswith("error") for p in probs), "duration": tl.get("duration"),
                      "bpm": (tl.get("music") or {}).get("bpm"), "problems": probs}, indent=2))
    if any(p.startswith("error") for p in probs):
        sys.exit(2)


if __name__ == "__main__":
    main()
