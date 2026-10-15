#!/usr/bin/env python3
"""Mix the soundtrack, normalise loudness and mux it with a rendered (silent) video.

  assemble.py COMP --video work/video.mp4 --out final.mp4
              [--lufs -14] [--tp -1] [--duck 9] [--no-voice] [--no-sfx] [--gif preview.gif]
              [--poster-from 4.2 --poster poster.jpg]

Reads COMP/audio/music.wav, sfx.wav and voice.wav (any can be missing).
Music ducks under the voice, the mix is normalised with ffmpeg's two-pass loudnorm
(-14 LUFS integrated, -1 dBTP: what YouTube, Spotify and most social apps normalise to),
then muxed as AAC 48 kHz with +faststart so it streams before it finishes downloading.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import die, log, media_duration, need_ffmpeg  # noqa: E402

SR = 48000


def read_wav(p: Path):
    if not p.exists():
        return None
    with wave.open(str(p)) as w:
        if w.getframerate() != SR or w.getsampwidth() != 2:
            log(f"assemble: {p.name} is not 48 kHz 16-bit; converting")
            return read_any(p)
        x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float64) / 32768.0
        ch = w.getnchannels()
    x = x.reshape(-1, ch).T
    return np.vstack([x[0], x[0]]) if ch == 1 else x[:2]


def read_any(p: Path):
    ff = need_ffmpeg()
    r = subprocess.run([ff, "-v", "error", "-i", str(p), "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"], capture_output=True)
    if r.returncode != 0:
        die(f"cannot read {p}")
    return np.frombuffer(r.stdout, dtype=np.float32).reshape(-1, 2).T.astype(np.float64)


def write_wav_f32(p: Path, x):
    ff = need_ffmpeg()
    raw = np.ascontiguousarray(x.T.astype(np.float32)).tobytes()
    r = subprocess.run([ff, "-y", "-v", "error", "-f", "f32le", "-ar", str(SR), "-ac", "2", "-i", "-", "-c:a", "pcm_f32le", str(p)],
                       input=raw)
    if r.returncode != 0:
        die("could not write intermediate audio")


def fit(x, n):
    if x is None:
        return np.zeros((2, n))
    if x.shape[1] >= n:
        return x[:, :n]
    return np.concatenate([x, np.zeros((2, n - x.shape[1]))], axis=1)


def duck_gain(voice, depth_db, n):
    """Gain curve for the music: dips while the voice speaks, with anticipation and a soft release."""
    v = np.abs(voice).max(axis=0)
    w = int(0.03 * SR)
    c = np.cumsum(np.concatenate([[0.0], v ** 2]))
    rms = np.sqrt(np.maximum((c[w:] - c[:-w]) / w, 0))
    rms = np.concatenate([rms, np.zeros(n - len(rms))])[:n]
    active = (rms > 0.01).astype(np.float64)
    pre, post = int(0.12 * SR), int(0.3 * SR)
    k = np.ones(pre + post + 1)
    act = np.convolve(active, k, mode="full")[post:post + n] > 0
    sm = int(0.15 * SR)
    m = np.convolve(act.astype(np.float64), np.ones(sm) / sm, mode="same")
    return 1 - (1 - 10 ** (-depth_db / 20)) * np.clip(m, 0, 1)


def loudnorm(ff, src: Path, dst: Path, I: float, TP: float):
    r = subprocess.run([ff, "-hide_banner", "-i", str(src), "-af", f"loudnorm=I={I}:TP={TP}:LRA=11:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if r.returncode != 0 or not m:
        log("assemble: loudnorm unavailable; using simple gain")
        return None
    meas = json.loads(m.group(0))
    if float(meas["input_i"]) < -70:  # silence
        subprocess.run([ff, "-y", "-v", "error", "-i", str(src), "-c:a", "pcm_s16le", str(dst)])
        return meas
    af = (f"loudnorm=I={I}:TP={TP}:LRA=11:measured_I={meas['input_i']}:measured_TP={meas['input_tp']}:"
          f"measured_LRA={meas['input_lra']}:measured_thresh={meas['input_thresh']}:offset={meas['target_offset']}:linear=true,"
          f"aresample={SR}")
    r2 = subprocess.run([ff, "-y", "-v", "error", "-i", str(src), "-af", af, "-ar", str(SR), "-c:a", "pcm_s16le", str(dst)])
    if r2.returncode != 0:
        return None
    return meas


def measure(ff, path: Path):
    r = subprocess.run([ff, "-hide_banner", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
    tp = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r.stderr)
    return {"lufs": float(i[-1]) if i else None, "true_peak": float(tp[-1]) if tp else None}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comp")
    ap.add_argument("--video", required=True, help="silent render from render.py")
    ap.add_argument("--out", required=True)
    ap.add_argument("--lufs", type=float, default=-14.0)
    ap.add_argument("--tp", type=float, default=-1.5, help="true-peak ceiling before AAC (lands under -1 dBTP after encoding)")
    ap.add_argument("--duck", type=float, default=9.0, help="dB the music dips under the voice")
    ap.add_argument("--sfx-duck", type=float, default=4.0, help="dB the sound effects dip under the voice")
    ap.add_argument("--voice-gain", type=float, default=0.0, help="dB")
    ap.add_argument("--music-gain", type=float, default=0.0, help="dB")
    ap.add_argument("--sfx-gain", type=float, default=0.0, help="dB")
    ap.add_argument("--no-voice", action="store_true")
    ap.add_argument("--no-sfx", action="store_true")
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--silent", action="store_true", help="no audio track at all")
    ap.add_argument("--gif", help="also write a small looping GIF preview here")
    ap.add_argument("--gif-width", type=int, default=480)
    ap.add_argument("--poster-from", type=float, help="extract a poster still at this time")
    ap.add_argument("--poster", help="poster path (default: OUT with .jpg)")
    args = ap.parse_args()

    ff = need_ffmpeg()
    comp = Path(args.comp)
    video = Path(args.video)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    vdur = media_duration(video)
    if not vdur:
        die(f"cannot read {video}")
    n = int(round(vdur * SR))
    adir = comp / "audio"
    tmp = Path(tempfile.mkdtemp(prefix="ptv-mix-"))
    report = {"video": str(out), "duration": round(vdur, 3)}

    if args.silent:
        r = subprocess.run([ff, "-y", "-v", "error", "-i", str(video), "-c", "copy", "-an", "-movflags", "+faststart", str(out)])
        if r.returncode:
            die("mux failed")
    else:
        music = None if args.no_music else read_wav(adir / "music.wav")
        sfx = None if args.no_sfx else read_wav(adir / "sfx.wav")
        voice = None if args.no_voice else read_wav(adir / "voice.wav")
        if music is None and sfx is None and voice is None:
            die(f"no audio in {adir} (run music.py / voice.py, or pass --silent)")
        music, sfx, voice = fit(music, n), fit(sfx, n), fit(voice, n)
        g = lambda d: 10 ** (d / 20)  # noqa: E731
        if np.any(voice):
            music = music * duck_gain(voice, args.duck, n)
            sfx = sfx * duck_gain(voice, args.sfx_duck, n)
            report["ducking_db"] = {"music": args.duck, "sfx": args.sfx_duck}
        mix = music * g(args.music_gain) + sfx * g(args.sfx_gain) + voice * g(args.voice_gain)
        fade = int(0.02 * SR)
        mix[:, -fade:] *= np.linspace(1, 0, fade)
        raw = tmp / "mix.wav"
        write_wav_f32(raw, mix)
        norm = tmp / "mix_norm.wav"
        meas = loudnorm(ff, raw, norm, args.lufs, args.tp)
        if meas is None:
            pk = np.max(np.abs(mix)) + 1e-9
            write_wav_f32(norm, mix * (10 ** (args.tp / 20) / pk))
        r = subprocess.run([ff, "-y", "-v", "error", "-i", str(video), "-i", str(norm), "-map", "0:v:0", "-map", "1:a:0",
                            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-ac", "2",
                            "-af", f"apad,atrim=0:{vdur:.4f}", "-t", f"{vdur:.4f}", "-movflags", "+faststart", str(out)])
        if r.returncode:
            die("mux failed")
        report["loudness"] = measure(ff, out)

    if args.poster_from is not None:
        poster = Path(args.poster) if args.poster else out.with_suffix(".jpg")
        subprocess.run([ff, "-y", "-v", "error", "-ss", f"{args.poster_from:.3f}", "-i", str(out), "-frames:v", "1", "-q:v", "2", str(poster)])
        report["poster"] = str(poster)
    if args.gif:
        pal = tmp / "pal.png"
        flt = f"fps=12,scale={args.gif_width}:-1:flags=lanczos"
        subprocess.run([ff, "-y", "-v", "error", "-i", str(out), "-vf", f"{flt},palettegen=stats_mode=diff", str(pal)])
        subprocess.run([ff, "-y", "-v", "error", "-i", str(out), "-i", str(pal), "-lavfi",
                        f"{flt}[x];[x][1:v]paletteuse=dither=sierra2_4a", "-loop", "0", args.gif])
        report["gif"] = args.gif
    report["size_mb"] = round(out.stat().st_size / 1e6, 2)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
