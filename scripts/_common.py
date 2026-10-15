"""Shared helpers for onevideo scripts. Standard library only."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
FORMATS = {
    "landscape": (1920, 1080),
    "vertical": (1080, 1920),
    "square": (1080, 1080),
    "portrait": (1080, 1350),
    "wide": (2560, 1080),
}
RTL_LANGS = {"ar", "he", "iw", "fa", "ur", "yi", "ps", "sd", "ug", "dv", "ckb", "syr", "nqo", "ks"}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def die(msg, code=1):
    log("error: " + msg)
    sys.exit(code)


def format_size(fmt: str) -> tuple[int, int]:
    m = re.match(r"^(\d+)x(\d+)$", fmt or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    if fmt not in FORMATS:
        die(f"unknown format '{fmt}' (use {', '.join(FORMATS)} or WxH)")
    return FORMATS[fmt]


# ---------------------------------------------------------------- ffmpeg
def ffmpeg_bin() -> str | None:
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg  # pip install imageio-ffmpeg ships a static ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def need_ffmpeg() -> str:
    p = ffmpeg_bin()
    if not p:
        die("ffmpeg not found. Install it (apt/brew/winget install ffmpeg) or: pip install imageio-ffmpeg")
    return p


def media_duration(path: str | Path) -> float | None:
    """Duration in seconds via ffprobe, or by parsing `ffmpeg -i` when ffprobe is missing."""
    probe = shutil.which("ffprobe")
    if probe:
        r = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                           capture_output=True, text=True)
        try:
            return float(r.stdout.strip())
        except ValueError:
            pass
    ff = ffmpeg_bin()
    if not ff:
        return None
    r = subprocess.run([ff, "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
    if not m:
        return None
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


# -------------------------------------------------------------- timeline
def load_json(path: Path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as e:
        die(f"{path}: invalid JSON ({e})")


def write_json(path: Path, data) -> None:
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_timeline(comp: Path) -> dict:
    return load_json(Path(comp) / "timeline.json", {}) or {}


def normalize_timeline(tl: dict) -> dict:
    """Fill in scene starts and total duration. Returns the same dict."""
    t = 0.0
    for s in tl.get("scenes", []):
        if s.get("start") is None:
            s["start"] = round(t, 4)
        s["start"] = float(s["start"])
        s["dur"] = float(s["dur"])
        t = s["start"] + s["dur"]
    if tl.get("scenes"):
        tl["duration"] = round(max(s["start"] + s["dur"] for s in tl["scenes"]), 4)
    return tl


def scene_abs(tl: dict, ref: dict) -> float:
    """Absolute time for an item given as {t} or {scene, at}."""
    if ref.get("t") is not None:
        return float(ref["t"])
    sid = ref.get("scene")
    for s in tl.get("scenes", []):
        if s["id"] == sid:
            return float(s["start"]) + float(ref.get("at", 0))
    if sid:
        die(f"unknown scene '{sid}' referenced in timeline")
    return float(ref.get("at", 0))


def sync_mirrors(comp: Path) -> None:
    """Write the .js mirrors the page loads (works from file:// as well as http://).

    timeline.json -> timeline.js (window.TIMELINE)
    strings/*.json -> strings.js (window.STRINGS)
    captions.json -> captions.js (window.CAPTIONS)
    """
    comp = Path(comp)
    tl = load_json(comp / "timeline.json")
    if tl is not None:
        normalize_timeline(tl)
        (comp / "timeline.js").write_text("window.TIMELINE = " + json.dumps(tl, ensure_ascii=False) + ";\n", encoding="utf-8")
    sdir = comp / "strings"
    table = None
    if sdir.is_dir():
        table = {}
        for f in sorted(sdir.glob("*.json")):
            table[f.stem] = load_json(f, {})
    (comp / "strings.js").write_text("window.STRINGS = " + json.dumps(table, ensure_ascii=False) + ";\n", encoding="utf-8")
    caps = load_json(comp / "captions.json")
    (comp / "captions.js").write_text("window.CAPTIONS = " + json.dumps(caps, ensure_ascii=False) + ";\n", encoding="utf-8")


# --------------------------------------------------------------- browser
BROWSER_ARGS = [
    "--disable-dev-shm-usage",
    "--hide-scrollbars",
    "--force-color-profile=srgb",
    "--font-render-hinting=none",
    "--disable-lcd-text",
    "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist",
    "--mute-audio",
    "--autoplay-policy=no-user-gesture-required",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
]


def browser_candidates() -> list[str]:
    env = os.environ.get("ONEVIDEO_BROWSER")
    c = [env] if env else []
    c += [
        "/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
        "/snap/bin/chromium", "/usr/bin/microsoft-edge",
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ]
    return [p for p in c if p and os.path.exists(p)]


def launch_browser(pw, extra_args=()):
    """Launch a headless Chromium. Order: ONEVIDEO_BROWSER, Playwright's own build, installed Chrome/Edge."""
    args = BROWSER_ARGS + list(extra_args)
    errors = []
    env = os.environ.get("ONEVIDEO_BROWSER")
    if env:
        try:
            return pw.chromium.launch(executable_path=env, headless=True, args=args)
        except Exception as e:
            errors.append(f"ONEVIDEO_BROWSER: {str(e).splitlines()[0]}")
    try:
        return pw.chromium.launch(headless=True, args=args)
    except Exception as e:
        errors.append(f"playwright chromium: {str(e).splitlines()[0]}")
    for ch in ("chrome", "msedge", "chromium"):
        try:
            return pw.chromium.launch(channel=ch, headless=True, args=args)
        except Exception as e:
            errors.append(f"channel {ch}: {str(e).splitlines()[0]}")
    for path in browser_candidates():
        try:
            return pw.chromium.launch(executable_path=path, headless=True, args=args)
        except Exception as e:
            errors.append(f"{path}: {str(e).splitlines()[0]}")
    die("no usable Chromium browser.\n  " + "\n  ".join(errors) +
        "\nFix: `python3 -m playwright install chromium`, install Google Chrome, or set ONEVIDEO_BROWSER=/path/to/chrome")


def import_playwright():
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        return sync_playwright
    except ImportError:
        die("Python Playwright is missing. Install: pip install playwright  (then, if no Chrome is installed: python3 -m playwright install chromium)")
