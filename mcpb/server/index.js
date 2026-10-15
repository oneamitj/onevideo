#!/usr/bin/env node
"use strict";
// onevideo MCP server (stdio, no dependencies). Packaged in onevideo.mcpb for Claude Desktop.
// It exposes the skill (SKILL.md + references) and lets Claude run its scripts and read/write
// files inside one workspace folder, so Desktop chat can do what Claude Code does with a shell.
const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const SKILL_DIR = path.resolve(__dirname, "..");
let VERSION = "0.0.0";
try { VERSION = JSON.parse(fs.readFileSync(path.join(SKILL_DIR, "manifest.json"), "utf8")).version; } catch (_) {}
const IS_WIN = process.platform === "win32";
const PY = IS_WIN ? "python" : "python3";

function workspace() {
  let w = process.env.ONEVIDEO_WORKSPACE || "";
  if (!w || w.includes("${")) w = path.join(os.homedir(), "onevideo");
  w = path.resolve(w.replace(/^~(?=$|[\\/])/, os.homedir()));
  fs.mkdirSync(w, { recursive: true });
  return w;
}
const WS = workspace();

function inWorkspace(p) {
  const abs = path.resolve(WS, p || ".");
  const rel = path.relative(WS, abs);
  if (rel.startsWith("..") || path.isAbsolute(rel)) throw new Error(`path must stay inside the workspace (${WS}): ${p}`);
  return abs;
}

const INSTRUCTIONS =
  "onevideo makes short videos from a prompt. Before doing anything else call onevideo_guide with no arguments " +
  "and follow the workflow it returns. All files live in the workspace folder; use the onevideo_* tools to run " +
  "scripts, read and write files, and look at images.";

function guideText(topic) {
  const refDir = path.join(SKILL_DIR, "references");
  const refs = fs.existsSync(refDir) ? fs.readdirSync(refDir).filter((f) => f.endsWith(".md")).map((f) => f.slice(0, -3)) : [];
  if (topic === "list") return `Available topics: ${refs.join(", ")}`;
  if (topic) {
    const f = path.join(refDir, `${topic.replace(/\.md$/, "")}.md`);
    if (!fs.existsSync(f) || path.dirname(f) !== refDir) throw new Error(`unknown topic '${topic}'. Available: ${refs.join(", ")}`);
    return fs.readFileSync(f, "utf8");
  }
  const skill = fs.readFileSync(path.join(SKILL_DIR, "SKILL.md"), "utf8").replace(/^---[\s\S]*?---\s*/, "");
  const header = [
    "# How to use this skill in Claude Desktop",
    "",
    `The skill below was written for an agent with a shell. Here you have tools instead. Translate like this:`,
    `- \`python3 SKILL_DIR/scripts/X.py ARGS\`  ->  onevideo_run { script: "X.py", args: [ARGS] }. SKILL_DIR is ${SKILL_DIR}; you never need the path.`,
    `- OUT (the project folder) is a name inside the workspace, e.g. "tidepool". Every path you pass to a tool is relative to the workspace: ${WS}`,
    `- Writing comp/index.html, timeline.json, plan.md ...  ->  onevideo_write_file { path: "tidepool/comp/index.html", content }`,
    `- Reading files  ->  onevideo_read_file / onevideo_list_files`,
    `- "Open the sheet image and look"  ->  onevideo_view_image { path: "tidepool/work/sheet.png" }`,
    `- Long renders: onevideo_run waits ~50 s, then returns a job id. Poll with onevideo_job until it finishes. Do not start the same render twice.`,
    `- "references/foo.md"  ->  onevideo_guide { topic: "foo" }  (topics: ${refs.join(", ")})`,
    `- Before the first video run onevideo_setup once if doctor.py says Python packages are missing.`,
    `- Tell the user where the finished files are (the full path of the workspace folder) and that they can open them in Finder / Explorer.`,
    "",
    "---",
    "",
  ].join("\n");
  return header + skill;
}

// ---- jobs ----
const jobs = new Map();
let jobSeq = 0;

function startJob(cmd, args, cwd, label) {
  const id = String(++jobSeq);
  const job = { id, label, out: "", done: false, code: null, startedAt: Date.now(), proc: null };
  jobs.set(id, job);
  let proc;
  try {
    proc = spawn(cmd, args, { cwd, env: { ...process.env, PYTHONUNBUFFERED: "1", PYTHONIOENCODING: "utf-8" }, windowsHide: true });
  } catch (e) {
    job.out = String(e); job.done = true; job.code = -1; return job;
  }
  job.proc = proc;
  const add = (b) => { job.out += b.toString("utf8"); if (job.out.length > 400000) job.out = "...(truncated)...\n" + job.out.slice(-300000); };
  proc.stdout.on("data", add);
  proc.stderr.on("data", add);
  proc.on("error", (e) => { job.out += `\nfailed to start '${cmd}': ${e.message}${e.code === "ENOENT" ? ` (is ${cmd === PY ? "Python 3.9+" : cmd} installed and on PATH?)` : ""}\n`; job.done = true; job.code = -1; });
  proc.on("close", (c) => { job.done = true; job.code = c; });
  return job;
}

function waitJob(job, seconds, since = 0) {
  return new Promise((resolve) => {
    const end = Date.now() + Math.max(0, seconds) * 1000;
    const tick = () => {
      if (job.done || Date.now() >= end) return resolve(jobReport(job, since));
      setTimeout(tick, 250);
    };
    tick();
  });
}

function jobReport(job, since) {
  const text = job.out.slice(since);
  const tail = text.length > 12000 ? "...(earlier output omitted)...\n" + text.slice(-12000) : text;
  const status = job.done ? `finished, exit code ${job.code}` : `STILL RUNNING (${Math.round((Date.now() - job.startedAt) / 1000)} s). Call onevideo_job { id: "${job.id}" } to keep waiting`;
  job.cursor = job.out.length;
  return `[job ${job.id}: ${job.label}] ${status}\n${tail}`;
}

// ---- tools ----
const str = (d) => ({ type: "string", description: d });
const TOOLS = [
  {
    name: "onevideo_guide",
    description: "Read this FIRST. Returns the onevideo skill (the full workflow for making a video) adapted to these tools. With topic, returns one reference document instead (topic 'list' lists them).",
    inputSchema: { type: "object", properties: { topic: str("Optional reference name, e.g. 'audio', 'motion-design', 'runtime-api', 'storyboards', 'visual-toolkit', 'platforms', 'global', or 'list'.") } },
    run: async (a) => guideText(a.topic),
  },
  {
    name: "onevideo_run",
    description: "Run one of the skill's scripts (doctor.py, new_video.py, timeline.py, voice.py, render.py, music.py, assemble.py, fetch_assets.py) with Python. Paths in args are relative to the workspace. Waits up to wait_seconds, then returns a job id if it is still running.",
    inputSchema: {
      type: "object",
      properties: {
        script: str("Script file name inside scripts/, e.g. 'render.py'."),
        args: { type: "array", items: { type: "string" }, description: "Command line arguments, one per item." },
        wait_seconds: { type: "number", description: "How long to wait before returning a job id (default 50, max 55)." },
      },
      required: ["script"],
    },
    run: async (a) => {
      const name = path.basename(a.script || "");
      const script = path.join(SKILL_DIR, "scripts", name);
      if (!name.endsWith(".py") || name.startsWith("_") || !fs.existsSync(script)) {
        const avail = fs.readdirSync(path.join(SKILL_DIR, "scripts")).filter((f) => f.endsWith(".py") && !f.startsWith("_"));
        throw new Error(`unknown script '${a.script}'. Available: ${avail.join(", ")}`);
      }
      const job = startJob(PY, [script, ...(a.args || [])], WS, `${name} ${(a.args || []).join(" ")}`.trim());
      return waitJob(job, Math.min(a.wait_seconds ?? 50, 55));
    },
  },
  {
    name: "onevideo_job",
    description: "Check or wait for a job started by onevideo_run or onevideo_setup. Returns new output since the last check. kill:true stops it.",
    inputSchema: { type: "object", properties: { id: str("Job id."), wait_seconds: { type: "number", description: "Wait up to this long (default 50, max 55)." }, kill: { type: "boolean" } }, required: ["id"] },
    run: async (a) => {
      const job = jobs.get(String(a.id));
      if (!job) throw new Error(`no job '${a.id}'. Known: ${[...jobs.keys()].join(", ") || "none"}`);
      if (a.kill && !job.done && job.proc) job.proc.kill();
      return waitJob(job, a.kill ? 1 : Math.min(a.wait_seconds ?? 50, 55), job.cursor || 0);
    },
  },
  {
    name: "onevideo_setup",
    description: "Install the Python packages onevideo needs (playwright, numpy, a bundled FFmpeg, plus a Chromium browser). full:true adds scipy and kokoro-onnx for voiceover. Run once, only if doctor.py reports something missing. Returns a job id; poll with onevideo_job.",
    inputSchema: { type: "object", properties: { full: { type: "boolean", description: "Also install scipy and kokoro-onnx." }, skip_browser: { type: "boolean", description: "Skip 'playwright install chromium' (Chrome or Edge already installed)." } } },
    run: async (a) => {
      const pkgs = ["playwright", "numpy", "imageio-ffmpeg", ...(a.full ? ["scipy", "kokoro-onnx"] : [])];
      const steps = [`${PY} -m pip install ${pkgs.join(" ")}`];
      if (!a.skip_browser) steps.push(`${PY} -m playwright install chromium`);
      const job = startJob(IS_WIN ? "cmd" : "sh", IS_WIN ? ["/c", steps.join(" && ")] : ["-c", steps.join(" && ")], WS, "setup");
      return waitJob(job, 50);
    },
  },
  {
    name: "onevideo_write_file",
    description: "Write a text file inside the workspace (creates folders). Use it for comp/index.html, comp/timeline.json, comp/strings/en.json, plan.md, share.txt ...",
    inputSchema: { type: "object", properties: { path: str("Path relative to the workspace, e.g. 'tidepool/comp/index.html'."), content: str("File content.") }, required: ["path", "content"] },
    run: async (a) => {
      const p = inWorkspace(a.path);
      fs.mkdirSync(path.dirname(p), { recursive: true });
      fs.writeFileSync(p, a.content, "utf8");
      return `wrote ${path.relative(WS, p)} (${Buffer.byteLength(a.content)} bytes)`;
    },
  },
  {
    name: "onevideo_read_file",
    description: "Read a text file from the workspace.",
    inputSchema: { type: "object", properties: { path: str("Path relative to the workspace."), max_bytes: { type: "number", description: "Default 60000." } }, required: ["path"] },
    run: async (a) => {
      const p = inWorkspace(a.path);
      const buf = fs.readFileSync(p);
      const max = a.max_bytes || 60000;
      return buf.length > max ? buf.subarray(0, max).toString("utf8") + `\n...(truncated, ${buf.length} bytes total)` : buf.toString("utf8");
    },
  },
  {
    name: "onevideo_list_files",
    description: "List files and folders inside the workspace (one level, or recursive up to 300 entries).",
    inputSchema: { type: "object", properties: { path: str("Folder relative to the workspace (default: the workspace itself)."), recursive: { type: "boolean" } } },
    run: async (a) => {
      const base = inWorkspace(a.path || ".");
      const out = [];
      const walk = (d) => {
        for (const e of fs.readdirSync(d, { withFileTypes: true }).sort((x, y) => x.name.localeCompare(y.name))) {
          if (out.length >= 300) return;
          const full = path.join(d, e.name);
          const rel = path.relative(WS, full);
          if (e.isDirectory()) { out.push(rel + "/"); if (a.recursive) walk(full); }
          else out.push(`${rel}  ${(fs.statSync(full).size / 1024).toFixed(1)} KB`);
        }
      };
      walk(base);
      return `workspace: ${WS}\n` + (out.join("\n") || "(empty)");
    },
  },
  {
    name: "onevideo_view_image",
    description: "Look at a PNG/JPG/GIF/WebP from the workspace (contact sheets, stills, posters).",
    inputSchema: { type: "object", properties: { path: str("Image path relative to the workspace.") }, required: ["path"] },
    run: async (a) => {
      const p = inWorkspace(a.path);
      const ext = path.extname(p).slice(1).toLowerCase();
      const mime = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif", webp: "image/webp" }[ext];
      if (!mime) throw new Error("not an image: " + a.path);
      const size = fs.statSync(p).size;
      if (size > 3.5 * 1024 * 1024) throw new Error(`image is ${(size / 1048576).toFixed(1)} MB, too big to view; render a smaller still`);
      return { content: [{ type: "image", data: fs.readFileSync(p).toString("base64"), mimeType: mime }] };
    },
  },
  {
    name: "onevideo_where",
    description: "Tell the user where the workspace folder is, and open it in Finder / Explorer when open:true.",
    inputSchema: { type: "object", properties: { open: { type: "boolean" }, path: str("Optional subfolder to open.") } },
    run: async (a) => {
      const target = inWorkspace(a.path || ".");
      if (a.open) {
        const cmd = process.platform === "darwin" ? "open" : IS_WIN ? "explorer" : "xdg-open";
        try { spawn(cmd, [target], { detached: true, stdio: "ignore" }).unref(); } catch (_) {}
      }
      return target;
    },
  },
];

const PROMPTS = [
  {
    name: "make_video",
    description: "Make a short video with onevideo",
    arguments: [{ name: "brief", description: "What the video is about, platform, length, feel", required: true }],
    text: (args) => `Use the onevideo tools to make this video. Call onevideo_guide first and follow it.\n\nBrief: ${args.brief || "(ask me)"}`,
  },
];

// ---- JSON-RPC over stdio ----
const send = (m) => process.stdout.write(JSON.stringify(m) + "\n");
const ok = (id, result) => send({ jsonrpc: "2.0", id, result });
const err = (id, code, message) => send({ jsonrpc: "2.0", id, error: { code, message } });

async function handle(msg) {
  const { id, method, params = {} } = msg;
  const isReq = id !== undefined && id !== null;
  try {
    switch (method) {
      case "initialize":
        return ok(id, {
          protocolVersion: params.protocolVersion || "2025-06-18",
          capabilities: { tools: {}, prompts: {} },
          serverInfo: { name: "onevideo", version: VERSION },
          instructions: INSTRUCTIONS,
        });
      case "ping": return ok(id, {});
      case "tools/list":
        return ok(id, { tools: TOOLS.map(({ name, description, inputSchema }) => ({ name, description, inputSchema })) });
      case "tools/call": {
        const tool = TOOLS.find((t) => t.name === params.name);
        if (!tool) return err(id, -32602, `unknown tool ${params.name}`);
        try {
          const r = await tool.run(params.arguments || {});
          return ok(id, typeof r === "string" ? { content: [{ type: "text", text: r }] } : r);
        } catch (e) {
          return ok(id, { isError: true, content: [{ type: "text", text: String(e && e.message || e) }] });
        }
      }
      case "prompts/list":
        return ok(id, { prompts: PROMPTS.map(({ name, description, arguments: a }) => ({ name, description, arguments: a })) });
      case "prompts/get": {
        const p = PROMPTS.find((x) => x.name === params.name);
        if (!p) return err(id, -32602, `unknown prompt ${params.name}`);
        return ok(id, { description: p.description, messages: [{ role: "user", content: { type: "text", text: p.text(params.arguments || {}) } }] });
      }
      case "resources/list": return ok(id, { resources: [] });
      default:
        if (isReq) err(id, -32601, `method not found: ${method}`);
    }
  } catch (e) {
    if (isReq) err(id, -32603, String(e && e.message || e));
  }
}

let buf = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buf += chunk;
  let i;
  while ((i = buf.indexOf("\n")) >= 0) {
    const line = buf.slice(0, i).trim();
    buf = buf.slice(i + 1);
    if (!line) continue;
    try { handle(JSON.parse(line)); } catch (e) { err(null, -32700, "parse error"); }
  }
});
process.stdin.on("end", () => process.exit(0));
