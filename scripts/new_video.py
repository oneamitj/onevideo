#!/usr/bin/env python3
"""Scaffold a new video project.

  new_video.py OUT [--title "Tidepool launch"] [--format vertical] [--lang he]
               [--fonts "Inter" "Noto Sans Hebrew"] [--weights 400,700,800] [--3d]

Creates:
  OUT/comp/            the composition (index.html, runtime/, timeline.json, strings/, assets/)
  OUT/work/            scratch renders, stills and QA reports
Fonts come from Fontsource over the npm registry; if that is unreachable the page falls back
to system fonts (doctor.py lists them). --3d also fetches three.js and the product3d recipe.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import RTL_LANGS, SKILL_DIR, die, load_json, log, sync_mirrors, write_json  # noqa: E402

SCRIPT_FONT = {"he": "Noto Sans Hebrew", "ar": "Noto Sans Arabic", "fa": "Noto Sans Arabic", "ur": "Noto Sans Arabic",
               "hi": "Noto Sans Devanagari", "mr": "Noto Sans Devanagari", "ne": "Noto Sans Devanagari",
               "bn": "Noto Sans Bengali", "ta": "Noto Sans Tamil", "te": "Noto Sans Telugu", "th": "Noto Sans Thai",
               "ja": "Noto Sans JP", "zh": "Noto Sans SC", "ko": "Noto Sans KR", "ru": None, "el": None}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--title", default="Untitled video")
    ap.add_argument("--format", default="landscape")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--fonts", nargs="*", help="Google font families (default: Inter + a Noto font for the script)")
    ap.add_argument("--weights", default="400,600,800")
    ap.add_argument("--3d", dest="three", action="store_true", help="also fetch three.js + product3d.js")
    ap.add_argument("--force", action="store_true", help="overwrite an existing comp/")
    args = ap.parse_args()

    out = Path(args.out).resolve()
    comp = out / "comp"
    if comp.exists() and not args.force:
        die(f"{comp} exists (use --force to overwrite)")
    (out / "work").mkdir(parents=True, exist_ok=True)
    if comp.exists():
        shutil.rmtree(comp)
    shutil.copytree(SKILL_DIR / "assets" / "template", comp)
    shutil.copytree(SKILL_DIR / "assets" / "runtime", comp / "runtime")
    (comp / "assets" / "fonts").mkdir(parents=True, exist_ok=True)
    (comp / "assets" / "fonts" / "fonts.css").write_text("/* fonts: run fetch_assets.py fonts */\n")

    tl = load_json(comp / "timeline.json")
    tl["title"] = args.title
    tl["format"] = args.format
    tl["lang"] = args.lang
    base = args.lang.lower().split("-")[0]
    tl["voice"]["lang"] = "en-us" if base == "en" else args.lang
    write_json(comp / "timeline.json", tl)
    if base != "en":
        (comp / "strings" / "en.json").rename(comp / "strings" / f"{base}.json")
        html = (comp / "index.html").read_text(encoding="utf-8").replace('<html lang="en">', f'<html lang="{args.lang}"'
                                                                         + (' dir="rtl">' if base in RTL_LANGS else ">"))
        (comp / "index.html").write_text(html, encoding="utf-8")

    fonts = args.fonts if args.fonts is not None else ["Inter"] + ([SCRIPT_FONT[base]] if SCRIPT_FONT.get(base) else [])
    fetched = False
    if fonts:
        r = subprocess.run([sys.executable, str(SKILL_DIR / "scripts" / "fetch_assets.py"), "fonts", str(comp), *fonts,
                            "--weights", args.weights], capture_output=True, text=True)
        fetched = r.returncode == 0
        if not fetched:
            log("new_video: could not fetch fonts (offline?). The page will use system fonts; doctor.py lists them.")
            log("  " + (r.stderr.strip().splitlines() or [""])[-1])
    if args.three:
        r = subprocess.run([sys.executable, str(SKILL_DIR / "scripts" / "fetch_assets.py"), "npm", str(comp), "three",
                            "build/three.module.js", "build/three.core.js", "examples/jsm/environments/RoomEnvironment.js",
                            "examples/jsm/geometries/RoundedBoxGeometry.js"], capture_output=True, text=True)
        if r.returncode != 0:
            log("new_video: could not fetch three.js: " + (r.stderr.strip().splitlines() or [""])[-1])
        (comp / "assets" / "recipes").mkdir(parents=True, exist_ok=True)
        shutil.copy(SKILL_DIR / "assets" / "recipes" / "product3d.js", comp / "assets" / "recipes" / "product3d.js")
    sync_mirrors(comp)
    print(json.dumps({"comp": str(comp), "work": str(out / "work"), "fonts": fonts if fetched else [],
                      "three": bool(args.three), "next": [
                          "edit comp/timeline.json (scenes, music, voice) then: timeline.py comp --snap",
                          "write comp/index.html scenes + strings/<lang>.json",
                          "render.py comp --stills auto --sheet work/sheet.png   (look at it)",
                          "render.py comp --qa"]}, indent=2))


if __name__ == "__main__":
    main()
