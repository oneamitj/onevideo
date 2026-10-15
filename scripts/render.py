#!/usr/bin/env python3
"""Render a onevideo composition (a folder with index.html + stage.js).

Modes (pick one; default is a full render):
  render.py COMP --out video.mp4 [--format vertical] [--lang he] [--quality draft|final] [--poster-at 4.2]
  render.py COMP --stills auto --sheet sheet.png      contact sheet of key moments (look at it!)
  render.py COMP --stills 1.2,3.5 --frames-dir shots  full-size PNGs at given times
  render.py COMP --qa [--strict]                      readability / layout / contrast report
  render.py COMP --cues                               write COMP/cues.json (sfx cues from the animation)
  render.py COMP --serve                              live preview server (open the printed URL)

Needs: Python 3.9+, `pip install playwright pillow`, a Chromium browser, ffmpeg.
Every frame is rendered by calling window.__stage.seek(t) then screenshotting,
so the output is frame-exact and independent of machine speed.
"""
from __future__ import annotations

import argparse
import base64
import functools
import http.server
import io
import json
import math
import mimetypes
import multiprocessing as mp
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (die, format_size, import_playwright, launch_browser, log, media_duration,  # noqa: E402
                     need_ffmpeg, sync_mirrors, write_json)

mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")
mimetypes.add_type("application/wasm", ".wasm")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("model/gltf-binary", ".glb")


# ----------------------------------------------------------------- server
class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def start_server(root: Path, port: int = 0):
    handler = functools.partial(QuietHandler, directory=str(root))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    return httpd, httpd.server_address[1]


# ------------------------------------------------------------------- page
def page_url(port, args):
    q = ["render=1", f"format={args.format}"] if args.format else ["render=1"]
    if args.lang:
        q.append(f"lang={args.lang}")
    if args.safe:
        q.append(f"safe={args.safe}")
    if args.fps:
        q.append(f"fps={args.fps}")
    for kv in getattr(args, "param", None) or []:
        q.append(kv)  # free-form k=v for the page (variants, A/B tests): read with new URLSearchParams(location.search)
    return f"http://127.0.0.1:{port}/index.html?" + "&".join(q)


def open_page(pw, url, size, scale=1.0, log_console=True):
    browser = launch_browser(pw)
    ctx = browser.new_context(viewport={"width": size[0], "height": size[1]}, device_scale_factor=scale)
    page = ctx.new_page()
    problems = []
    page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
    page.on("requestfailed", lambda r: problems.append(f"failed to load {r.url.split('/', 3)[-1]} ({r.failure})"))

    def on_resp(r):
        if r.status >= 400:
            problems.append(f"HTTP {r.status} for {r.url.split('/', 3)[-1]}")
    page.on("response", on_resp)
    if log_console:
        page.on("console", lambda m: m.type in ("error",) and problems.append(f"console: {m.text}"))
    page.goto(url, wait_until="load", timeout=120_000)
    try:
        page.wait_for_function("window.__stage && window.__stage.isReady === true", timeout=120_000)
    except Exception:
        die("the page never became ready. Is stage.js loaded and Stage.start() called?\n  " + "\n  ".join(problems[:10]))
    info = page.evaluate("window.__stage.info()")
    return browser, page, info, problems


def stage_size(page):
    return page.evaluate("[window.__stage.info().width, window.__stage.info().height]")


class Grabber:
    """Fast viewport capture through CDP, falling back to page.screenshot."""

    def __init__(self, page, fmt="jpeg", quality=92):
        self.page, self.fmt, self.q = page, fmt, quality
        self.cdp = None
        try:
            self.cdp = page.context.new_cdp_session(page)
            self.params = {"format": fmt, "captureBeyondViewport": False, "optimizeForSpeed": True}
            if fmt == "jpeg":
                self.params["quality"] = quality
            self.cdp.send("Page.captureScreenshot", self.params)
        except Exception:
            try:
                self.params.pop("optimizeForSpeed", None)
                self.cdp.send("Page.captureScreenshot", self.params)
            except Exception:
                self.cdp = None

    def __call__(self) -> bytes:
        if self.cdp:
            return base64.b64decode(self.cdp.send("Page.captureScreenshot", self.params)["data"])
        kw = {"type": self.fmt}
        if self.fmt == "jpeg":
            kw["quality"] = self.q
        return self.page.screenshot(**kw)


# ----------------------------------------------------------------- render
def encoder_cmd(ff, fps, out, fmt, quality, out_size=None):
    inp = ["-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg" if fmt == "jpeg" else "png", "-i", "-"]
    vf = "scale=in_range=full:in_color_matrix=bt601:out_range=tv:out_color_matrix=bt709" if fmt == "jpeg" else \
        "scale=out_range=tv:out_color_matrix=bt709"
    if out_size:
        vf = vf.replace("scale=", f"scale={out_size[0]}:{out_size[1]}:flags=lanczos:", 1)
    vf += ",format=yuv420p"
    preset, crf = ("veryfast", "23") if quality == "draft" else ("medium", "17")
    return [ff, "-y", "-hide_banner", "-loglevel", "error", *inp, "-vf", vf, "-c:v", "libx264", "-preset", preset,
            "-crf", crf, "-profile:v", "high", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
            "-colorspace", "bt709", "-g", str(int(fps * 2)), "-r", str(fps), "-movflags", "+faststart", str(out)]


def render_chunk(job):
    """Worker: render frames [a, b) into one MP4 segment."""
    (url, size, scale, fps, a, b, seg, fmt, quality, poster_at, wid, no_bake) = job
    sync_playwright = import_playwright()
    ff = need_ffmpeg()
    out_size = None
    with sync_playwright() as pw:
        browser, page, info, problems = open_page(pw, url, size, scale)
        if info["errors"]:
            browser.close()
            return {"error": info["errors"]}
        grab = Grabber(page, fmt, 92 if quality == "final" else 80)
        proc = subprocess.Popen(encoder_cmd(ff, fps, seg, fmt, quality, out_size), stdin=subprocess.PIPE)
        t0 = time.time()
        for f in range(a, b):
            t = f / fps
            if f == 0 and poster_at is not None and not no_bake:
                t = poster_at
            page.evaluate("t => window.__stage.seek(t)", t)
            proc.stdin.write(grab())
            if wid == 0 and f > a and ((f - a) == 12 or (f - a) % max(1, int(fps * 3)) == 0):
                el = time.time() - t0
                rate = (f - a) / el
                log(f"  frame {f - a}/{b - a} of chunk, {rate:.1f} fps, about {max(0, (b - f) / rate):.0f}s left")
        proc.stdin.close()
        proc.wait()
        browser.close()
        if proc.returncode != 0:
            return {"error": [f"ffmpeg failed for segment {seg}"]}
        return {"ok": True, "frames": b - a, "secs": time.time() - t0, "problems": problems[:20]}


def do_render(args, comp, port, info):
    ff = need_ffmpeg()
    fps = int(round(info["fps"]))
    total = int(round(info["duration"] * fps))
    if total <= 0:
        die("timeline has zero duration")
    size = (info["width"], info["height"])
    scale = 0.5 if args.quality == "draft" else 1.0
    fmt = "jpeg"
    workers = args.workers or max(1, min(4, (os.cpu_count() or 2) // 2))
    workers = min(workers, max(1, total // 30))
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="onevideo-"))
    url = page_url(port, args)
    bounds = [round(i * total / workers) for i in range(workers + 1)]
    jobs = [(url, size, scale, fps, bounds[i], bounds[i + 1], str(tmp / f"seg{i:03d}.mp4"), fmt, args.quality,
             args.poster_at, i, args.no_bake) for i in range(workers)]
    log(f"render: {total} frames @ {fps} fps, {size[0]}x{size[1]}{' (draft, half size)' if scale < 1 else ''}, {workers} worker(s)")
    t0 = time.time()
    if workers == 1:
        results = [render_chunk(jobs[0])]
    else:
        ctx = mp.get_context("spawn")
        with ctx.Pool(workers) as pool:
            results = pool.map(render_chunk, jobs)
    for r in results:
        if r.get("error"):
            die("render failed:\n  " + "\n  ".join(r["error"]))
    probs = sorted({p for r in results for p in r.get("problems", [])})
    if probs:
        log("warnings from the page:\n  " + "\n  ".join(probs[:15]))
    segs = [j[6] for j in jobs]
    if len(segs) == 1:
        shutil.move(segs[0], out)
    else:
        lst = tmp / "list.txt"
        lst.write_text("".join(f"file '{s}'\n" for s in segs))
        r = subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                            "-c", "copy", "-movflags", "+faststart", str(out)])
        if r.returncode != 0:
            die("ffmpeg concat failed")
    shutil.rmtree(tmp, ignore_errors=True)
    dt = time.time() - t0
    dur = media_duration(out)
    log(f"render: wrote {out} ({dur:.2f}s video) in {dt:.1f}s")
    result = {"video": str(out), "duration": dur, "frames": total, "fps": fps, "width": int(size[0] * scale),
              "height": int(size[1] * scale), "seconds": round(dt, 1)}
    flashes = flash_check(out, fps)
    if flashes:
        result["flash_warnings"] = flashes
        log("WARNING possible flashing (more than 3 big luminance flips per second) at: " + ", ".join(f"{x:.1f}s" for x in flashes))
    if args.poster_at is not None:
        poster = out.with_suffix(".jpg") if not args.poster else Path(args.poster)
        poster.parent.mkdir(parents=True, exist_ok=True)
        ss = [] if not args.no_bake else ["-ss", f"{args.poster_at:.3f}"]
        subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", *ss, "-i", str(out), "-frames:v", "1", "-q:v", "2", str(poster)])
        result["poster"] = str(poster)
        result["poster_baked_as_frame0"] = not args.no_bake
    print(json.dumps(result, indent=2))


def flash_check(video, fps):
    """WCAG 2.3.1-style check: >3 large opposing luminance changes within any 1 s window."""
    try:
        import numpy as np
    except ImportError:
        return []
    ff = need_ffmpeg()
    w, h = 32, 18
    r = subprocess.run([ff, "-v", "error", "-i", str(video), "-vf", f"scale={w}:{h},format=gray", "-f", "rawvideo", "-"],
                       capture_output=True)
    if r.returncode != 0 or not r.stdout:
        return []
    frames = np.frombuffer(r.stdout, dtype=np.uint8).reshape(-1, h * w).astype(np.float32) / 255.0
    lum = (frames ** 2.2).mean(axis=1)  # rough relative luminance
    d = np.diff(lum)
    big = np.where(np.abs(d) > 0.1)[0]
    flips, last_sign = [], 0
    for i in big:
        s = np.sign(d[i])
        darker = min(lum[i], lum[i + 1])
        if s != last_sign and darker < 0.8:
            flips.append(i / fps)
            last_sign = s
    warn = []
    for i, t in enumerate(flips):
        window = [x for x in flips[i:] if x - t < 1.0]
        if len(window) >= 7:  # 3 flashes = ~6-7 opposing changes
            if not warn or t - warn[-1] > 1.0:
                warn.append(t)
    return warn


# ----------------------------------------------------------------- stills
def auto_times(info, n_max=24):
    times = []
    for s in info["scenes"]:
        tr = s.get("transition") or {}
        if tr.get("type", "cut") != "cut" and tr.get("dur"):
            times.append((s["id"] + " (transition)", s["start"] + tr["dur"] * 0.5))
        times.append((s["id"], s["start"] + s["dur"] * 0.62))
    times.append(("end", max(0, info["duration"] - 1 / info["fps"])))
    return times[:n_max]


def do_stills(args, page, info):
    from PIL import Image, ImageDraw, ImageFont
    grab = Grabber(page, "png")
    if args.stills == "auto":
        times = auto_times(info)
    else:
        times = []
        for x in args.stills.split(","):
            x = x.strip()
            if x:
                t = float(x)
                sid = next((s["id"] for s in reversed(info["scenes"]) if s["start"] <= t), "")
                times.append((sid, t))
    shots = []
    for label, t in times:
        page.evaluate("t => window.__stage.seek(t)", t)
        png = grab()
        img = Image.open(io.BytesIO(png)).convert("RGB")
        shots.append((label, t, img))
        if args.frames_dir:
            d = Path(args.frames_dir)
            d.mkdir(parents=True, exist_ok=True)
            img.save(d / f"t{t:07.3f}.png")
    out = {"stills": [{"label": l, "t": round(t, 3)} for l, t, _ in shots]}
    if args.sheet or not args.frames_dir:
        sheet_path = Path(args.sheet or "contact-sheet.png")
        W, H = info["width"], info["height"]
        tw = 560 if W >= H else 300
        th = int(tw * H / W)
        cols = 4 if W >= H else 6
        cols = min(cols, len(shots))
        rows = math.ceil(len(shots) / cols)
        bar = 34
        sheet = Image.new("RGB", (cols * tw + (cols + 1) * 12, rows * (th + bar) + (rows + 1) * 12), (24, 24, 28))
        try:
            font = ImageFont.truetype("DejaVuSans.ttf", 17)
        except Exception:
            font = ImageFont.load_default()
        dr = ImageDraw.Draw(sheet)
        for i, (label, t, img) in enumerate(shots):
            r, c = divmod(i, cols)
            x, y = 12 + c * (tw + 12), 12 + r * (th + bar + 12)
            sheet.paste(img.resize((tw, th), Image.LANCZOS), (x, y + bar))
            dr.text((x + 4, y + 7), f"{t:6.2f}s  {label}", fill=(235, 235, 240), font=font)
        sheet.save(sheet_path)
        out["sheet"] = str(sheet_path.resolve())
    print(json.dumps(out, indent=2))


# --------------------------------------------------------------------- qa
def lum(c):
    def ch(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])


def contrast(l1, l2):
    a, b = max(l1, l2), min(l1, l2)
    return (a + 0.05) / (b + 0.05)


def transition_windows(info):
    """Per scene: time ranges where the scene is entering or leaving (not readable as 'settled')."""
    win = {}
    sc = info["scenes"]
    for i, s in enumerate(sc):
        w = []
        tr = s.get("transition") or {}
        if i > 0 and tr.get("type", "cut") != "cut":
            w.append((s["start"], s["start"] + tr.get("dur", 0)))
        if i + 1 < len(sc):
            n = sc[i + 1]
            ntr = n.get("transition") or {}
            typ, d = ntr.get("type", "cut"), ntr.get("dur", 0)
            if typ == "dip":
                w.append((n["start"] - d / 2, n["start"]))
            elif typ not in ("cut", "flash"):
                w.append((n["start"], n["start"] + d))
        win[s["id"]] = w
    return win


def do_qa(args, page, info):
    from PIL import Image
    import numpy as np
    U = min(info["width"], info["height"]) / 100
    step = args.qa_step
    dur = info["duration"]
    n = int(dur / step) + 1
    tw = transition_windows(info)
    in_tr = lambda scene, t: any(a <= t < b for a, b in tw.get(scene, []))  # noqa: E731
    max_speed = 0.06 * min(info["width"], info["height"])  # px/s a reader can still follow
    samples = {}  # id -> list of (t, block, speed)
    prev = {}
    overl = set()
    issues = []
    page.evaluate("window.__onevideoQA = true")  # heavy canvas/WebGL drawing can be skipped while sampling text layout
    for i in range(n):
        t = min(i * step, dur - 1e-3)
        page.evaluate("t => window.__stage.seek(t)", t)
        pr = page.evaluate("window.__stage.probe()")
        cur = {}
        for b in pr["blocks"]:
            cur[b["id"]] = b
            p = prev.get(b["id"])
            if p is None:
                speed = 1e9
            else:
                d = max(abs(b["x"] - p["x"]), abs(b["y"] - p["y"]), abs(b["w"] - p["w"]) / 2, abs(b["h"] - p["h"]) / 2)
                speed = d / step
            samples.setdefault(b["id"], []).append((t, b, speed))
        # overlaps: same scene, both readable, outside transitions
        vis = [b for b in pr["blocks"] if b["opacity"] >= 0.6 and not in_tr(b["scene"], t)]
        for x in range(len(vis)):
            for y in range(x + 1, len(vis)):
                a, b = vis[x], vis[y]
                caps = "captions" in a["lint"] + b["lint"]
                if (a["scene"] != b["scene"] and not caps) or "overlap-ok" in a["lint"] + b["lint"]:
                    continue
                ix = max(0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
                iy = max(0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
                small = min(a["w"] * a["h"], b["w"] * b["h"]) or 1
                if ix * iy / small > 0.12:
                    overl.add((a["id"], b["id"], round(t, 2)))
        prev = cur

    stats = {}
    for bid, rows in samples.items():
        peak = max(r[1]["opacity"] for r in rows)
        s = {"block": rows[-1][1], "settled": 0.0, "best_t": None, "unsafe": False, "clipped": False,
             "overflow": False, "tiny": False}
        best_score = -1
        for t, b, speed in rows:
            settled = (b["opacity"] >= 0.92 * peak and b["opacity"] >= 0.25 and not b["typing"] and speed <= max_speed
                       and b["inStage"] and not in_tr(b["scene"], t))
            if settled:
                s["settled"] += step
                if b["opacity"] > best_score:
                    best_score, s["best_t"] = b["opacity"], t
                if not b["safe"] and "decor" not in b["lint"]:
                    s["unsafe"] = True
                if b["overflow"]:
                    s["overflow"] = True
                if b["size"] < 1.9 * U and "small-ok" not in b["lint"]:
                    s["tiny"] = True
            if b["opacity"] >= 0.5 and not b["inStage"] and speed <= max_speed and not in_tr(b["scene"], t):
                s["clipped"] = True
        stats[bid] = s

    # reading time
    for bid, s in stats.items():
        b = s["block"]
        if "captions" in b["lint"] or "noread" in b["lint"] or not b["words"]:
            continue
        need = 0.8 if b["words"] <= 3 else max(1.2, 0.3 * b["words"])
        if s["settled"] + 1e-6 < need * 0.9:
            issues.append({"level": "warn", "kind": "reading-time", "scene": b["scene"], "el": b["tag"], "text": b["text"],
                           "settled": round(s["settled"], 2), "needs": round(need, 2),
                           "fix": "hold this line longer (or cut words); fast-in, then hold"})
        if s["clipped"]:
            issues.append({"level": "error", "kind": "off-frame", "scene": b["scene"], "el": b["tag"], "text": b["text"],
                           "fix": "text is cut off by the frame edge"})
        elif s["unsafe"]:
            issues.append({"level": "warn", "kind": "safe-area", "scene": b["scene"], "el": b["tag"], "text": b["text"],
                           "fix": "move inside .safe (platform UI covers this area)"})
        if s["overflow"]:
            issues.append({"level": "warn", "kind": "overflow", "scene": b["scene"], "el": b["tag"], "text": b["text"],
                           "fix": "text is wider than its box; reduce size or allow wrapping"})
        if s["tiny"]:
            issues.append({"level": "warn", "kind": "tiny-text", "scene": b["scene"], "el": b["tag"], "text": b["text"],
                           "fix": f"font smaller than {1.9 * U:.0f}px is hard to read on a phone"})
    seenpair = set()
    for a, b, t in sorted(overl, key=lambda x: x[2]):
        if (a, b) in seenpair:
            continue
        seenpair.add((a, b))
        ba, bb = stats.get(a, {}).get("block"), stats.get(b, {}).get("block")
        if ba and bb:
            issues.append({"level": "warn", "kind": "overlap", "scene": ba["scene"], "t": t, "el": f"{ba['tag']} / {bb['tag']}",
                           "text": f"{ba['text'][:30]} / {bb['text'][:30]}", "fix": "two text blocks overlap"})

    # contrast: measure each block at its own most-settled moment (shared screenshots per time)
    page.evaluate("window.__onevideoQA = false")
    grab = Grabber(page, "png")
    checked = set()
    by_t = {}
    for bid, s in stats.items():
        if s["best_t"] is not None:
            by_t.setdefault(s["best_t"], set()).add(bid)
    for t, ids in sorted(by_t.items()):
        page.evaluate("t => window.__stage.seek(t)", t)
        img = np.asarray(Image.open(io.BytesIO(grab())).convert("RGB")).astype(np.int32)
        pr = page.evaluate("window.__stage.probe()")
        for b in pr["blocks"]:
            if b["id"] not in ids or b["id"] in checked or "captions" in b["lint"]:
                continue
            x0, y0 = max(0, int(b["x"])), max(0, int(b["y"]))
            x1, y1 = min(img.shape[1], int(b["x"] + b["w"])), min(img.shape[0], int(b["y"] + b["h"]))
            if x1 - x0 < 4 or y1 - y0 < 4:
                continue
            checked.add(b["id"])
            crop = img[y0:y1, x0:x1].reshape(-1, 3)
            tc = np.array(b["color"][:3])
            dist = np.sqrt(((crop - tc) ** 2).sum(axis=1))
            bg = crop[dist > 60]
            if len(bg) < 0.15 * len(crop):
                continue
            # what the eye sees: text colour blended over the background by its opacity
            a = max(0.0, min(1.0, b["opacity"] * (b["color"][3] if len(b["color"]) > 3 else 1)))
            eff = a * tc + (1 - a) * np.median(bg, axis=0)
            ch = bg / 255.0
            ch = np.where(ch <= 0.04045, ch / 12.92, ((ch + 0.055) / 1.055) ** 2.4)
            L = 0.2126 * ch[:, 0] + 0.7152 * ch[:, 1] + 0.0722 * ch[:, 2]
            lt = lum(eff)
            med = float(np.median(L))
            worst = float(np.percentile(L, 90)) if lt < med else float(np.percentile(L, 10))
            cr, cw = contrast(lt, med), contrast(lt, worst)
            need = 3.0 if b["size"] >= 5 * U else 4.5
            if cr < need or cw < need * 0.66:
                issues.append({"level": "warn" if cr >= need * 0.75 else "error", "kind": "contrast", "scene": b["scene"],
                               "t": round(t, 2), "el": b["tag"], "text": b["text"], "ratio": round(cr, 2),
                               "worst": round(cw, 2), "needs": need,
                               "fix": "raise contrast (darker/lighter text, scrim, or calmer background behind the text)"})
    for e in info.get("errors", []):
        issues.insert(0, {"level": "error", "kind": "runtime", "text": e})
    for w in info.get("warnings", []):
        issues.append({"level": "warn", "kind": "runtime", "text": w})
    errors = sum(1 for i in issues if i["level"] == "error")
    report = {"ok": errors == 0, "errors": errors, "warnings": len(issues) - errors, "blocks_checked": len(stats), "issues": issues}
    if args.qa_out:
        write_json(Path(args.qa_out), report)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if args.strict and errors:
        sys.exit(3)


# ------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comp", help="composition folder (contains index.html)")
    ap.add_argument("--out", help="output .mp4 (full render)")
    ap.add_argument("--format", help="landscape | vertical | square | portrait | WxH (default: timeline's)")
    ap.add_argument("--lang", help="render a translated version (needs strings/<lang>.json)")
    ap.add_argument("--safe", help="safe-area profile: social | clean | none")
    ap.add_argument("--fps", type=int, help="override fps")
    ap.add_argument("--quality", choices=["draft", "final"], default="final", help="draft = half size, fast encode")
    ap.add_argument("--workers", type=int, help="parallel browsers (default: cores/2, max 4)")
    ap.add_argument("--poster-at", type=float, help="time (s) of the frame to show as frame 0 / thumbnail")
    ap.add_argument("--poster", help="where to save the poster jpg (default: next to --out)")
    ap.add_argument("--no-bake", action="store_true",
                    help="save the poster jpg but keep the real frame 0 (for looping Reels/TikTok with an uploaded cover)")
    ap.add_argument("--stills", help="'auto' or comma list of times")
    ap.add_argument("--sheet", help="contact sheet png path")
    ap.add_argument("--frames-dir", help="save full-size stills here")
    ap.add_argument("--qa", action="store_true", help="readability/layout/contrast report")
    ap.add_argument("--qa-step", type=float, default=0.1)
    ap.add_argument("--qa-out", help="write the QA report json here")
    ap.add_argument("--strict", action="store_true", help="exit non-zero when QA finds errors")
    ap.add_argument("--cues", action="store_true", help="write COMP/cues.json from animation sfx cues")
    ap.add_argument("--param", action="append", metavar="K=V", help="extra query parameter for the page (repeatable)")
    ap.add_argument("--serve", action="store_true", help="serve the composition for live preview")
    ap.add_argument("--port", type=int, default=0)
    args = ap.parse_args()

    comp = Path(args.comp).resolve()
    if not (comp / "index.html").exists():
        die(f"{comp}/index.html not found")
    sync_mirrors(comp)
    httpd, port = start_server(comp, args.port)

    if args.serve:
        log(f"preview: http://127.0.0.1:{port}/index.html   (space = play, arrows = step, ?format=vertical, ?lang=xx)")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            return

    sync_playwright = import_playwright()
    if not args.format:
        from _common import load_timeline
        tfmt = load_timeline(comp).get("format")
        if tfmt:
            try:
                format_size(tfmt)
                args.format = tfmt
            except SystemExit:
                pass
    if args.out and not (args.stills or args.qa or args.cues):
        # probe once for duration/fps, then render in workers
        with sync_playwright() as pw:
            fmt_size = format_size(args.format) if args.format else (1920, 1080)
            browser, page, info, problems = open_page(pw, page_url(port, args), fmt_size)
            if (info["width"], info["height"]) != fmt_size:
                browser.close()
                browser, page, info, problems = open_page(pw, page_url(port, args), (info["width"], info["height"]))
            browser.close()
        if info["errors"]:
            die("the composition has errors:\n  " + "\n  ".join(info["errors"]))
        if info["warnings"]:
            log("stage warnings:\n  " + "\n  ".join(info["warnings"][:15]))
        do_render(args, comp, port, info)
        return

    with sync_playwright() as pw:
        size = format_size(args.format) if args.format else (1920, 1080)
        browser, page, info, problems = open_page(pw, page_url(port, args), size)
        if (info["width"], info["height"]) != size:
            browser.close()
            browser, page, info, problems = open_page(pw, page_url(port, args), (info["width"], info["height"]))
        if problems:
            log("page problems:\n  " + "\n  ".join(problems[:15]))
        if info["errors"]:
            log("stage errors:\n  " + "\n  ".join(info["errors"]))
        if args.cues:
            cues = page.evaluate("window.__stage.cues()")
            write_json(comp / "cues.json", cues)
            print(json.dumps({"cues": str(comp / "cues.json"), "count": len(cues)}, indent=2))
        if args.stills:
            do_stills(args, page, info)
        if args.qa:
            do_qa(args, page, info)
        if not (args.cues or args.stills or args.qa):
            print(json.dumps({k: info[k] for k in ("width", "height", "fps", "duration", "format", "lang", "dir", "scenes",
                                                   "errors", "warnings")}, indent=2, ensure_ascii=False))
        browser.close()
    httpd.shutdown()


if __name__ == "__main__":
    main()
