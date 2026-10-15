#!/usr/bin/env node
"use strict";
const fs = require("fs");
const os = require("os");
const path = require("path");
const zlib = require("zlib");
const { spawnSync } = require("child_process");

const NAME = "onevideo";
const ROOT = path.resolve(__dirname, "..");
const PAYLOAD = ["SKILL.md", "README.md", "LICENSE", "references", "scripts", "assets"];
const SKIP = new Set([".DS_Store", "__pycache__", ".git", "node_modules"]);
const VERSION = require(path.join(ROOT, "package.json")).version;

const HELP = `onevideo ${VERSION} - prompt-to-video skill for Claude

Usage: npx onevideo [command] [options]

Commands
  install      Install the skill into Claude Code (default)
  desktop      Build onevideo.mcpb for Claude Desktop and open it (one click: press Install).
               --zip builds onevideo.skill / onevideo.zip for claude.ai / Settings > Capabilities > Skills instead
  uninstall    Remove the installed skill
  setup        pip-install the Python dependencies (playwright, numpy; --full adds scipy, kokoro-onnx)
  doctor       Check this machine (Python, FFmpeg, browser, fonts, voice)

Options
  --project    Install into ./.claude/skills instead of ~/.claude/skills
  --agents     Install into ~/.agents/skills (Codex, Gemini CLI, Cursor, ...)
  --all        Claude Code + Claude Desktop zip
  --out <dir>  Where 'desktop' writes the file (default: ~/Downloads)
  --no-open    With desktop: build only, do not open the file
  --full       With setup: include optional scipy and kokoro-onnx
  -h, --help   Show this help
`;

const args = process.argv.slice(2);
const flag = (f) => args.includes(f);
const val = (f) => { const i = args.indexOf(f); return i >= 0 ? args[i + 1] : undefined; };
const cmd = args.find((a) => !a.startsWith("-") && a !== val("--out")) || "install";

const say = (m = "") => console.log(m);
const die = (m) => { console.error(`onevideo: ${m}`); process.exit(1); };

function listFiles(rel = "") {
  const out = [];
  for (const p of PAYLOAD) {
    const abs = path.join(ROOT, p);
    if (!fs.existsSync(abs)) continue;
    walk(abs, p, out);
  }
  return out;
}
function walk(abs, rel, out) {
  if (SKIP.has(path.basename(abs))) return;
  const st = fs.statSync(abs);
  if (st.isDirectory()) {
    for (const f of fs.readdirSync(abs).sort()) walk(path.join(abs, f), `${rel}/${f}`, out);
  } else out.push({ abs, rel, mode: st.mode });
}

function install(base, label) {
  const dest = path.join(base, NAME);
  fs.rmSync(dest, { recursive: true, force: true });
  for (const f of listFiles()) {
    const to = path.join(dest, f.rel);
    fs.mkdirSync(path.dirname(to), { recursive: true });
    fs.copyFileSync(f.abs, to);
    fs.chmodSync(to, f.mode & 0o777);
  }
  say(`  [ok] ${label}: ${dest}`);
}

// --- minimal zip writer (deflate), no dependencies ---
const CRC = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
const crc32 = (b) => { let c = 0xffffffff; for (let i = 0; i < b.length; i++) c = CRC[(c ^ b[i]) & 0xff] ^ (c >>> 8); return (c ^ 0xffffffff) >>> 0; };

function buildZip(files) {
  const locals = [], central = [];
  let offset = 0;
  for (const f of files) {
    const name = Buffer.from(f.rel);
    const data = fs.readFileSync(f.abs);
    const comp = zlib.deflateRawSync(data, { level: 9 });
    const crc = crc32(data);
    const h = Buffer.alloc(30);
    h.writeUInt32LE(0x04034b50, 0); h.writeUInt16LE(20, 4); h.writeUInt16LE(0x0800, 6); h.writeUInt16LE(8, 8);
    h.writeUInt16LE(0, 10); h.writeUInt16LE(0x21, 12); // fixed 1980-01-01 for reproducible zips
    h.writeUInt32LE(crc, 14); h.writeUInt32LE(comp.length, 18); h.writeUInt32LE(data.length, 22);
    h.writeUInt16LE(name.length, 26);
    locals.push(h, name, comp);
    const c = Buffer.alloc(46);
    c.writeUInt32LE(0x02014b50, 0); c.writeUInt16LE(0x031e, 4); c.writeUInt16LE(20, 6); c.writeUInt16LE(0x0800, 8); c.writeUInt16LE(8, 10);
    c.writeUInt16LE(0, 12); c.writeUInt16LE(0x21, 14);
    c.writeUInt32LE(crc, 16); c.writeUInt32LE(comp.length, 20); c.writeUInt32LE(data.length, 24);
    c.writeUInt16LE(name.length, 28); c.writeUInt32LE(((0o100000 | (f.mode & 0o777)) << 16) >>> 0, 38);
    c.writeUInt32LE(offset, 42);
    central.push(c, name);
    offset += h.length + name.length + comp.length;
  }
  const cd = Buffer.concat(central);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(files.length, 8); end.writeUInt16LE(files.length, 10);
  end.writeUInt32LE(cd.length, 12); end.writeUInt32LE(offset, 16);
  return Buffer.concat([...locals, cd, end]);
}

function desktop() {
  const dir = path.resolve(val("--out") || path.join(os.homedir(), "Downloads"));
  fs.mkdirSync(dir, { recursive: true });
  if (flag("--zip")) {
    const data = buildZip(listFiles().map((f) => ({ ...f, rel: `${NAME}/${f.rel}` })));
    for (const ext of ["skill", "zip"]) fs.writeFileSync(path.join(dir, `${NAME}.${ext}`), data);
    say(`  [ok] Skill package: ${path.join(dir, NAME)}.skill (and .zip, same file)`);
    say("       claude.ai or Claude Desktop > Settings > Capabilities > Skills > Upload skill. Code execution must be on.");
    return;
  }
  const mcpbDir = path.join(ROOT, "mcpb");
  const manifest = JSON.parse(fs.readFileSync(path.join(mcpbDir, "manifest.json"), "utf8"));
  manifest.version = VERSION;
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "onevideo-"));
  fs.writeFileSync(path.join(tmp, "manifest.json"), JSON.stringify(manifest, null, 2));
  const files = [
    { abs: path.join(tmp, "manifest.json"), rel: "manifest.json", mode: 0o644 },
    { abs: path.join(mcpbDir, "server", "index.js"), rel: "server/index.js", mode: 0o644 },
    ...listFiles(),
  ];
  const out = path.join(dir, `${NAME}.mcpb`);
  fs.writeFileSync(out, buildZip(files));
  fs.rmSync(tmp, { recursive: true, force: true });
  say(`  [ok] Claude Desktop extension: ${out}`);
  if (flag("--no-open")) { say("       Double-click it, or drag it into Claude Desktop > Settings > Extensions, then press Install."); return; }
  const opener = process.platform === "darwin" ? ["open", [out]] : process.platform === "win32" ? ["cmd", ["/c", "start", "", out]] : ["xdg-open", [out]];
  const r = spawnSync(opener[0], opener[1], { stdio: "ignore" });
  say(r.status === 0 ? "       Opened in Claude Desktop: press Install." : "       Double-click it, or drag it into Claude Desktop > Settings > Extensions, then press Install.");
}

function python() {
  for (const p of ["python3", "python"]) {
    if (spawnSync(p, ["--version"], { stdio: "ignore" }).status === 0) return p;
  }
  die("Python 3.9+ not found. Install it from https://python.org");
}

function run(py, argv) {
  const r = spawnSync(py, argv, { stdio: "inherit" });
  if (r.status !== 0) process.exit(r.status || 1);
}

if (flag("-h") || flag("--help")) { say(HELP); process.exit(0); }

switch (cmd) {
  case "install": {
    say(`Installing ${NAME} ${VERSION}`);
    const home = os.homedir();
    if (flag("--agents")) install(path.join(home, ".agents", "skills"), "Agent Skills");
    else if (flag("--project")) install(path.join(process.cwd(), ".claude", "skills"), "Claude Code (project)");
    else install(path.join(home, ".claude", "skills"), "Claude Code");
    if (flag("--all")) desktop();
    say();
    say("Next:");
    say("  1. npx onevideo setup     # Python deps (playwright, numpy)");
    say("  2. npx onevideo doctor    # verify FFmpeg + browser");
    say("  3. Restart Claude Code, then: \"Make a 20 second launch video for ...\"");
    say("  Claude Desktop: npx onevideo desktop");
    break;
  }
  case "desktop":
    desktop();
    break;
  case "uninstall": {
    const bases = [path.join(os.homedir(), ".claude", "skills"), path.join(os.homedir(), ".agents", "skills"), path.join(process.cwd(), ".claude", "skills")];
    for (const b of bases) {
      const d = path.join(b, NAME);
      if (fs.existsSync(path.join(d, "SKILL.md"))) { fs.rmSync(d, { recursive: true, force: true }); say(`  removed ${d}`); }
    }
    break;
  }
  case "setup": {
    const py = python();
    const pkgs = ["playwright", "numpy", "imageio-ffmpeg", ...(flag("--full") ? ["scipy", "kokoro-onnx"] : [])];
    run(py, ["-m", "pip", "install", ...pkgs]);
    if (!flag("--no-browser")) run(py, ["-m", "playwright", "install", "chromium"]);
    break;
  }
  case "doctor":
    run(python(), [path.join(ROOT, "scripts", "doctor.py"), ...args.filter((a) => a === "--quick")]);
    break;
  case "help":
    say(HELP);
    break;
  default:
    die(`unknown command '${cmd}'\n\n${HELP}`);
}
