#!/usr/bin/env python3
"""Voiceover and captions with free, local text-to-speech.

  voice.py COMP                     speak timeline.voice.lines -> COMP/audio/voice.wav,
                                    COMP/voice.json, COMP/captions.{json,srt,vtt}
  voice.py --list                   engines and voices available on this machine
  voice.py --say "Hello" --lang es --out hello.wav

Timeline:
  "voice": {"engine": "auto", "lang": "en-us", "voice": "af_heart", "speed": 1.0,
            "lines": [{"id": "l1", "scene": "hook", "at": 0.3, "text": "..."}]}
  A line's text may be "@key" to read strings/<lang>.json, so translations reuse one timeline.

Engines (auto picks the first that supports the language):
  kokoro   Kokoro-82M via `pip install kokoro-onnx` (Apache-2.0 weights). Natural voices for
           English (US/UK), Spanish, French, Hindi, Italian, Brazilian Portuguese, Japanese
           and Mandarin. Model files (~190 MB) download once from GitHub releases.
  piper    `pip install piper-tts` + a voice .onnx (set voice.model). Many languages, but
           check each voice's licence: several are non-commercial.
  espeak   `espeak-ng` binary. 100+ languages, robotic. Last resort.
  say      macOS built-in voices. Apple's licence limits them to personal, non-commercial use.
  sapi     Windows built-in voices via PowerShell.
No engine for the language? Skip voiceover and rely on on-screen text plus captions.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import die, load_json, load_timeline, log, normalize_timeline, scene_abs, sync_mirrors, write_json  # noqa: E402

SR = 48000
CACHE = Path(os.environ.get("ONEVIDEO_CACHE", Path.home() / ".cache" / "onevideo"))
KOKORO_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/"
KOKORO_FILES = {"model": "kokoro-v1.0.fp16.onnx", "voices": "voices-v1.0.bin"}
# language -> (kokoro lang code, default female voice, default male voice)
KOKORO_LANGS = {
    "en-us": ("en-us", "af_heart", "am_michael"), "en": ("en-us", "af_heart", "am_michael"),
    "en-gb": ("en-gb", "bf_emma", "bm_george"), "es": ("es", "ef_dora", "em_alex"),
    "fr": ("fr-fr", "ff_siwis", "ff_siwis"), "hi": ("hi", "hf_alpha", "hm_omega"),
    "it": ("it", "if_sara", "im_nicola"), "pt-br": ("pt-br", "pf_dora", "pm_alex"), "pt": ("pt-br", "pf_dora", "pm_alex"),
    "ja": ("ja", "jf_alpha", "jm_kumo"), "zh": ("cmn", "zf_xiaobei", "zm_yunjian"), "cmn": ("cmn", "zf_xiaobei", "zm_yunjian"),
}
CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")


# ------------------------------------------------------------------ engines
def norm_lang(lang: str) -> str:
    lang = (lang or "en-us").lower().replace("_", "-")
    if lang in KOKORO_LANGS:
        return lang
    return lang.split("-")[0] if lang.split("-")[0] in KOKORO_LANGS else lang


def have_kokoro() -> bool:
    try:
        import kokoro_onnx  # noqa: F401
        return True
    except Exception:
        return False


def kokoro_paths(download=True):
    d = CACHE / "kokoro"
    d.mkdir(parents=True, exist_ok=True)
    paths = {k: d / v for k, v in KOKORO_FILES.items()}
    for k, p in paths.items():
        if p.exists() and p.stat().st_size > 1_000_000:
            continue
        if not download:
            return None
        url = KOKORO_URL + p.name
        log(f"voice: downloading {p.name} (one time) from {url}")
        tmp = p.with_suffix(p.suffix + ".part")
        ok = False
        if shutil.which("curl"):
            ok = subprocess.run(["curl", "-fsSL", "--retry", "3", "-o", str(tmp), url]).returncode == 0
        if not ok:
            try:
                import urllib.request
                urllib.request.urlretrieve(url, tmp)
                ok = True
            except Exception as e:
                log(f"voice: download failed: {e}")
        if not ok:
            die(f"could not download {url}. Download it manually into {d}")
        tmp.rename(p)
    return paths


_KOKORO = None


def kokoro_engine():
    global _KOKORO
    if _KOKORO is None:
        try:
            import onnxruntime
            onnxruntime.set_default_logger_severity(3)
        except Exception:
            pass
        from kokoro_onnx import Kokoro
        p = kokoro_paths()
        _KOKORO = Kokoro(str(p["model"]), str(p["voices"]))
    return _KOKORO


def synth_kokoro(text, lang, voice, speed):
    code, fdef, _ = KOKORO_LANGS[norm_lang(lang)]
    k = kokoro_engine()
    voice = voice or fdef
    if voice not in k.get_voices():
        die(f"unknown kokoro voice '{voice}'. Try: voice.py --list")
    try:
        audio, sr, timings = k.create_timed(text, voice=voice, speed=float(speed), lang=code)
        words = []
        cur = None
        for tm in timings:
            if tm.phoneme.strip() == "" or tm.phoneme in ".,!?;:":
                if cur:
                    words.append(cur)
                    cur = None
                continue
            if cur is None:
                cur = [tm.start, tm.end]
            else:
                cur[1] = tm.end
        if cur:
            words.append(cur)
    except Exception:
        audio, sr = k.create(text, voice=voice, speed=float(speed), lang=code)
        words = []
    return np.asarray(audio, dtype=np.float64), sr, words, voice


def synth_cmd(cmd, wav_out):
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0 or not Path(wav_out).exists():
        die(f"TTS command failed: {' '.join(cmd[:3])} ... {r.stderr.decode(errors='ignore')[:300]}")


def read_any_audio(path):
    """Read wav/aiff through ffmpeg to mono float at 48 kHz."""
    from _common import need_ffmpeg
    ff = need_ffmpeg()
    r = subprocess.run([ff, "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"], capture_output=True)
    if r.returncode != 0:
        die(f"could not read {path}")
    return np.frombuffer(r.stdout, dtype=np.float32).astype(np.float64)


def synth_other(engine, text, lang, voice, speed, model=None):
    tmpd = Path(tempfile.mkdtemp(prefix="ptv-tts-"))
    out = tmpd / "line.wav"
    if engine == "espeak":
        exe = shutil.which("espeak-ng") or shutil.which("espeak")
        if not exe:
            die("espeak-ng not installed (apt install espeak-ng / brew install espeak-ng)")
        synth_cmd([exe, "-v", voice or lang.split("-")[0], "-s", str(int(165 * float(speed))), "-w", str(out), text], out)
    elif engine == "say":
        aiff = tmpd / "line.aiff"
        cmd = ["say", "-o", str(aiff), "-r", str(int(185 * float(speed)))]
        if voice:
            cmd += ["-v", voice]
        synth_cmd(cmd + [text], aiff)
        out = aiff
    elif engine == "sapi":
        ps = shutil.which("powershell") or shutil.which("pwsh")
        if not ps:
            die("PowerShell not found")
        safe = text.replace("'", "''")
        sel = f"$s.SelectVoice('{voice}');" if voice else ""
        script = ("Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                  f"{sel} $s.Rate = {int(round((float(speed) - 1) * 10))}; $s.SetOutputToWaveFile('{out}'); $s.Speak('{safe}'); $s.Dispose()")
        synth_cmd([ps, "-NoProfile", "-Command", script], out)
    elif engine == "piper":
        if not model:
            die("piper needs voice.model (path to a .onnx voice). Check that voice's licence.")
        synth_cmd([sys.executable, "-m", "piper", "-m", str(model), "-f", str(out), "--", text], out)
    else:
        die(f"unknown engine '{engine}'")
    audio = read_any_audio(out)
    shutil.rmtree(tmpd, ignore_errors=True)
    return audio, SR, [], voice or "default"


def pick_engine(lang, wanted):
    if wanted and wanted != "auto":
        return wanted
    if norm_lang(lang) in KOKORO_LANGS and have_kokoro():
        return "kokoro"
    if shutil.which("espeak-ng") or shutil.which("espeak"):
        return "espeak"
    if platform.system() == "Darwin" and shutil.which("say"):
        return "say"
    if platform.system() == "Windows":
        return "sapi"
    return None


# ------------------------------------------------------------------- audio
def resample(x, sr):
    if sr == SR:
        return x
    try:
        from scipy.signal import resample_poly
        from math import gcd
        g = gcd(SR, sr)
        return resample_poly(x, SR // g, sr // g)
    except Exception:
        n = int(len(x) * SR / sr)
        return np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)


def clean(x):
    """Trim silence, high-pass, even out level (-19 dBFS RMS, peaks under -2 dBFS).
    Returns (audio, seconds trimmed from the start) so word timings can be shifted."""
    if not len(x):
        return x, 0.0
    thr = 10 ** (-48 / 20) * (np.max(np.abs(x)) + 1e-9) * 30
    idx = np.where(np.abs(x) > thr)[0]
    a = 0
    if len(idx):
        a, b = max(0, idx[0] - int(0.03 * SR)), min(len(x), idx[-1] + int(0.08 * SR))
        x = x[a:b]
    try:
        from scipy.signal import butter, sosfilt
        x = sosfilt(butter(2, 70, "highpass", fs=SR, output="sos"), x)
    except Exception:
        pass
    rms = np.sqrt(np.mean(x ** 2)) + 1e-9
    x = x * (10 ** (-19 / 20) / rms)
    pk = np.max(np.abs(x))
    if pk > 10 ** (-2 / 20):
        x = np.tanh(x / pk * 1.2) / np.tanh(1.2) * 10 ** (-2 / 20)
    fade = int(0.006 * SR)
    x[:fade] *= np.linspace(0, 1, fade)
    x[-fade:] *= np.linspace(1, 0, fade)
    return x, a / SR


# ---------------------------------------------------------------- captions
def chunk_text(text, max_chars=38):
    cjk = bool(CJK.search(text))
    limit = 16 if cjk else max_chars
    if cjk:
        units = re.findall(r".", text)
        joiner = ""
    else:
        units = text.split()
        joiner = " "
    chunks, cur = [], []
    for u in units:
        trial = joiner.join(cur + [u])
        if cur and len(trial) > limit:
            chunks.append(joiner.join(cur))
            cur = [u]
        else:
            cur.append(u)
        if not cjk and re.search(r"[.!?;:]$", u) and len(joiner.join(cur)) > limit * 0.45:
            chunks.append(joiner.join(cur))
            cur = []
    if cur:
        chunks.append(joiner.join(cur))
    return [c.strip() for c in chunks if c.strip()]


def caption_times(chunks, start, dur, words):
    """Map chunks to times. Uses word timings from the TTS when it has them,
    otherwise spreads chunks by character count across the line."""
    total = sum(len(c) for c in chunks) or 1
    out = []
    acc = 0
    for c in chunks:
        a = acc / total
        b = (acc + len(c)) / total
        acc += len(c)
        if words:
            def at(frac):
                i = min(len(words) - 1, int(frac * len(words)))
                return words[i][0]
            s = at(a) if a > 0 else 0.0
            e = words[min(len(words) - 1, max(0, int(round(b * len(words))) - 1))][1] if b < 1 else dur
        else:
            s, e = a * dur, b * dur
        out.append({"start": round(start + s, 3), "end": round(start + max(e, s + 0.6), 3), "text": c})
    for i in range(len(out) - 1):
        out[i]["end"] = min(out[i]["end"], out[i + 1]["start"])
        if out[i + 1]["start"] - out[i]["end"] < 0.12:
            out[i]["end"] = out[i + 1]["start"]
    return out


def srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def write_captions(comp, caps, lang):
    write_json(comp / "captions.json", caps)
    srt = "\n".join(f"{i + 1}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}\n" for i, c in enumerate(caps))
    (comp / "captions.srt").write_text(srt, encoding="utf-8")
    vtt = "WEBVTT\n\n" + "\n".join(f"{srt_time(c['start']).replace(',', '.')} --> {srt_time(c['end']).replace(',', '.')}\n{c['text']}\n" for c in caps)
    (comp / "captions.vtt").write_text(vtt, encoding="utf-8")


# -------------------------------------------------------------------- main
def resolve_text(comp, text, lang):
    if isinstance(text, str) and text.startswith("@"):
        key = text[1:]
        table = load_json(comp / "strings" / f"{lang.split('-')[0]}.json") or load_json(comp / "strings" / f"{lang}.json") or {}
        if key not in table:
            die(f"voice line uses {text} but strings/{lang}.json has no '{key}'")
        return table[key]
    return text


def run(comp, args):
    tl = load_timeline(comp)
    normalize_timeline(tl)
    v = tl.get("voice") or {}
    lines = v.get("lines") or []
    if not lines:
        die("timeline.voice.lines is empty")
    lang = args.lang or v.get("lang") or tl.get("lang") or "en-us"
    engine = pick_engine(lang, args.engine or v.get("engine"))
    if not engine:
        die(f"no TTS engine for '{lang}' here. Options: pip install kokoro-onnx (en/es/fr/hi/it/pt-br/ja/zh), "
            "install espeak-ng, or skip voiceover and keep captions/on-screen text.")
    voice = args.voice or v.get("voice")
    speed = float(args.speed or v.get("speed", 1.0))
    dur = float(tl.get("duration", 0))
    track = np.zeros(int((dur + 1) * SR))
    out_lines, caps, problems = [], [], []
    prev_end = 0.0
    scenes = {s["id"]: s for s in tl.get("scenes", [])}
    for i, line in enumerate(lines):
        text = resolve_text(comp, line["text"], lang)
        if engine == "kokoro":
            a, sr, words, used = synth_kokoro(text, lang, voice, line.get("speed", speed))
        else:
            a, sr, words, used = synth_other(engine, text, lang, voice, line.get("speed", speed), v.get("model"))
        a, cut = clean(resample(a, sr))
        words = [[max(0.0, w0 - cut), max(0.0, w1 - cut)] for w0, w1 in words]
        start = scene_abs(tl, line) if (line.get("t") is not None or line.get("scene")) else prev_end + 0.25
        if start < prev_end + 0.12 and i:
            problems.append(f"line {line.get('id', i)} starts before the previous one ends; moved to {prev_end + 0.15:.2f}s")
            start = prev_end + 0.15
        ln = len(a) / SR
        end = start + ln
        sc = scenes.get(line.get("scene"))
        if sc and end > sc["start"] + sc["dur"] + 0.05:
            problems.append(f"line {line.get('id', i)} ends at {end:.2f}s, {end - (sc['start'] + sc['dur']):.2f}s past the end of scene "
                            f"'{sc['id']}' ({ln:.2f}s of speech). Lengthen the scene or shorten the line.")
        if end > dur:
            problems.append(f"line {line.get('id', i)} runs past the end of the video ({end:.2f}s > {dur:.2f}s)")
        i0 = int(start * SR)
        if i0 + len(a) > len(track):
            track = np.concatenate([track, np.zeros(i0 + len(a) - len(track) + SR)])
        track[i0:i0 + len(a)] += a
        prev_end = end
        toks = text.split()
        wl = [{"start": round(start + w0, 3), "end": round(start + w1, 3), **({"text": toks[j]} if len(toks) == len(words) else {})}
              for j, (w0, w1) in enumerate(words)]
        out_lines.append({"id": line.get("id", f"l{i + 1}"), "text": text, "start": round(start, 3), "end": round(end, 3),
                          "dur": round(ln, 3), "scene": line.get("scene"), "engine": engine, "voice": used, "words": wl})
        cap = line.get("caption", True)   # false = don't caption this line; a string = caption text instead of the spoken text
        if cap:
            ctext = cap if isinstance(cap, str) else text
            caps += caption_times(chunk_text(ctext), start, ln, words if ctext == text else [])
    adir = comp / "audio"
    adir.mkdir(exist_ok=True)
    track = track[: int(dur * SR)] if dur else track
    st = np.vstack([track, track])
    pcm = (np.clip(st, -1, 1).T * 32767).astype("<i2")
    with wave.open(str(adir / "voice.wav"), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    write_json(comp / "voice.json", {"engine": engine, "lang": lang, "lines": out_lines, "problems": problems})
    write_captions(comp, caps, lang)
    sync_mirrors(comp)
    for p in problems:
        log("voice: " + p)
    print(json.dumps({"engine": engine, "lang": lang, "lines": [{k: l[k] for k in ("id", "start", "end", "dur", "scene")} for l in out_lines],
                      "captions": len(caps), "problems": problems, "files": [str(adir / "voice.wav"), str(comp / "captions.srt")]},
                     indent=2, ensure_ascii=False))


def list_engines():
    info = {"kokoro": {"installed": have_kokoro(), "models_cached": kokoro_paths(download=False) is not None,
                       "languages": sorted({k for k in KOKORO_LANGS}), "install": "pip install kokoro-onnx"},
            "espeak": {"installed": bool(shutil.which("espeak-ng") or shutil.which("espeak"))},
            "say": {"installed": platform.system() == "Darwin" and bool(shutil.which("say")), "note": "personal use only"},
            "sapi": {"installed": platform.system() == "Windows"},
            "piper": {"installed": bool(subprocess.run([sys.executable, "-c", "import piper"], capture_output=True).returncode == 0),
                      "note": "needs a voice .onnx; check its licence"}}
    if info["kokoro"]["installed"] and info["kokoro"]["models_cached"]:
        try:
            vs = kokoro_engine().get_voices()
            info["kokoro"]["voices"] = {p: [x for x in vs if x[0] == p] for p in sorted({x[0] for x in vs})}
            info["kokoro"]["voice_prefix"] = {"a": "en-us", "b": "en-gb", "e": "es", "f": "fr", "h": "hi", "i": "it", "j": "ja", "p": "pt-br", "z": "zh"}
        except Exception as e:
            info["kokoro"]["error"] = str(e)
    print(json.dumps(info, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comp", nargs="?")
    ap.add_argument("--engine", help="auto | kokoro | piper | espeak | say | sapi")
    ap.add_argument("--voice")
    ap.add_argument("--lang")
    ap.add_argument("--speed", type=float)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--say", help="speak this text to --out (quick test)")
    ap.add_argument("--out", default="say.wav")
    args = ap.parse_args()
    if args.list:
        return list_engines()
    if args.say:
        lang = args.lang or "en-us"
        eng = pick_engine(lang, args.engine)
        if not eng:
            die(f"no TTS engine for {lang}")
        a, sr, _, used = synth_kokoro(args.say, lang, args.voice, args.speed or 1.0) if eng == "kokoro" else \
            synth_other(eng, args.say, lang, args.voice, args.speed or 1.0)
        a, _ = clean(resample(a, sr))
        with wave.open(args.out, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((np.clip(a, -1, 1) * 32767).astype("<i2").tobytes())
        print(json.dumps({"engine": eng, "voice": used, "seconds": round(len(a) / SR, 2), "out": args.out}))
        return
    if not args.comp:
        ap.error("COMP is required")
    run(Path(args.comp), args)


if __name__ == "__main__":
    main()
