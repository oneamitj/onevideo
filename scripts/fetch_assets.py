#!/usr/bin/env python3
"""Fetch free, openly licensed assets into a composition, straight from the npm registry
(reachable in most sandboxes even when Google Fonts and CDNs are blocked). No Node needed.

  fetch_assets.py fonts COMP "Inter" "Noto Sans Hebrew" [--weights 400,700,800] [--variable]
      -> COMP/assets/fonts/*.woff2 + COMP/assets/fonts/fonts.css   (Fontsource, mostly OFL-1.1)
  fetch_assets.py icons COMP check zap leaf [--set lucide|tabler]
      -> COMP/assets/icons/<name>.svg     (Lucide: ISC, Tabler: MIT)
  fetch_assets.py npm COMP three build/three.module.min.js examples/jsm/environments/RoomEnvironment.js
      -> COMP/assets/vendor/three/...     (any package; you check its licence)
  fetch_assets.py search-icons coffee     list matching icon names

Link fonts in index.html with <link rel="stylesheet" href="assets/fonts/fonts.css">.
Licences are recorded in COMP/assets/LICENSES.json; keep it with the project.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import die, log, write_json, load_json  # noqa: E402

REG = "https://registry.npmjs.org/"
_cache: dict[str, bytes] = {}


def http_get(url: str) -> bytes:
    if url in _cache:
        return _cache[url]
    data = None
    if shutil.which("curl"):
        r = subprocess.run(["curl", "-fsSL", "--retry", "2", "--max-time", "120", url], capture_output=True)
        if r.returncode == 0:
            data = r.stdout
    if data is None:
        try:
            with urllib.request.urlopen(url, timeout=120) as f:
                data = f.read()
        except Exception as e:
            die(f"download failed: {url}\n  {e}\n  (no network? use system fonts or files the user provides)")
    _cache[url] = data
    return data


def package(name: str, version: str | None = None):
    meta = json.loads(http_get(REG + urllib.parse.quote(name, safe="@")))
    ver = version or meta["dist-tags"]["latest"]
    if ver not in meta["versions"]:
        die(f"{name}@{ver} not found")
    info = meta["versions"][ver]
    tgz = http_get(info["dist"]["tarball"])
    tar = tarfile.open(fileobj=io.BytesIO(tgz), mode="r:gz")
    return ver, info.get("license", "see package"), tar


def record_license(comp: Path, key: str, value: dict):
    p = comp / "assets" / "LICENSES.json"
    data = load_json(p, {}) or {}
    data[key] = value
    p.parent.mkdir(parents=True, exist_ok=True)
    write_json(p, data)


def slug(family: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")


def fonts(comp: Path, families: list[str], weights: list[str], variable: bool, italic: bool):
    out = comp / "assets" / "fonts"
    out.mkdir(parents=True, exist_ok=True)
    css_all = []
    for fam in families:
        pkg = ("@fontsource-variable/" if variable else "@fontsource/") + slug(fam)
        ver, lic, tar = package(pkg)
        members = {m.name: m for m in tar.getmembers()}
        blocks = []
        if variable:
            cssnames = [n for n in members if re.match(r"package/(index|wght)\.css$", n)]
            cssnames = cssnames[:1]
        else:
            # <weight>.css holds every subset with its unicode-range, so browsers fetch only what text needs
            cssnames = [n for n in members if re.match(r"package/(\d{3})(-italic)?\.css$", n)
                        and re.match(r"package/(\d{3})", n).group(1) in weights
                        and (italic or not n.endswith("-italic.css"))]
        if not cssnames:
            avail = sorted({re.match(r"package/(\d{3})\.css$", n).group(1) for n in members if re.match(r"package/(\d{3})\.css$", n)})
            die(f"{pkg}: none of weights {weights} found (available: {', '.join(avail) or 'variable only, try --variable'})")
        used = set()
        for cn in cssnames:
            css = tar.extractfile(members[cn]).read().decode()
            for blk in re.findall(r"@font-face\s*{[^}]*}", css):
                srcs = re.findall(r"url\(\./files/([^)]+?\.woff2)\)", blk)
                if not srcs:
                    continue
                f = srcs[0]
                blk = re.sub(r"src:[^;]+;", f"src: url(./{f}) format('woff2');", blk)
                blocks.append(blk)
                used.add(f)
        for f in sorted(used):
            m = members.get("package/files/" + f)
            if m:
                (out / f).write_bytes(tar.extractfile(m).read())
        uniq = list(dict.fromkeys(blocks))
        css_all.append(f"/* {fam}: {pkg}@{ver} ({lic}) */\n" + "\n".join(uniq))
        fam_name = re.search(r"font-family:\s*'([^']+)'", uniq[0]).group(1) if uniq else fam
        record_license(comp, pkg, {"version": ver, "license": lic, "files": sorted(used), "css_family": fam_name})
        log(f"fonts: {fam} -> font-family: '{fam_name}' ({len(used)} files, {lic})")
    existing = (out / "fonts.css").read_text() if (out / "fonts.css").exists() else ""
    merged = existing + ("\n" if existing else "") + "\n\n".join(css_all) + "\n"
    (out / "fonts.css").write_text(merged)
    print(json.dumps({"css": str(out / "fonts.css"), "families": families}, indent=2))


ICON_PKG = {"lucide": ("lucide-static", "package/icons/{}.svg", "ISC"),
            "tabler": ("@tabler/icons", "package/icons/outline/{}.svg", "MIT")}


def icons(comp: Path, names: list[str], iset: str):
    pkg, pattern, _ = ICON_PKG[iset]
    ver, lic, tar = package(pkg)
    members = {m.name: m for m in tar.getmembers()}
    out = comp / "assets" / "icons"
    out.mkdir(parents=True, exist_ok=True)
    got, missing = [], []
    for n in names:
        m = members.get(pattern.format(n))
        if not m:
            missing.append(n)
            continue
        (out / f"{n}.svg").write_bytes(tar.extractfile(m).read())
        got.append(n)
    record_license(comp, pkg, {"version": ver, "license": lic, "icons": got})
    print(json.dumps({"saved": [str(out / f"{n}.svg") for n in got], "missing": missing,
                      "hint": "fetch_assets.py search-icons <word> lists names" if missing else ""}, indent=2))


def search_icons(word: str, iset: str):
    pkg, pattern, _ = ICON_PKG[iset]
    _, _, tar = package(pkg)
    pre, suf = pattern.split("{}")
    names = sorted(m.name[len(pre):-len(suf)] for m in tar.getmembers() if m.name.startswith(pre) and m.name.endswith(suf))
    hits = [n for n in names if word.lower() in n]
    print(json.dumps({"set": iset, "matches": hits[:80], "total": len(names)}, indent=2))


def npm_files(comp: Path, spec: str, files: list[str]):
    name, ver = (spec.rsplit("@", 1) if spec.count("@") > (1 if spec.startswith("@") else 0) else (spec, None))
    ver_s, lic, tar = package(name, ver)
    members = {m.name: m for m in tar.getmembers()}
    out = comp / "assets" / "vendor" / name.split("/")[-1]
    saved = []
    for f in files:
        m = members.get("package/" + f.lstrip("/"))
        if not m:
            near = [k[8:] for k in members if k.endswith(Path(f).name)][:5]
            die(f"{name}: {f} not in package" + (f" (did you mean {', '.join(near)}?)" if near else ""))
        dst = out / f
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(tar.extractfile(m).read())
        saved.append(str(dst))
    record_license(comp, name, {"version": ver_s, "license": lic, "files": files})
    print(json.dumps({"package": f"{name}@{ver_s}", "license": lic, "saved": saved}, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("fonts")
    a.add_argument("comp")
    a.add_argument("families", nargs="+")
    a.add_argument("--weights", default="400,700")
    a.add_argument("--variable", action="store_true")
    a.add_argument("--italic", action="store_true")
    b = sub.add_parser("icons")
    b.add_argument("comp")
    b.add_argument("names", nargs="+")
    b.add_argument("--set", default="lucide", choices=list(ICON_PKG))
    c = sub.add_parser("npm")
    c.add_argument("comp")
    c.add_argument("package")
    c.add_argument("files", nargs="+")
    d = sub.add_parser("search-icons")
    d.add_argument("word")
    d.add_argument("--set", default="lucide", choices=list(ICON_PKG))
    args = ap.parse_args()
    if args.cmd == "fonts":
        fonts(Path(args.comp), args.families, [w.strip() for w in args.weights.split(",")], args.variable, args.italic)
    elif args.cmd == "icons":
        icons(Path(args.comp), args.names, args.set)
    elif args.cmd == "npm":
        npm_files(Path(args.comp), args.package, args.files)
    else:
        search_icons(args.word, args.set)


if __name__ == "__main__":
    main()
