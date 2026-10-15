#!/usr/bin/env python3
"""Check what this machine can do before making a video. Prints JSON to stdout and a
short human summary to stderr.

  doctor.py            full check (launches the browser once, ~5 s)
  doctor.py --quick    skip the browser launch and network probes
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import ffmpeg_bin, log  # noqa: E402

SCRIPT_FONTS = {
    "hebrew": ["Noto Sans Hebrew", "Noto Serif Hebrew", "Rubik", "Heebo", "Assistant", "Arial"],
    "arabic": ["Noto Sans Arabic", "Noto Naskh Arabic", "Cairo", "Tajawal", "Amiri"],
    "cjk": ["Noto Sans CJK", "Noto Sans JP", "Noto Sans SC", "Source Han", "IPAGothic", "PingFang", "Hiragino"],
    "devanagari": ["Noto Sans Devanagari", "Mukta", "Hind"],
    "thai": ["Noto Sans Thai", "Sarabun", "Prompt"],
}


def has_mod(name):
    try:
        importlib.import_module(name)
        return True
    except Exception:
        return False


def check_ffmpeg():
    ff = ffmpeg_bin()
    if not ff:
        return {"ok": False, "fix": "install ffmpeg (apt/brew/winget) or pip install imageio-ffmpeg"}
    v = subprocess.run([ff, "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    enc = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    flt = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    return {"ok": "libx264" in enc, "path": ff, "version": v, "libx264": "libx264" in enc, "loudnorm": "loudnorm" in flt,
            **({} if "libx264" in enc else {"fix": "this ffmpeg lacks libx264; pip install imageio-ffmpeg gives one that has it"})}


def check_browser():
    if not has_mod("playwright"):
        return {"ok": False, "fix": "pip install playwright  (then python3 -m playwright install chromium if no Chrome is installed)"}
    code = r"""
import sys, json
sys.path.insert(0, %r)
from _common import launch_browser
from playwright.sync_api import sync_playwright
with sync_playwright() as pw:
    b = launch_browser(pw)
    p = b.new_page()
    gl = p.evaluate("(() => { const c = document.createElement('canvas'); const g = c.getContext('webgl2') || c.getContext('webgl'); if (!g) return null; const d = g.getExtension('WEBGL_debug_renderer_info'); return d ? g.getParameter(d.UNMASKED_RENDERER_WEBGL) : 'webgl'; })()")
    seg = p.evaluate("typeof Intl.Segmenter === 'function'")
    print(json.dumps({"ok": True, "version": b.version, "webgl": gl, "segmenter": seg}))
    b.close()
""" % str(Path(__file__).resolve().parent)
    try:
        r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=90)
        if r.returncode == 0 and r.stdout.strip():
            info = json.loads(r.stdout.strip().splitlines()[-1])
            gl = (info.get("webgl") or "").lower()
            info["gpu"] = bool(gl) and not any(x in gl for x in ("swiftshader", "llvmpipe", "software"))
            return info
        return {"ok": False, "error": (r.stderr or r.stdout).strip().splitlines()[-1:] or ["unknown"],
                "fix": "python3 -m playwright install chromium, install Google Chrome, or set ONEVIDEO_BROWSER=/path/to/chrome"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "browser launch timed out"}


def check_fonts():
    out = {"system": platform.system()}
    if shutil.which("fc-list"):
        fams = subprocess.run(["fc-list", ":", "family"], capture_output=True, text=True).stdout
        out["count"] = len(set(fams.splitlines()))
        out["scripts"] = {k: [f for f in v if f.lower() in fams.lower()] for k, v in SCRIPT_FONTS.items()}
    else:
        out["note"] = "macOS and Windows ship fonts for most scripts; fetch_assets.py fonts adds web fonts"
    return out


def check_voice():
    cache = Path(os.environ.get("ONEVIDEO_CACHE", Path.home() / ".cache" / "onevideo")) / "kokoro"
    return {
        "kokoro": {"installed": has_mod("kokoro_onnx"), "models_cached": (cache / "kokoro-v1.0.fp16.onnx").exists(),
                   "languages": "en-us, en-gb, es, fr, hi, it, pt-br, ja, zh", "install": "pip install kokoro-onnx"},
        "espeak": bool(shutil.which("espeak-ng") or shutil.which("espeak")),
        "macos_say": platform.system() == "Darwin" and bool(shutil.which("say")),
        "windows_sapi": platform.system() == "Windows",
        "piper": has_mod("piper"),
    }


def probe(url):
    """Tiny ranged GET (some proxies refuse HEAD)."""
    if shutil.which("curl"):
        r = subprocess.run(["curl", "-sfL", "-r", "0-0", "--max-time", "8", "-o", os.devnull, url], capture_output=True)
        return r.returncode == 0
    try:
        req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status < 400
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    rep = {
        "python": platform.python_version(), "os": f"{platform.system()} {platform.machine()}", "cpus": os.cpu_count(),
        "modules": {m: has_mod(m) for m in ("numpy", "scipy", "PIL", "playwright", "kokoro_onnx")},
        "ffmpeg": check_ffmpeg(), "fonts": check_fonts(), "voice": check_voice(),
    }
    rep["workers"] = max(1, min(4, (os.cpu_count() or 2) // 2))
    if not args.quick:
        rep["browser"] = check_browser()
        rep["network"] = {name: probe(u) for name, u in {
            "npm_registry": "https://registry.npmjs.org/three", "pypi": "https://pypi.org/simple/kokoro-onnx/",
            "github_releases": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.0.bin",
            "huggingface": "https://huggingface.co/api/models?limit=1", "google_fonts": "https://fonts.googleapis.com/css2?family=Inter",
            "openverse": "https://api.openverse.org/v1/images/?q=tea&page_size=1"}.items()}
    need = []
    if not rep["modules"]["numpy"]:
        need.append("pip install numpy")
    if not rep["ffmpeg"].get("ok"):
        need.append(rep["ffmpeg"].get("fix", "install ffmpeg"))
    if not args.quick and not rep["browser"].get("ok"):
        need.append(rep["browser"].get("fix", "install a Chromium browser"))
    rep["ready"] = not need
    rep["fix"] = need
    tips = []
    if not rep["modules"]["scipy"]:
        tips.append("pip install scipy: nicer, faster music synthesis")
    if not rep["voice"]["kokoro"]["installed"]:
        tips.append("pip install kokoro-onnx: free natural voiceover in 9 languages")
    if not args.quick and rep["browser"].get("ok") and not rep["browser"].get("gpu"):
        tips.append("no GPU in the browser: keep 3D canvases small, prefer 2D/CSS motion")
    rep["tips"] = tips
    print(json.dumps(rep, indent=2))
    log(f"doctor: {'READY' if rep['ready'] else 'NOT READY'}  python {rep['python']}, {rep['cpus']} cpus, "
        f"ffmpeg {'ok' if rep['ffmpeg'].get('ok') else 'missing'}, browser {'ok' if args.quick or rep['browser'].get('ok') else 'missing'}"
        + (f", net: {', '.join(k for k, v in rep.get('network', {}).items() if v) or 'none'}" if not args.quick else ""))
    for x in need:
        log("  fix: " + x)
    for x in tips:
        log("  tip: " + x)


if __name__ == "__main__":
    main()
