#!/usr/bin/env python3
"""Compose an original soundtrack and sound effects for a composition, from its timeline.

  music.py COMP                  writes COMP/audio/{music,sfx,soundtrack}.wav and music.json
  music.py COMP --style lofi --seed 7
  music.py COMP --list           styles and sound-effect names
  music.py --analyze song.mp3    tempo + first beat of a track the user supplied

Everything is synthesised here with numpy (scipy makes it faster and nicer), so the
music is original and needs no licence. It is scored to the picture: tempo comes from
timeline.json (run timeline.py --snap first so cuts land on beats), each scene's
`energy` (0..1) decides how dense the arrangement is, scene `music` hints add builds,
drops, stops and the final sting, and every sound effect is tuned to the song's key
and sent through the same reverb so it sits inside the music instead of on top of it.

Timeline fields used:
  music: {style, bpm, key ("D"), mode (major|minor|dorian|mixolydian), seed, ending
          (sting|ringout|fade|button|cut), lead (true|false), gain_db, track: {file, offset}}
  scenes[]: {id, start, dur, energy, music: build|drop|stop|hit|sting|soft}
  sfx[]: {t | scene+at, type, gain}     plus COMP/cues.json written by render.py --cues
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import die, load_json, load_timeline, log, need_ffmpeg, normalize_timeline, scene_abs, write_json  # noqa: E402

try:
    from scipy import signal as sps
except Exception:  # pragma: no cover - works without scipy, just slower/plainer
    sps = None

SR = 48000
TAU = 2 * np.pi
NOTE = {"C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3, "E": 4, "F": 5, "F#": 6, "GB": 6, "G": 7,
        "G#": 8, "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11}
MODES = {"major": [0, 2, 4, 5, 7, 9, 11], "minor": [0, 2, 3, 5, 7, 8, 10], "dorian": [0, 2, 3, 5, 7, 9, 10],
         "mixolydian": [0, 2, 4, 5, 7, 9, 10], "lydian": [0, 2, 4, 6, 7, 9, 11]}

# 16-step patterns: x = hit, o = ghost note. Each drum has (pattern, minimum energy to play).
DRUMS = {
    "pop": {"kick": ("x.....x.x.......", .45), "clap": ("....x.......x...", .5), "hat": ("x.x.x.x.x.x.x.x.", .3),
            "hat16": (".o.o.o.o.o.o.o.o", .74), "shaker": ("oooooooooooooooo", .36), "openhat": ("..............x.", .8)},
    "house": {"kick": ("x...x...x...x...", .42), "clap": ("....x.......x...", .5), "hat": ("..x...x...x...x.", .3),
              "hat16": ("o.oo.oo.o.oo.oo.", .74), "openhat": ("..x...x...x...x.", .85)},
    "lofi": {"kick": ("x......x..x.....", .32), "snare": ("....x.......x...", .4), "hat": ("x.x.x.x.x.x.x.x.", .25),
             "hat16": ("...o.......o....", .6)},
    "taiko": {"taiko": ("x.....x.x..x....", .55), "taiko_lo": ("x.......x.......", .3), "perc": ("..o...o...o...o.", .72)},
    "chip": {"kick": ("x.......x.......", .4), "snare": ("....x.......x...", .5), "hat": ("x.x.x.x.x.x.x.x.", .3),
             "hat16": (".o.o.o.o.o.o.o.o", .78)},
    "acoustic": {"kick": ("x.......x.......", .45), "clap": ("....x.......x...", .55), "shaker": ("oxoxoxoxoxoxoxox", .3),
                 "tamb": ("....x.......x...", .75)},
    "trap": {"kick": ("x.........x.....", .45), "clap": ("........x.......", .5), "hat": ("x.x.x.x.x.x.x.x.", .3),
             "hat16": (".o.o.o.o.o.ooo.o", .7)},
    "soft": {"shaker": ("o.o.o.o.o.o.o.o.", .55)},
}
BASS_PAT = {"pop": "x.....x.x...x...", "offbeat": "..x...x...x...x.", "whole": "x...............",
            "lofi": "x.....x...x.....", "chip": "x.x.x.x.x.x.x.x.", "808": "x.........x.....", "acoustic": "x.......x...x..."}
STYLES = {
    "uplifting": dict(mode="major", progs=[[0, 4, 5, 3], [5, 3, 0, 4], [0, 5, 3, 4], [3, 0, 4, 5]], bpc=1, drums="pop",
                      bass=("synth", "pop"), pad="warm", comp="pluck", arp="saw", lead="pluck", rt60=1.6, side=.25,
                      keys=["D", "E", "A", "C", "G", "F"], cad=4),
    "tech": dict(mode="minor", progs=[[0, 5, 2, 6], [0, 6, 5, 6], [0, 3, 5, 4]], bpc=1, drums="house",
                 bass=("synth", "offbeat"), pad="saw", comp=None, arp="saw", lead="saw", rt60=1.4, side=.45,
                 keys=["A", "F#", "C#", "D", "E"], cad=6),
    "cinematic": dict(mode="minor", progs=[[0, 5, 2, 6], [0, 3, 5, 4], [0, 5, 3, 4]], bpc=2, drums="taiko",
                      bass=("sub", "whole"), pad="strings", comp="ostinato", arp=None, lead="bell", rt60=2.8, side=0,
                      keys=["D", "C", "E", "A"], cad=4),
    "lofi": dict(mode="major", progs=[[1, 4, 0, 5], [3, 2, 1, 0], [0, 5, 1, 4]], bpc=1, drums="lofi",
                 bass=("soft", "lofi"), pad="warm", comp="epiano", arp=None, lead="epiano", rt60=1.5, side=0,
                 keys=["F", "Eb", "C", "Ab", "D"], sevenths=True, swing=.58, vinyl=True, cad=4),
    "ambient": dict(mode="major", progs=[[0, 3, 0, 4], [0, 5, 3, 0], [3, 0, 5, 4]], bpc=2, drums="soft",
                    bass=("sub", "whole"), pad="glass", comp="bell", arp=None, lead="bell", rt60=3.6, side=0,
                    keys=["E", "D", "A", "B", "F#"], sevenths=True, cad=3),
    "chiptune": dict(mode="major", progs=[[0, 5, 3, 4], [0, 4, 5, 3]], bpc=1, drums="chip", bass=("triangle", "chip"),
                     pad=None, comp=None, arp="square", lead="square", rt60=.7, side=0, keys=["C", "G", "D", "A"], cad=4),
    "acoustic": dict(mode="major", progs=[[0, 4, 5, 3], [0, 3, 4, 3], [5, 3, 0, 4]], bpc=1, drums="acoustic",
                     bass=("soft", "acoustic"), pad="warm", comp="guitar", arp=None, lead="pluck", rt60=1.3, side=0,
                     keys=["G", "D", "C", "A", "E"], cad=4),
    "hype": dict(mode="minor", progs=[[0, 0, 5, 4], [0, 5, 6, 4], [0, 3, 5, 6]], bpc=1, drums="trap", bass=("808", "808"),
                 pad="dark", comp=None, arp="bell", lead="bell", rt60=1.5, side=.2, keys=["F", "G", "C#", "A"], cad=4),
    "piano": dict(mode="major", progs=[[0, 4, 5, 3], [5, 3, 0, 4], [0, 5, 3, 4]], bpc=1, drums=None,
                  bass=None, pad="glass", comp="piano", arp=None, lead=None, rt60=2.4, side=0,
                  keys=["C", "G", "F", "D", "Eb"], cad=4),
}
SFX_NAMES = ["whoosh", "swoosh", "swipe", "riser", "downlifter", "impact", "boom", "hit", "pop", "click", "tap",
             "type", "tick", "ding", "chime", "sparkle", "success", "error", "notify", "glitch", "shutter",
             "bubble", "thud", "snap", "crash", "stinger"]
ALIASES = {"whoosh_short": "swoosh", "woosh": "whoosh", "slam": "impact", "keypress": "type", "key": "type",
           "bell": "ding", "pling": "ding", "notification": "notify", "camera": "shutter", "drop": "impact",
           "reveal": "impact", "transition": "swoosh", "boing": "bubble", "wrong": "error", "correct": "success"}


# ------------------------------------------------------------------ dsp basics
def T(n):
    return np.arange(n, dtype=np.float64) / SR


def mhz(m):
    return 440.0 * 2.0 ** ((np.asarray(m, dtype=np.float64) - 69.0) / 12.0)


def db(x):
    return 10.0 ** (x / 20.0)


def _sos(kind, f, order):
    nyq = SR / 2
    if kind == "bandpass":
        lo, hi = f
        lo, hi = max(15.0, min(lo, nyq * 0.9)), max(25.0, min(hi, nyq * 0.97))
        if hi <= lo * 1.05:
            hi = lo * 1.05
        return sps.butter(order, [lo, hi], btype="bandpass", fs=SR, output="sos")
    return sps.butter(order, max(10.0, min(f, nyq * 0.97)), btype=kind, fs=SR, output="sos")


def filt(x, kind, f, order=2):
    if sps is not None:
        return sps.sosfilt(_sos(kind, f, order), x, axis=-1)
    n = x.shape[-1]
    F = np.fft.rfftfreq(n, 1 / SR)
    X = np.fft.rfft(x, axis=-1)
    Fs = np.maximum(F, 1e-6)
    if kind == "lowpass":
        H = 1 / np.sqrt(1 + (Fs / f) ** (2 * order))
    elif kind == "highpass":
        H = 1 / np.sqrt(1 + (f / Fs) ** (2 * order))
    else:
        lo, hi = f
        H = (1 / np.sqrt(1 + (lo / Fs) ** (2 * order))) / np.sqrt(1 + (Fs / hi) ** (2 * order))
    return np.fft.irfft(X * H, n=n, axis=-1)


def lp(x, f, o=2):
    return filt(x, "lowpass", f, o)


def hp(x, f, o=2):
    return filt(x, "highpass", f, o)


def bp(x, lo, hi, o=2):
    return filt(x, "bandpass", (lo, hi), o)


def sweep(x, kind, f0, f1, q=1.4, block=256):
    """Filter whose cutoff (or band centre) glides exponentially from f0 to f1."""
    n = len(x)
    nb = max(1, math.ceil(n / block))
    if sps is None:
        parts = 8
        out = np.zeros(n)
        edges = np.linspace(0, n, parts + 1).astype(int)
        for i in range(parts):
            fc = f0 * (f1 / f0) ** (i / max(1, parts - 1))
            seg = filt(x, "bandpass", (fc / (1 + .5 / q), fc * (1 + .5 / q)), 1) if kind == "bandpass" else filt(x, kind, fc, 2)
            out[edges[i]:edges[i + 1]] = seg[edges[i]:edges[i + 1]]
        return out
    out = np.zeros(n)
    zi = None
    for i in range(nb):
        fc = f0 * (f1 / f0) ** (i / max(1, nb - 1))
        sos = _sos("bandpass", (fc / (1 + .5 / q), fc * (1 + .5 / q)), 1) if kind == "bandpass" else _sos(kind, fc, 2)
        if zi is None:
            zi = np.zeros((sos.shape[0], 2))
        seg = x[i * block:(i + 1) * block]
        y, zi = sps.sosfilt(sos, seg, zi=zi)
        out[i * block:i * block + len(y)] = y
    return out


_WT = {}


def _table(shape, H):
    key = (shape, H)
    if key in _WT:
        return _WT[key]
    L = 4096
    ph = np.arange(L) / L
    w = np.zeros(L)
    if shape == "sine" or H < 1:
        w = np.sin(TAU * ph)
    elif shape == "saw":
        for h in range(1, H + 1):
            w += np.sin(TAU * h * ph) / h
        w *= 2 / np.pi
    elif shape == "square":
        for h in range(1, H + 1, 2):
            w += np.sin(TAU * h * ph) / h
        w *= 4 / np.pi
    elif shape == "triangle":
        for h in range(1, H + 1, 2):
            w += ((-1) ** ((h - 1) // 2)) * np.sin(TAU * h * ph) / (h * h)
        w *= 8 / np.pi ** 2
    elif shape == "pulse":
        d = 0.25
        for h in range(1, H + 1):
            w += (2 / (h * np.pi)) * np.sin(np.pi * h * d) * np.cos(TAU * h * (ph - d / 2))
        w -= w.mean()
    w = np.append(w, w[0])
    _WT[key] = w
    return w


_XP = np.arange(4097, dtype=np.float64)


def osc(shape, freq, n, phase0=0.0, cutoff=None):
    """Band-limited wavetable oscillator. freq can be a scalar or a per-sample array."""
    fmax = float(np.max(freq))
    lim = min(cutoff or SR * 0.45, SR * 0.45)
    H = int(max(1, min(200, lim / max(fmax, 1.0))))
    if H > 24:
        H = int(round(H / 8) * 8)
    tab = _table(shape, H)
    if np.ndim(freq) == 0:
        ph = phase0 + np.arange(n) * (float(freq) / SR)
    else:
        ph = phase0 + np.cumsum(freq) / SR
    return np.interp((ph % 1.0) * 4096.0, _XP, tab)


def adsr(n, a, d, s, r, length):
    t = T(n)
    a = max(a, 1e-4)
    e = np.where(t < a, t / a, np.where(t < a + d, 1 - (1 - s) * (t - a) / max(d, 1e-4), s))
    L = max(length, 0.0)
    vL = (L / a) if L < a else (1 - (1 - s) * (L - a) / max(d, 1e-4) if L < a + d else s)
    rel = t >= L
    e = np.where(rel, vL * np.clip(1 - (t - L) / max(r, 1e-4), 0, 1) ** 2, e)
    return e


def fade_edges(x, a=0.002, b=0.01):
    na, nb = int(a * SR), int(b * SR)
    if na and x.shape[-1] > na:
        x[..., :na] *= np.linspace(0, 1, na)
    if nb and x.shape[-1] > nb:
        x[..., -nb:] *= np.linspace(1, 0, nb)
    return x


def conv(a, b):
    if sps is not None:
        return sps.fftconvolve(a, b)
    n = len(a) + len(b) - 1
    N = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(a, N) * np.fft.rfft(b, N), N)[:n]


def lfilter1(b, a, x):
    if sps is not None:
        return sps.lfilter(b, a, x)
    y = np.zeros_like(x)
    for i in range(len(x)):  # only used for short signals without scipy
        acc = sum(b[k] * x[i - k] for k in range(len(b)) if i - k >= 0)
        acc -= sum(a[k] * y[i - k] for k in range(1, len(a)) if i - k >= 0)
        y[i] = acc / a[0]
    return y


# ----------------------------------------------------------------- instruments
class Kit:
    def __init__(self, rng):
        self.rng = rng

    def noise(self, n):
        return self.rng.standard_normal(n)

    def kick(self, v=1.0, tone=1.0):
        n = int(0.5 * SR)
        t = T(n)
        f = 43 + 125 * tone * np.exp(-t * 36)
        body = np.sin(TAU * np.cumsum(f) / SR) * np.exp(-t * 6.8)
        click = hp(self.noise(n) * np.exp(-t * 380), 1800) * 0.18
        x = np.tanh(1.7 * body) * 0.95 + click
        return fade_edges(x * v, 0.0005, 0.02)

    def snare(self, v=1.0):
        n = int(0.32 * SR)
        t = T(n)
        tone = (np.sin(TAU * 186 * t) * np.exp(-t * 24) + 0.5 * np.sin(TAU * 332 * t) * np.exp(-t * 32)) * 0.55
        nz = bp(self.noise(n), 1300, 8500) * np.exp(-t * 17)
        return fade_edges((tone + nz * 0.95) * v * 0.8)

    def clap(self, v=1.0):
        n = int(0.38 * SR)
        x = np.zeros(n)
        for k, dt in enumerate([0, 0.0095, 0.0185, 0.027]):
            i = int(dt * SR)
            m = n - i
            x[i:] += self.noise(m) * np.exp(-T(m) * (150 if k < 3 else 15)) * (0.75 if k < 3 else 1.0)
        return fade_edges(bp(x, 950, 5200) * 0.62 * v)

    def hat(self, v=1.0, open_=False):
        n = int((0.42 if open_ else 0.085) * SR)
        t = T(n)
        metal = np.zeros(n)
        for f in (205.3, 304.4, 369.6, 522.7, 540.0, 800.0):
            metal += np.sign(np.sin(TAU * f * 1.71 * t + self.rng.uniform(0, TAU)))
        x = hp(0.5 * metal / 6 + 0.55 * self.noise(n), 7200, 2)
        x = lp(x, 15000)
        return fade_edges(x * np.exp(-t * (7.5 if open_ else 58)) * 0.32 * v, 0.0005, 0.01)

    def shaker(self, v=1.0):
        n = int(0.11 * SR)
        t = T(n)
        env = (1 - np.exp(-t * 260)) * np.exp(-t * 40)
        return fade_edges(bp(self.noise(n), 3600, 11000) * env * 0.3 * v)

    def tamb(self, v=1.0):
        n = int(0.25 * SR)
        t = T(n)
        x = np.zeros(n)
        for k in range(3):
            i = int(k * 0.012 * SR)
            x[i:] += bp(self.noise(n - i), 5500, 13000) * np.exp(-T(n - i) * 30)
        return fade_edges(x * 0.22 * v)

    def taiko(self, v=1.0, low=False):
        n = int(1.3 * SR)
        t = T(n)
        f0 = 52 if low else 74
        f = f0 * (1 + 0.25 * np.exp(-t * 22))
        body = np.sin(TAU * np.cumsum(f) / SR) * np.exp(-t * (2.6 if low else 3.6))
        skin = lp(self.noise(n), 900) * np.exp(-t * 30) * 0.7
        return fade_edges(np.tanh(1.4 * (body + skin)) * 0.9 * v)

    def perc(self, v=1.0):
        n = int(0.18 * SR)
        t = T(n)
        x = np.sin(TAU * 420 * t) * np.exp(-t * 35) + bp(self.noise(n), 1500, 4000) * np.exp(-t * 60) * 0.5
        return fade_edges(x * 0.4 * v)

    def crash(self, v=1.0):
        n = int(2.4 * SR)
        t = T(n)
        metal = np.zeros(n)
        for f in (263, 400, 421, 474, 587, 845):
            metal += np.sign(np.sin(TAU * f * 2.3 * t + self.rng.uniform(0, TAU)))
        x = hp(0.35 * metal / 6 + self.noise(n), 3800, 2)
        x = lp(x, 12500)
        env = (1 - np.exp(-t * 600)) * np.exp(-t * 1.55)
        return fade_edges(x * env * 0.26 * v)

    def chip_noise(self, v=1.0, dur=0.08, tone=0.0):
        n = int(dur * SR)
        t = T(n)
        steps = np.repeat(self.rng.choice([-1.0, 1.0], size=n // 24 + 1), 24)[:n]
        x = steps * np.exp(-t * (40 / max(dur, 0.02)) * 0.08)
        if tone:
            x = x * 0.6 + np.sign(np.sin(TAU * tone * t * (1 - t * 3))) * 0.5
        return fade_edges(x * 0.35 * v)


class Synth:
    def __init__(self, rng, bright=1.0):
        self.rng = rng
        self.bright = bright

    # ---- bass
    def bass(self, kind, m, dur, v=1.0):
        f = float(mhz(m))
        n = int((dur + 0.12) * SR)
        t = T(n)
        if kind == "synth":
            raw = osc("saw", f, n, cutoff=6000) * 0.5 + np.sin(TAU * f * t) * 0.75
            br, dk = lp(raw, 1800), lp(raw, 380)
            fe = np.exp(-t * 13)
            x = (br * fe + dk * (1 - fe)) * adsr(n, 0.004, 0.18, 0.8, 0.07, dur)
        elif kind == "808":
            fr = f * (1 + 0.14 * np.exp(-t * 32))
            x = np.tanh(2.0 * np.sin(TAU * np.cumsum(fr) / SR)) * np.exp(-t * (0.7 / max(dur, 0.3)))
            x *= adsr(n, 0.003, 0.05, 1.0, 0.08, dur)
        elif kind == "triangle":
            x = osc("triangle", f, n, cutoff=7000) * adsr(n, 0.002, 0.04, 0.9, 0.03, dur)
        else:  # soft / sub
            x = np.sin(TAU * f * t) + 0.24 * np.sin(2 * TAU * f * t) + 0.07 * np.sin(3 * TAU * f * t)
            x = np.tanh(1.15 * x) * adsr(n, 0.008, 0.25, 0.75, 0.08, dur)
            if kind == "sub":
                x = lp(x, 260)
        return fade_edges(x * v * 0.75, 0.001, 0.01)

    # ---- pads (stereo)
    def pad(self, kind, notes, dur, v=1.0):
        rel = {"strings": 0.9, "glass": 1.6, "dark": 1.0}.get(kind, 1.1)
        n = int((dur + rel) * SR)
        t = T(n)
        L = np.zeros(n)
        R = np.zeros(n)
        shape = {"warm": "triangle", "saw": "saw", "strings": "saw", "dark": "saw", "glass": "triangle"}.get(kind, "saw")
        cut = {"warm": 2200, "saw": 2600, "strings": 3200, "dark": 1100, "glass": 5200}.get(kind, 2400) * self.bright
        voices = [(-9, -0.65), (0, 0.0), (9, 0.65)]
        for m in notes:
            f = float(mhz(m))
            for cents, pan in voices:
                fr = f * 2 ** (cents / 1200)
                if kind == "strings":
                    vib = 1 + 0.0035 * np.sin(TAU * 5.3 * t + self.rng.uniform(0, TAU)) * np.clip(t / 0.5, 0, 1)
                    x = osc(shape, fr * vib, n, self.rng.random(), cutoff=cut * 1.5)
                else:
                    x = osc(shape, fr, n, self.rng.random(), cutoff=cut * 1.5)
                if kind == "glass":
                    x = x * 0.6 + np.sin(TAU * fr * 2 * t + self.rng.uniform(0, TAU)) * 0.25
                L += x * (1 - pan) * 0.5
                R += x * (1 + pan) * 0.5
        st = np.vstack([L, R]) / max(1, len(notes))
        st = lp(st, cut)
        att = {"strings": 0.5, "glass": 0.7, "warm": 0.25, "dark": 0.35}.get(kind, 0.3)
        env = adsr(n, att, 0.6, 0.85, rel, dur)
        return fade_edges(st * env * v * 0.55)

    # ---- keys and plucks
    def epiano(self, m, dur, v=1.0, trem=0.0):
        f = float(mhz(m))
        n = int((dur + 0.8) * SR)
        t = T(n)
        idx = (1.6 * v + 0.4) * np.exp(-t * 2.8) + 0.22
        x = np.sin(TAU * f * t + idx * np.sin(TAU * f * t))
        x += np.sin(TAU * f * 7.0 * t) * np.exp(-t * 32) * 0.1 * v
        env = (1 - np.exp(-t * 350)) * np.exp(-t * 1.05)
        env *= np.where(t > dur, np.exp(-(t - dur) * 9), 1.0)
        if trem:
            x *= 1 + trem * np.sin(TAU * 4.6 * t)
        return fade_edges(x * env * v * 0.42)

    def bell(self, m, dur, v=1.0):
        f = float(mhz(m))
        n = int((max(dur, 0.4) + 1.8) * SR)
        t = T(n)
        idx = 2.6 * np.exp(-t * 2.0) + 0.15
        x = np.sin(TAU * f * t + idx * np.sin(TAU * f * 3.5 * t))
        x += 0.25 * np.sin(TAU * f * 2.0 * t) * np.exp(-t * 3)
        env = (1 - np.exp(-t * 900)) * np.exp(-t * 1.5)
        return fade_edges(x * env * v * 0.3)

    def piano(self, m, dur, v=1.0):
        f = float(mhz(m))
        n = int((dur + 1.0) * SR)
        t = T(n)
        B = 0.00035
        x = np.zeros(n)
        bright = 0.6 + 0.6 * v
        for k in range(1, 11):
            fk = k * f * math.sqrt(1 + B * k * k)
            if fk > 12000:
                break
            amp = (1 / k ** 1.25) * (bright ** (k - 1))
            dec = 1.1 + 0.55 * (k - 1) + f / 900
            x += amp * np.sin(TAU * fk * t + self.rng.uniform(0, TAU)) * np.exp(-t * dec)
        x += lp(self.rng.standard_normal(n), 2500) * np.exp(-t * 90) * 0.04
        env = (1 - np.exp(-t * 500)) * np.where(t > dur, np.exp(-(t - dur) * 7), 1.0)
        return fade_edges(x * env * v * 0.34)

    def ks(self, m, dur, v=1.0, bright=0.5, decay=0.996):
        """Karplus-Strong plucked string, pitch-corrected by resampling."""
        f = float(mhz(m))
        if sps is None:
            return self.pluck(m, dur, v)
        P = SR / f
        Lp = int(P)
        n = int((dur + 0.6) * SR)
        exc = self.rng.standard_normal(Lp)
        exc = lp(exc, 1200 + 7000 * bright)
        x = np.zeros(n + Lp + 2)
        x[:Lp] = exc
        a = np.zeros(Lp + 2)
        a[0] = 1
        a[Lp] = -decay * 0.5
        a[Lp + 1] = -decay * 0.5
        y = sps.lfilter([1.0], a, x)
        ratio = (Lp + 0.5) / P  # actual period vs wanted
        idx = np.arange(n) * ratio
        y = np.interp(idx, np.arange(len(y)), y)
        y = hp(y, 60)
        env = np.where(T(n) > dur, np.exp(-(T(n) - dur) * 10), 1.0)
        return fade_edges(y * env * v * 0.5 / (np.max(np.abs(y[: int(0.05 * SR)])) + 1e-9) * 0.6)

    def pluck(self, m, dur, v=1.0, shape="saw"):
        f = float(mhz(m))
        n = int((dur + 0.35) * SR)
        t = T(n)
        raw = osc(shape, f, n, self.rng.random(), cutoff=9000 * self.bright)
        br, dk = lp(raw, 5200 * self.bright), lp(raw, 900)
        fe = np.exp(-t * 16)
        env = (1 - np.exp(-t * 700)) * np.exp(-t * 4.2) * np.where(t > dur, np.exp(-(t - dur) * 14), 1.0)
        return fade_edges((br * fe + dk * (1 - fe)) * env * v * 0.42)

    def square(self, m, dur, v=1.0, vib=True):
        f = float(mhz(m))
        n = int((dur + 0.06) * SR)
        t = T(n)
        fr = f * (1 + (0.006 * np.sin(TAU * 5.8 * t) * np.clip((t - 0.12) / 0.2, 0, 1) if vib else 0))
        x = osc("pulse", fr, n, cutoff=10000)
        return fade_edges(x * adsr(n, 0.003, 0.08, 0.75, 0.04, dur) * v * 0.22)


# --------------------------------------------------------------------- mixer
class Mixer:
    def __init__(self, dur, tail=4.5):
        self.n = int((dur + tail) * SR)
        self.bus = {}
        self.send = {}

    def get(self, name):
        if name not in self.bus:
            self.bus[name] = np.zeros((2, self.n))
        return self.bus[name]

    def add(self, name, x, t, gain=1.0, pan=0.0, send=0.0, space="music"):
        i0 = int(round(t * SR))
        if i0 >= self.n or x is None or not len(x):
            return
        if x.ndim == 1:
            st = np.vstack([x * min(1.0, 1 - pan), x * min(1.0, 1 + pan)]) * gain
        else:
            st = x * gain
            if pan:
                st = np.vstack([st[0] * min(1.0, 1 - pan), st[1] * min(1.0, 1 + pan)])
        if i0 < 0:
            st = st[:, -i0:]
            i0 = 0
        m = min(st.shape[1], self.n - i0)
        self.get(name)[:, i0:i0 + m] += st[:, :m]
        if send > 0:
            s = self.send.setdefault(space, np.zeros(self.n))
            s[i0:i0 + m] += (st[0, :m] + st[1, :m]) * 0.5 * send


def make_ir(rt60, rng, predelay=0.02):
    n = int((rt60 * 1.15) * SR)
    t = T(n)
    env = 10 ** (-3 * t / rt60)
    ir = rng.standard_normal((2, n)) * env
    w = np.clip(t / (rt60 * 0.45), 0, 1)
    ir = lp(ir, 9500) * (1 - w) + lp(ir, 2800) * w
    ir = hp(ir, 150)
    for k, (dt, g) in enumerate([(0.0109, .6), (0.0173, .45), (0.0229, .4), (0.0311, .32), (0.0397, .26), (0.0503, .2)]):
        ir[k % 2, int(dt * SR)] += g * 3
    ir = np.concatenate([np.zeros((2, int(predelay * SR))), ir], axis=1)
    ir /= np.sqrt((ir ** 2).sum(axis=1, keepdims=True)) + 1e-12
    return ir


def apply_reverb(send, ir, n):
    out = np.zeros((2, n))
    if send is None or not np.any(send):
        return out
    for c in range(2):
        out[c] = conv(send, ir[c])[:n]
    return out


def delay_fx(x, t_delay, fb=0.32, taps=4, damp=3500):
    """Ping-pong echo on a stereo buffer."""
    out = x.copy()
    d = int(t_delay * SR)
    src = lp(x.mean(axis=0), damp)
    for k in range(1, taps + 1):
        sh = k * d
        if sh >= x.shape[1]:
            break
        ch = k % 2
        out[ch, sh:] += src[:-sh] * fb ** k
    return out


def compress(x, thresh_db=-16.0, ratio=2.5, release=0.18, makeup_db=0.0):
    mono = np.sqrt(np.mean(x ** 2, axis=0))
    w = int(0.015 * SR)
    c = np.cumsum(np.concatenate([[0.0], mono ** 2]))
    rms = np.sqrt(np.maximum((c[w:] - c[:-w]) / w, 0))
    rms = np.concatenate([np.full(w - 1, rms[0]), rms])[: x.shape[1]]
    lvl = 20 * np.log10(rms + 1e-9)
    gr = -np.maximum(0.0, lvl - thresh_db) * (1 - 1 / ratio)
    a = math.exp(-1 / (release * SR))
    gr = lfilter1([1 - a], [1, -a], gr) if sps is not None else gr
    return x * db(gr + makeup_db)


# ------------------------------------------------------------------- composer
class Composer:
    def __init__(self, tl, cues, args):
        self.tl = tl
        self.music = tl.get("music") or {}
        self.args = args
        style = args.style or self.music.get("style") or "uplifting"
        if style == "none":
            self.style = None
        elif style not in STYLES:
            die(f"unknown style '{style}' ({', '.join(STYLES)})")
        else:
            self.style = STYLES[style]
        self.style_name = style
        self.seed = int(args.seed if args.seed is not None else self.music.get("seed", 1))
        self.rng = np.random.default_rng(self.seed)
        self.kit = Kit(np.random.default_rng(self.seed + 11))
        self.syn = Synth(np.random.default_rng(self.seed + 23), bright=float(self.music.get("brightness", 1.0)))
        self.dur = float(tl["duration"])
        self.bpm = float(self.music.get("bpm") or 110)
        self.beat = 60.0 / self.bpm
        self.s16 = self.beat / 4
        st = self.style or STYLES["uplifting"]
        self.mode = self.music.get("mode") or st["mode"]
        if self.mode not in MODES:
            die(f"unknown mode '{self.mode}'")
        key = str(self.music.get("key") or st["keys"][self.seed % len(st["keys"])]).upper()
        if key.endswith("M") and len(key) > 1 and key[:-1] in NOTE:
            key = key[:-1]
        if key not in NOTE:
            die(f"unknown key '{key}'")
        self.key = key[0] + key[1:].lower()
        self.root = NOTE[key]
        self.scale = MODES[self.mode]
        self.scenes = tl["scenes"]
        self.cues = cues or []
        self.voice = bool((tl.get("voice") or {}).get("lines"))
        self.lead_ok = self.music.get("lead", not self.voice)
        n = len(self.scenes)
        for i, s in enumerate(self.scenes):
            if s.get("energy") is None:
                s["_e"] = 0.42 if i == 0 else (0.62 if i == n - 1 else 0.6 + 0.25 * (i / max(1, n - 1)))
            else:
                s["_e"] = float(s["energy"])
        ending = self.music.get("ending") or ("ringout" if self.style_name in ("ambient", "piano") else "sting")
        self.ending = ending
        self.sting_t = None
        last = self.scenes[-1]
        if ending in ("sting", "ringout"):
            self.sting_t = float(self.music.get("sting_at", last["start"]))
        for s in self.scenes:
            if s.get("music") == "sting":
                self.sting_t = float(s["start"])
                self.ending = "sting"
        self.mix = Mixer(self.dur)
        self.kicks = []
        self.events = []

    # --- musical helpers
    def deg_midi(self, deg, octave):
        o, d = divmod(deg, 7)
        return 12 * (octave + 1 + o) + self.root + self.scale[d]

    def chord(self, deg, octave=4, sevenths=False, ninths=False):
        ds = [deg, deg + 2, deg + 4] + ([deg + 6] if sevenths else []) + ([deg + 8] if ninths else [])
        return [self.deg_midi(d, octave) for d in ds]

    def scene_at(self, t):
        for s in reversed(self.scenes):
            if t >= s["start"] - 1e-6:
                return s
        return self.scenes[0]

    def energy(self, t):
        s = self.scene_at(t)
        if s.get("music") == "stop":
            return 0.0
        if s.get("music") == "soft":
            return min(s["_e"], 0.35)
        return s["_e"]

    def chord_at(self, t, prog, bpc):
        bar = int(t // (self.beat * 4))
        if self.sting_t is not None:
            sbar = int(round(self.sting_t / (self.beat * 4)))
            if bar >= sbar:
                return 0
            if bar == sbar - 1 and self.style:
                return self.style.get("cad", 4)
        return prog[(bar // bpc) % len(prog)]

    def swing(self, k):
        sw = (self.style or {}).get("swing", 0)
        if sw and k % 2 == 1:
            return (sw - 0.5) * 2 * self.s16
        return 0.0

    def tonal_midi(self, octave=6, step=0):
        return self.deg_midi(step % 7 + 7 * (step // 7), octave)

    # --- composition
    def compose(self):
        if self.style is None:
            return
        st = self.style
        prog = st["progs"][self.seed % len(st["progs"])]
        bpc = st["bpc"]
        sev = st.get("sevenths", False)
        steps = int(math.ceil(self.dur / self.s16))
        after = lambda t: self.sting_t is not None and t >= self.sting_t - 1e-6  # noqa: E731
        end_drums = self.dur - (self.beat if self.ending == "button" else 0)
        hum = lambda: self.rng.normal(0, 0.0035)  # noqa: E731
        vel = lambda base: float(np.clip(base * (1 + self.rng.normal(0, 0.07)), 0.05, 1.2))  # noqa: E731
        drums = DRUMS.get(st["drums"]) if st["drums"] else None
        bass_kind, bass_pat = st["bass"] if st["bass"] else (None, None)

        # drums + bass + rhythmic parts on the 16th grid
        for k in range(steps):
            t = k * self.s16 + self.swing(k)
            if t >= self.dur:
                break
            E = self.energy(t)
            s16 = k % 16
            if after(t) or t >= end_drums:
                continue
            first_in_scene = abs(t - self.scene_at(t)["start"]) < 1e-6
            if drums:
                for name, (pat, emin) in drums.items():
                    ch = pat[s16]
                    if ch == "." or E < emin:
                        continue
                    if self.scene_at(t) is self.scenes[0] and E < 0.5 and name in ("kick", "clap", "snare", "taiko"):
                        continue  # keep the hook light
                    v = 1.0 if ch == "x" else 0.45
                    v *= 0.75 + 0.35 * E
                    self.hit(name, t + (0 if s16 == 0 else hum()), vel(v))
            if bass_kind and E >= 0.32:
                ch = BASS_PAT[bass_pat][s16]
                if ch == "x":
                    deg = self.chord_at(t, prog, bpc)
                    nxt = BASS_PAT[bass_pat][s16 + 1:] + "x"
                    length = (nxt.index("x") + 1) * self.s16
                    oct_ = 1 if bass_kind in ("808", "sub") else 2
                    m = self.deg_midi(deg, oct_)
                    if bass_pat == "chip" and (k // 2) % 2:
                        m += 12
                    if bass_pat == "pop" and s16 in (6, 12) and E > 0.6:
                        m += 12
                    gain = db(-4) * (0.7 + 0.3 * E)
                    self.mix.add("bass", self.syn.bass(bass_kind, m, length * 0.92, 1.0), t, gain, 0.0, 0.03)
            self.comp_step(st, k, t, E, prog, bpc, sev, first_in_scene)

        # pads per chord span
        if st.get("pad"):
            span = self.beat * 4 * bpc
            t = 0.0
            while t < self.dur:
                E = self.energy(t)
                deg = self.chord_at(t + 1e-6, prog, bpc)
                end = min(self.dur, t + span)
                if after(t):
                    end = self.dur
                if self.sting_t is not None and t < self.sting_t < end:
                    end = self.sting_t
                notes = self.voiced(deg, sev)
                g = db(-9) * (0.55 + 0.45 * min(1.0, E + 0.2))
                if self.scene_at(t).get("music") == "stop":
                    g *= 0.35
                if after(t):
                    g = db(-8)
                buf = self.syn.pad(st["pad"], notes, end - t + 0.05, 1.0)
                self.mix.add("pads", buf, t, g, 0.0, 0.35)
                t = end

        self.transitions(prog, bpc)
        self.ending_events(prog, bpc)
        if st.get("vinyl"):
            self.vinyl()

    def voiced(self, deg, sev):
        base = self.chord(deg, 3, sevenths=sev)
        center = 12 * 5 + self.root - 7
        out = []
        for m in base:
            while m < center - 6:
                m += 12
            while m > center + 8:
                m -= 12
            out.append(m)
        return sorted(set(out))

    def comp_step(self, st, k, t, E, prog, bpc, sev, first):
        s16 = k % 16
        deg = self.chord_at(t, prog, bpc)
        comp = st.get("comp")
        notes = self.chord(deg, 4, sevenths=sev)
        if comp == "pluck" and E >= 0.3 and s16 % 2 == 0:
            order = [0, 1, 2, 1, 3 if len(notes) > 3 else 2, 1, 2, 0]
            m = notes[order[(s16 // 2) % 8] % len(notes)] + (12 if s16 >= 8 and E > 0.7 else 0)
            v = 0.8 if s16 in (0, 6, 12) else 0.55
            self.mix.add("keys", self.syn.pluck(m, self.s16 * 1.6, v), t, db(-9), 0.25 if s16 % 4 else -0.25, 0.3)
        elif comp == "epiano" and E >= 0.2 and s16 in (0, 7, 10):
            dur = self.s16 * (6 if s16 == 0 else 3)
            for i, m in enumerate(self.voiced(deg, True)):
                self.mix.add("keys", self.syn.epiano(m, dur, 0.75 if s16 == 0 else 0.5, trem=0.12), t + i * 0.006, db(-11), 0.0, 0.3)
        elif comp == "guitar" and E >= 0.25:
            pat = "D...D.U...U.D.U."
            ch = pat[s16]
            if ch != ".":
                strum = self.voiced(deg, False) + [self.deg_midi(deg, 4) + 12]
                strum = sorted(strum)
                if ch == "U":
                    strum = strum[::-1][:3]
                for i, m in enumerate(strum):
                    self.mix.add("keys", self.syn.ks(m, self.s16 * 3.5, 0.55 if ch == "U" else 0.8, bright=0.45),
                                 t + i * 0.011, db(-8), -0.2 + 0.1 * i, 0.25)
        elif comp == "bell" and E >= 0.15 and s16 in (0, 10):
            m = notes[(k // 16 + (1 if s16 == 10 else 0)) % len(notes)] + 12
            self.mix.add("keys", self.syn.bell(m, 1.0, 0.6), t, db(-13), 0.3 if s16 else -0.3, 0.55)
        elif comp == "piano" and E >= 0.1:
            lh = self.deg_midi(deg, 2)
            rh = self.voiced(deg, False)
            if s16 == 0:
                self.mix.add("keys", self.syn.piano(lh, self.beat * 3.5, 0.75), t, db(-6), -0.15, 0.3)
            if s16 % 2 == 0 and s16:
                m = rh[(s16 // 2 - 1) % len(rh)] + (12 if s16 >= 8 else 0)
                self.mix.add("keys", self.syn.piano(m, self.s16 * 3, 0.45 + 0.1 * (s16 == 8)), t + self.rng.normal(0, 0.004), db(-9), 0.15, 0.32)
        elif comp == "ostinato" and E >= 0.5 and s16 % 2 == 0:
            m = self.deg_midi(deg, 3) + (12 if s16 % 8 == 4 else 0)
            self.mix.add("keys", self.syn.pluck(m, self.s16 * 1.7, 0.6, shape="saw"), t, db(-12), 0.0, 0.3)
        # arps
        arp = st.get("arp")
        if arp and E >= 0.58:
            if arp == "bell":
                if s16 in (0, 3, 6, 10, 12):
                    seq = self.chord(deg, 5)
                    self.mix.add("arp", self.syn.bell(seq[(k // 3) % len(seq)], 0.5, 0.5), t, db(-16 if self.voice else -13), 0.35, 0.4)
            else:
                seq = notes + [notes[0] + 12]
                m = seq[k % len(seq)] + 12
                buf = self.syn.square(m, self.s16 * 0.8, 0.6, vib=False) if arp == "square" else self.syn.pluck(m, self.s16 * 0.9, 0.5)
                self.mix.add("arp", buf, t, db(-17 if self.voice else -14), 0.45 if k % 2 else -0.45, 0.25)
        # lead hook at high energy
        lead = st.get("lead")
        if lead and self.lead_ok and E >= 0.78:
            self.lead_step(lead, k, t, deg)

    def lead_step(self, lead, k, t, deg):
        if not hasattr(self, "_motif"):
            cells = [[(0, 3), (3, 1), (4, 2), (6, 2), (8, 4), (12, 4)], [(0, 2), (2, 2), (4, 4), (10, 2), (12, 4)],
                     [(0, 6), (6, 2), (8, 2), (10, 2), (12, 4)], [(2, 2), (4, 2), (6, 2), (8, 6), (14, 2)]]
            shapes = [[0, 1, 2, 1, 0, -1], [2, 1, 0, 1, 2, 4], [0, 2, 1, 3, 2, 0], [4, 2, 1, 0, 1, 2]]
            self._motif = (cells[self.seed % 4], shapes[(self.seed // 4) % 4])
        cell, shape = self._motif
        s16 = k % 16
        for i, (pos, ln) in enumerate(cell):
            if pos == s16:
                bar = k // 16
                step = shape[i % len(shape)] + (2 if bar % 4 == 3 else 0)
                m = self.deg_midi(deg + step, 5)
                if ln >= 2:  # long notes land on chord tones
                    tones = self.chord(deg, 5) + [x + 12 for x in self.chord(deg, 5)]
                    m = min(tones, key=lambda x: abs(x - m))
                dur = ln * self.s16
                if lead == "square":
                    buf = self.syn.square(m, dur * 0.95, 0.7)
                elif lead == "bell":
                    buf = self.syn.bell(m, dur, 0.6)
                elif lead == "epiano":
                    buf = self.syn.epiano(m + 12, dur, 0.6)
                else:
                    buf = self.syn.pluck(m, dur, 0.65)
                self.mix.add("lead", buf, t, db(-10), 0.1, 0.35)

    def hit(self, name, t, v):
        kit = self.kit
        if name == "kick":
            self.kicks.append(t)
            self.mix.add("drums", kit.kick(v), t, db(-2), 0.0, 0.0)
        elif name == "snare":
            self.mix.add("drums", kit.snare(v), t, db(-6), 0.05, 0.12)
        elif name == "clap":
            self.mix.add("drums", kit.clap(v), t, db(-6), -0.05, 0.18)
        elif name in ("hat", "hat16"):
            self.mix.add("drums", kit.hat(v), t, db(-13 if name == "hat" else -17), 0.35, 0.05)
        elif name == "openhat":
            self.mix.add("drums", kit.hat(v, True), t, db(-16), 0.35, 0.08)
        elif name == "shaker":
            self.mix.add("drums", kit.shaker(v), t, db(-15), -0.4, 0.06)
        elif name == "tamb":
            self.mix.add("drums", kit.tamb(v), t, db(-15), 0.45, 0.1)
        elif name == "taiko":
            self.mix.add("drums", kit.taiko(v), t, db(-4), -0.15, 0.35)
        elif name == "taiko_lo":
            self.kicks.append(t)
            self.mix.add("drums", kit.taiko(v, low=True), t, db(-3), 0.15, 0.35)
        elif name == "perc":
            self.mix.add("drums", kit.perc(v), t, db(-14), 0.4, 0.25)
        elif name == "crash":
            self.mix.add("drums", kit.crash(v), t, db(-9), 0.25, 0.2)

    def transitions(self, prog, bpc):
        sc = self.scenes
        for i in range(len(sc) - 1):
            a, b = sc[i], sc[i + 1]
            t1 = b["start"]
            if self.sting_t is not None and t1 >= self.sting_t - 1e-6:
                continue
            ea, eb = self.energy(a["start"] + 0.01), self.energy(t1 + 0.01)
            build = a.get("music") == "build" or (eb - ea >= 0.25 and a["dur"] >= 1.4)
            if build:
                L = min(self.beat * 4, a["dur"] * 0.7)
                if self.style_name in ("piano", "ambient", "lofi", "acoustic"):
                    self.mix.add("fx", sfx_swell(L, self, self.chord_at(t1 + 1e-3, prog, bpc)), t1 - L, db(-10), 0.0, 0.3)
                else:
                    self.mix.add("fx", sfx_riser(L, self), t1 - L, db(-12), 0.0, 0.25)
                if self.style.get("drums") in ("pop", "house", "chip", "acoustic", "lofi", "trap") and eb >= 0.45:
                    n = 4 if self.bpm > 105 else 2
                    for j in range(n):
                        tt = t1 - self.beat + j * (self.beat / n)
                        self.mix.add("drums", self.kit.snare(0.25 + 0.6 * j / n), tt, db(-10), 0.0, 0.15)
            near_sting = self.sting_t is not None and 0 < self.sting_t - t1 < 2.6
            if b.get("music") in ("drop", "hit") or (eb - ea >= 0.25 and not near_sting):
                if self.style_name in ("ambient", "piano"):
                    # gentle styles: a bell on the tonic instead of a cymbal
                    self.mix.add("keys", self.syn.bell(self.deg_midi(self.chord_at(t1 + 1e-3, prog, bpc), 6), 1.5, 0.7),
                                 t1, db(-12), 0.2, 0.5)
                else:
                    self.hit("crash", t1, (0.9 if b.get("music") == "drop" else 0.65) * (0.6 if self.style_name in ("lofi", "acoustic") else 1.0))
                if b.get("music") == "drop":
                    self.mix.add("fx", sfx_impact(self, 1.0), t1, db(-8), 0.0, 0.25)
                    self.hit("kick", t1, 1.0)
            if a.get("music") == "stop" and self.style_name not in ("ambient", "piano"):
                self.hit("crash", t1, 0.8)

    def ending_events(self, prog, bpc):
        st = self.style
        if self.sting_t is not None and self.ending == "sting":
            t = self.sting_t
            self.hit("kick", t, 1.05)
            self.hit("crash", t, 1.0)
            self.mix.add("fx", sfx_impact(self, 0.9), t, db(-10), 0.0, 0.3)
            notes = self.chord(0, 4, sevenths=st.get("sevenths", False))
            for i, m in enumerate(notes + [notes[0] + 12]):
                buf = self.syn.piano(m, 2.5, 0.8) if st.get("comp") == "piano" else self.syn.epiano(m, 2.0, 0.85) \
                    if st.get("comp") == "epiano" else self.syn.pluck(m, 1.5, 0.8) if st.get("comp") in ("pluck", "guitar") \
                    else self.syn.bell(m, 2.0, 0.7)
                self.mix.add("keys", buf, t + i * 0.004, db(-8), -0.3 + 0.2 * i, 0.45)
            if st.get("bass"):
                self.mix.add("bass", self.syn.bass(st["bass"][0], self.deg_midi(0, 1), min(2.5, self.dur - t), 1.0), t, db(-3), 0.0, 0.05)
            self.mix.add("lead", self.syn.bell(self.deg_midi(0, 6), 2.0, 0.55), t + self.beat, db(-16), 0.2, 0.6)
        elif self.sting_t is not None and self.ending == "ringout":
            t = self.sting_t
            notes = self.voiced(0, st.get("sevenths", False))
            for i, m in enumerate(notes + [notes[0] + 12]):
                if st.get("comp") == "piano":
                    buf = self.syn.piano(m, 3.0, 0.55)
                elif st.get("comp") == "epiano":
                    buf = self.syn.epiano(m, 2.5, 0.55)
                else:
                    buf = self.syn.bell(m + 12, 2.5, 0.45)
                self.mix.add("keys", buf, t + i * 0.09, db(-9), -0.3 + 0.15 * i, 0.5)
            if st.get("bass"):
                self.mix.add("bass", self.syn.bass("sub", self.deg_midi(0, 1), min(3.0, self.dur - t), 0.8), t, db(-5), 0.0, 0.05)
        elif self.ending == "button":
            t = self.dur - self.beat
            self.hit("kick", t, 1.0)
            for m in self.chord(0, 4):
                self.mix.add("keys", self.syn.pluck(m, self.beat * 0.6, 0.9), t, db(-8), 0.0, 0.2)

    def vinyl(self):
        n = int(self.dur * SR)
        r = np.random.default_rng(self.seed + 5)
        x = lp(r.standard_normal(n), 5000) * 0.004
        idx = r.integers(0, n, size=int(self.dur * 9))
        x[idx] += r.uniform(-0.35, 0.35, size=len(idx))
        x = bp(x, 400, 9000)
        self.mix.add("fx", np.vstack([x, np.roll(x, 37)]), 0, db(-12))

    # --- sound effects (separate stem)
    def sfx_events(self):
        items = []
        for x in self.tl.get("sfx", []):
            items.append(dict(x, t=scene_abs(self.tl, x)))
        for c in self.cues:
            items.append(dict(c))
        if (self.tl.get("music") or {}).get("auto_sfx", True):
            for s in self.scenes[1:]:
                tr = s.get("transition")
                typ = tr if isinstance(tr, str) else (tr or {}).get("type", "cut")
                if typ == "whip":
                    items.append({"t": s["start"] - 0.12, "type": "whoosh", "gain": -4})
                elif typ in ("slide", "push", "zoom"):
                    items.append({"t": s["start"] - 0.05, "type": "swoosh", "gain": -8})
                elif typ == "flash":
                    items.append({"t": s["start"], "type": "hit", "gain": -6})
                elif typ == "wipe":
                    items.append({"t": s["start"], "type": "swipe", "gain": -10})
        items.sort(key=lambda x: x["t"])
        last_pop, pop_step = -9.0, 0
        for it in items:
            typ = ALIASES.get(it["type"], it["type"])
            t = float(it["t"])
            if t < 0 or t > self.dur + 0.5:
                continue
            g = db(float(it.get("gain", 0)))
            if typ == "pop":
                pop_step = pop_step + 1 if t - last_pop < 1.2 else 0
                last_pop = t
                it["_step"] = pop_step
            buf = make_sfx(typ, self, it)
            if buf is None:
                log(f"music: unknown sfx '{it['type']}' (known: {', '.join(SFX_NAMES)})")
                continue
            lead_in = {"whoosh": 0.35, "swoosh": 0.18, "swipe": 0.1, "riser": float(it.get("dur", 2.0))}.get(typ, 0.0)
            pan = float(it.get("pan", 0.0))
            self.mix.add("sfx", buf, t - lead_in, g * db(SFX_GAIN.get(typ, -12)), pan, 0.18, space="sfx")
            self.events.append({"t": round(t, 3), "type": typ})

    # --- mixdown
    def render(self):
        if self.style is not None:
            self.compose()
        self.sfx_events()
        mx = self.mix
        n = mx.n
        if self.style and self.style.get("side") and self.kicks:
            depth = self.style["side"]
            imp = np.zeros(n)
            for t in self.kicks:
                i = int(t * SR)
                if i < n:
                    imp[i] = 1.0
            ker = np.exp(-T(int(0.25 * SR)) / 0.09)
            env = np.clip(conv(imp, ker)[:n], 0, 1)
            duck = 1 - depth * env
            for b in ("pads", "bass", "arp", "keys"):
                if b in mx.bus:
                    mx.bus[b] *= duck
        if "lead" in mx.bus or "arp" in mx.bus:
            dl = 0.75 * self.beat
            for b in ("lead", "arp"):
                if b in mx.bus:
                    mx.bus[b] = delay_fx(mx.bus[b], dl, fb=0.28)
        ir = make_ir((self.style or {}).get("rt60", 1.6), np.random.default_rng(self.seed + 99))
        music = np.zeros((2, n))
        for b, x in mx.bus.items():
            if b == "sfx":
                continue
            g = {"drums": 1.0, "bass": 0.95, "pads": 0.85, "keys": 0.9, "arp": 0.8, "lead": 0.85, "fx": 0.8}.get(b, 0.9)
            music += x * g
        music += apply_reverb(mx.send.get("music"), ir, n) * 0.55
        music = hp(music, 28)
        sfx = mx.bus.get("sfx", np.zeros((2, n))) + apply_reverb(mx.send.get("sfx"), ir, n) * 0.5
        sfx = hp(sfx, 35)
        # glue + level
        if np.any(music):
            music = compress(music, -18, 2.2, 0.2)
        end = int(self.dur * SR)
        tail = int({"cut": 0.04, "button": 0.04}.get(self.ending, 0.0) * SR)
        music = music[:, :end]
        sfx = sfx[:, :end]
        if self.ending == "fade":
            f = int(min(2.5, self.dur * 0.25) * SR)
            music[:, -f:] *= np.linspace(1, 0, f) ** 1.5
        else:
            f = int(0.35 * SR) if not tail else tail
            music[:, -f:] *= np.linspace(1, 0, f)
        sfx[:, -int(0.05 * SR):] *= np.linspace(1, 0, int(0.05 * SR))
        g = float(self.music.get("gain_db", 0))
        music *= db(g)
        return music, sfx


SFX_GAIN = {"whoosh": -8, "swoosh": -10, "swipe": -12, "riser": -12, "downlifter": -12, "impact": -6, "boom": -6,
            "hit": -7, "pop": -10, "click": -12, "tap": -12, "type": -19, "tick": -17, "ding": -12, "chime": -12,
            "sparkle": -14, "success": -12, "error": -12, "notify": -12, "glitch": -12, "shutter": -11, "bubble": -12,
            "thud": -8, "snap": -11, "crash": -12, "stinger": -8}


# ----------------------------------------------------------------------- sfx
def _env_bell(n, peak=0.6, p=2.0):
    x = np.linspace(0, 1, n)
    a = np.clip(x / peak, 0, 1) ** p
    b = np.clip((1 - x) / (1 - peak), 0, 1) ** 1.5
    return np.minimum(a, b)


def sfx_riser(dur, c):
    n = int(dur * SR)
    t = T(n)
    nz = sweep(c.kit.noise(n), "bandpass", 300, 9000, q=1.2)
    f0 = float(mhz(c.deg_midi(0, 3)))
    fr = f0 * 2 ** (2.0 * (t / dur) ** 1.6)
    tone = osc("saw", fr, n, cutoff=4000) * 0.25
    env = (t / dur) ** 2.4
    x = (nz * 0.8 + lp(tone, 3000)) * env
    x[-int(0.01 * SR):] *= np.linspace(1, 0, int(0.01 * SR))
    return np.vstack([x, np.roll(x, 90)]) * 0.9


def sfx_swell(dur, c, deg=0):
    """Tonal reverse swell into the next chord (for gentle styles instead of a noise riser)."""
    n = int(dur * SR)
    t = T(n)
    out = np.zeros(n)
    for m in c.chord(deg, 4) + [c.deg_midi(deg, 5)]:
        f = float(mhz(m))
        out += osc("triangle", f, n, c.rng.random(), cutoff=6000) + 0.4 * np.sin(TAU * f * 2 * t)
    out = lp(out / 4, 3500)
    env = (t / dur) ** 2.8
    out *= env
    out[-int(0.012 * SR):] *= np.linspace(1, 0, int(0.012 * SR))
    return np.vstack([out, np.roll(out, 120)]) * 0.8


def sfx_impact(c, v=1.0, length=2.4):
    n = int(length * SR)
    t = T(n)
    f = 58 * (1 + 0.6 * np.exp(-t * 18))
    sub = np.sin(TAU * np.cumsum(f) / SR) * np.exp(-t * 2.4)
    body = lp(c.kit.noise(n), 2500) * np.exp(-t * 14) * 0.6
    click = hp(c.kit.noise(n), 3000) * np.exp(-t * 180) * 0.2
    x = np.tanh(1.5 * (sub + body + click)) * v
    return np.vstack([x, x])


def make_sfx(typ, c, it):
    k = c.kit
    s = c.syn
    rng = c.rng
    if typ in ("whoosh", "swoosh", "swipe"):
        d = {"whoosh": 0.75, "swoosh": 0.42, "swipe": 0.26}[typ]
        d = float(it.get("dur", d))
        n = int(d * SR)
        lo, hi = {"whoosh": (220, 2600), "swoosh": (450, 3800), "swipe": (1200, 6500)}[typ]
        x = sweep(k.noise(n), "bandpass", lo, hi, q=1.1) * _env_bell(n, 0.55)
        p = np.linspace(-0.8, 0.8, n) * (-1 if it.get("dir") == "left" else 1)
        return np.vstack([x * np.clip(1 - p, 0, 1), x * np.clip(1 + p, 0, 1)]) * 1.4
    if typ == "riser":
        return sfx_riser(float(it.get("dur", 2.0)), c)
    if typ == "downlifter":
        r = sfx_riser(float(it.get("dur", 1.5)), c)
        return r[:, ::-1].copy()
    if typ in ("impact", "boom"):
        return sfx_impact(c, 1.0, 3.0 if typ == "boom" else 2.2)
    if typ == "hit":
        x = k.kick(1.0) * 0.8
        sn = k.snare(0.9)
        out = np.zeros(max(len(x), len(sn)))
        out[:len(x)] += x
        out[:len(sn)] += sn * 0.7
        return out
    if typ == "crash":
        return k.crash(1.0)
    if typ == "pop":
        step = it.get("_step", 0)
        m = c.deg_midi([0, 2, 4, 7, 9, 11, 14][min(step, 6)], 5)
        f = float(mhz(m))
        n = int(0.16 * SR)
        t = T(n)
        fr = f * (0.62 + 0.38 * (1 - np.exp(-t * 90)))
        x = np.sin(TAU * np.cumsum(fr) / SR) * np.exp(-t * 34) * (1 - np.exp(-t * 2500))
        return fade_edges(x * 0.9)
    if typ in ("click", "tap"):
        n = int(0.05 * SR)
        t = T(n)
        if typ == "click":
            x = bp(k.noise(n), 2200, 7000) * np.exp(-t * 650) + np.sin(TAU * 2600 * t) * np.exp(-t * 900) * 0.4
        else:
            x = bp(k.noise(n), 500, 2500) * np.exp(-t * 300) + np.sin(TAU * 900 * t) * np.exp(-t * 400) * 0.5
        return fade_edges(x * 0.8, 0.0002, 0.005)
    if typ in ("type", "tick"):
        n = int(0.035 * SR)
        t = T(n)
        lo = float(rng.uniform(1300, 2600))
        x = bp(k.noise(n), lo, lo * 3.2) * np.exp(-t * float(rng.uniform(380, 650)))
        x += np.sin(TAU * float(rng.uniform(180, 320)) * t) * np.exp(-t * 220) * 0.35
        return fade_edges(x * float(rng.uniform(0.6, 1.0)), 0.0002, 0.004)
    if typ in ("ding", "chime", "notify"):
        if typ == "ding":
            return s.bell(c.deg_midi(0, 6), 1.2, 0.9)
        seq = [c.deg_midi(4, 5), c.deg_midi(7, 5)] if typ == "notify" else [c.deg_midi(2, 6), c.deg_midi(4, 6)]
        out = np.zeros(int(2.4 * SR))
        for i, m in enumerate(seq):
            b = s.bell(m, 1.0, 0.85)
            i0 = int(i * 0.12 * SR)
            out[i0:i0 + len(b)] += b[: len(out) - i0]
        return out
    if typ in ("sparkle", "success"):
        degs = [7, 9, 11, 14, 16] if typ == "sparkle" else [0, 2, 4, 7]
        gap = 0.045 if typ == "sparkle" else 0.075
        out = np.zeros(int(2.6 * SR))
        for i, d in enumerate(degs):
            b = s.bell(c.deg_midi(d, 5 if typ == "success" else 6), 0.6, 0.7 - 0.06 * i)
            i0 = int(i * gap * SR)
            out[i0:i0 + len(b)] += b[: len(out) - i0]
        return out
    if typ == "error":
        out = np.zeros(int(0.42 * SR))
        for i, m in enumerate([c.deg_midi(0, 3) + 1, c.deg_midi(0, 3)]):
            b = s.square(m, 0.14, 0.9, vib=False)
            i0 = int(i * 0.17 * SR)
            out[i0:i0 + len(b)] += b[: len(out) - i0]
        return lp(out, 2500)
    if typ == "glitch":
        n = int(0.35 * SR)
        out = np.zeros(n)
        for i in range(7):
            a = int(rng.uniform(0, n - 1500))
            ln = int(rng.uniform(300, 1800))
            seg = np.sign(np.sin(TAU * rng.uniform(200, 1800) * T(ln))) * 0.5 + k.noise(ln) * 0.3
            out[a:a + ln] += seg[: n - a]
        return hp(out, 300) * 0.5
    if typ == "shutter":
        n = int(0.25 * SR)
        out = np.zeros(n)
        for d0, g in ((0.0, 1.0), (0.09, 0.7)):
            m = int(0.03 * SR)
            i0 = int(d0 * SR)
            out[i0:i0 + m] += bp(k.noise(m), 1500, 6500) * np.exp(-T(m) * 160) * g
        return out * 0.8
    if typ == "bubble":
        n = int(0.14 * SR)
        t = T(n)
        f0 = float(mhz(c.deg_midi(4, 4)))
        x = np.sin(TAU * np.cumsum(f0 * (1 + 1.4 * t / 0.14)) / SR) * np.exp(-t * 26)
        return fade_edges(x * 0.8)
    if typ == "thud":
        n = int(0.4 * SR)
        t = T(n)
        x = np.sin(TAU * np.cumsum(95 * (1 - 0.35 * t / 0.4)) / SR) * np.exp(-t * 14) + lp(k.noise(n), 600) * np.exp(-t * 40) * 0.5
        return fade_edges(x * 0.9)
    if typ == "snap":
        n = int(0.08 * SR)
        t = T(n)
        return fade_edges(bp(k.noise(n), 1600, 4800) * np.exp(-t * 220) * 0.9 + np.sin(TAU * 1900 * t) * np.exp(-t * 300) * 0.2)
    if typ == "stinger":
        imp = sfx_impact(c, 0.9, 2.5)
        bell = s.bell(c.deg_midi(0, 5), 2.0, 0.8)
        out = imp.copy()
        out[:, :len(bell)] += bell[: out.shape[1]] * 0.8
        return out
    return None


# ------------------------------------------------------------- track support
def decode(path, sr=SR):
    ff = need_ffmpeg()
    r = subprocess.run([ff, "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", str(sr), "-"],
                       capture_output=True)
    if r.returncode != 0:
        die(f"could not decode {path}: {r.stderr.decode()[:200]}")
    return np.frombuffer(r.stdout, dtype=np.float32).reshape(-1, 2).T.astype(np.float64)


def analyze(path):
    """Tempo and beat phase of an audio file: spectral-flux onsets, then a comb search
    over tempo and phase with a mild prior around 115 bpm (resolves half/double tempo)."""
    sr = 22050
    x = decode(path, sr).mean(axis=0)
    hop, win = 256, 1024
    frames = 1 + (len(x) - win) // hop
    if frames < 100:
        die("track too short to analyse")
    idx = np.arange(win)[None, :] + hop * np.arange(frames)[:, None]
    S = np.log1p(20 * np.abs(np.fft.rfft(x[idx] * np.hanning(win), axis=1)))
    flux = np.maximum(0, np.diff(S, axis=0)).sum(axis=1)
    flux = np.convolve(flux, np.hanning(5) / 2.5, mode="same")
    flux = (flux - flux.mean()) / (flux.std() + 1e-9)
    fps = sr / hop
    grid = np.arange(len(flux))
    latency = 0.042  # STFT framing delay, calibrated on click tracks

    def prior(bpm):
        return math.exp(-0.5 * (math.log2(bpm / 115.0) / 0.8) ** 2)

    def comb(bpm, step):
        period = fps * 60 / bpm
        best = (-1e9, 0.0)
        for ph in np.arange(0, period, step):
            sc = float(np.interp(np.arange(ph, len(flux) - 1, period), grid, flux).mean())
            if sc > best[0]:
                best = (sc, float(ph))
        return best

    coarse = sorted((comb(b, 2.0)[0] * prior(b), float(b)) for b in np.arange(60, 180.01, 0.5))[-3:]
    best = None
    for _, b0 in coarse:
        for b in np.arange(b0 - 0.6, b0 + 0.601, 0.02):
            sc, ph = comb(b, 0.25)
            sc *= prior(b)
            if best is None or sc > best[0]:
                best = (sc, float(b), ph)
    _, bpm, ph = best
    beat = 60.0 / bpm
    first = (ph / fps + latency) % beat
    if first > beat - 0.03:
        first -= beat
    return {"bpm": round(bpm, 2), "first_beat": round(max(0.0, first), 3), "beat": round(beat, 4),
            "duration": round(len(x) / sr, 2)}


def use_track(comp_tl, spec, comp):
    path = Path(spec["file"])
    if not path.is_absolute():
        path = comp / path
    x = decode(path)
    off = int(float(spec.get("offset", 0)) * SR)
    dur = float(comp_tl["duration"])
    n = int(dur * SR)
    x = x[:, off:off + n]
    if x.shape[1] < n:
        x = np.concatenate([x, np.zeros((2, n - x.shape[1]))], axis=1)
    f = int(min(1.5, dur * 0.2) * SR)
    x[:, -f:] *= np.linspace(1, 0, f) ** 1.5
    return x * db(float(spec.get("gain_db", 0)))


# ----------------------------------------------------------------------- io
def write_wav(path, x):
    x = np.asarray(x, dtype=np.float64)
    dither = (np.random.default_rng(0).random(x.shape) - np.random.default_rng(1).random(x.shape)) / 32768.0
    pcm = np.clip(x + dither, -1, 1)
    pcm = (pcm.T * 32767.0).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def peak_norm(x, peak_db=-1.0):
    p = np.max(np.abs(x)) if x.size else 0
    return x * (db(peak_db) / p) if p > 1e-9 else x


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("comp", nargs="?", help="composition folder (with timeline.json)")
    ap.add_argument("--style", help="override music.style: " + ", ".join(STYLES) + ", none")
    ap.add_argument("--seed", type=int, help="different seed = different song in the same style")
    ap.add_argument("--out-dir", help="default: COMP/audio")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--analyze", metavar="AUDIO", help="print tempo/first beat of an audio file")
    args = ap.parse_args()
    if args.list:
        print(json.dumps({"styles": list(STYLES) + ["none"], "sfx": SFX_NAMES, "aliases": ALIASES,
                          "scene_hints": ["build", "drop", "stop", "hit", "sting", "soft"],
                          "endings": ["sting", "ringout", "fade", "button", "cut"]}, indent=2))
        return
    if args.analyze:
        print(json.dumps(analyze(args.analyze), indent=2))
        return
    if not args.comp:
        ap.error("COMP is required")
    comp = Path(args.comp)
    tl = load_timeline(comp)
    if not tl.get("scenes"):
        die("timeline.json has no scenes")
    normalize_timeline(tl)
    cues = load_json(comp / "cues.json", []) or []
    out = Path(args.out_dir) if args.out_dir else comp / "audio"
    out.mkdir(parents=True, exist_ok=True)
    c = Composer(tl, cues, args)
    track = (tl.get("music") or {}).get("track")
    if track:
        c.style = None
    music, sfx = c.render()
    if track:
        music = use_track(tl, track, comp)
        log(f"music: using supplied track {track['file']}")
    music = peak_norm(music, -3.0) if np.any(music) else music
    mix = music + sfx
    pk = np.max(np.abs(mix)) if mix.size else 0
    if pk > db(-1.0):
        scale = db(-1.0) / pk
        music, sfx, mix = music * scale, sfx * scale, mix * scale
    write_wav(out / "music.wav", music)
    write_wav(out / "sfx.wav", sfx)
    write_wav(out / "soundtrack.wav", mix)
    info = {"style": c.style_name if not track else "track", "bpm": c.bpm, "key": f"{c.key} {c.mode}", "seed": c.seed,
            "ending": c.ending, "sting_at": c.sting_t, "duration": c.dur, "sfx": c.events,
            "files": {k: str(out / f"{k}.wav") for k in ("music", "sfx", "soundtrack")}}
    write_json(out / "music.json", info)
    print(json.dumps({k: info[k] for k in ("style", "bpm", "key", "ending", "duration", "files")} | {"sfx_count": len(c.events)}, indent=2))


if __name__ == "__main__":
    main()
