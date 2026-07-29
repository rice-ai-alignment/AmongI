#!/usr/bin/env node
// Among-I Log Viewer — zero-dependency Node server
// Usage: node server.mjs [--port PORT] [--dir LOGS_DIR]
import { createServer } from "node:http";
import { readFile, readdir, stat } from "node:fs/promises";
import { createReadStream } from "node:fs";
import { join, extname } from "node:path";
import { fileURLToPath } from "node:url";

const PORT = parseInt(process.env.PORT || "3000");
const LOGS_DIR = process.env.LOGS_DIR || join(
  fileURLToPath(import.meta.url), "..", "..", "among-i", "logs"
);
const PUBLIC_DIR = join(fileURLToPath(import.meta.url), "..", "public");

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js":   "application/javascript; charset=utf-8",
  ".css":  "text/css; charset=utf-8",
  ".json": "application/json",
  ".jsonl":"application/json",
  ".svg":  "image/svg+xml",
};

// ── API helpers ───────────────────────────────────────────────────

async function parseJSONL(filepath) {
  const events = [];
  try {
    const raw = await readFile(filepath, "utf-8");
    for (const line of raw.split("\n")) {
      const trimmed = line.trim();
      if (trimmed) {
        try { events.push(JSON.parse(trimmed)); } catch { /* skip malformed */ }
      }
    }
  } catch { /* file missing */ }
  return events;
}

async function jsonResponse(res, data, code = 200) {
  res.writeHead(code, { "Content-Type": "application/json" });
  res.end(JSON.stringify(data));
}

// ── API routes ─────────────────────────────────────────────────────

async function listSessions(logsDir) {
  const entries = await readdir(logsDir, { withFileTypes: true });
  const sessions = [];
  for (const e of entries) {
    if (!e.isFile() || !e.name.startsWith("SESSION-") || !e.name.endsWith(".jsonl"))
      continue;
    const fp = join(logsDir, e.name);
    const st = await stat(fp);
    if (st.size === 0) continue;
    sessions.push({ id: e.name.replace(/\.jsonl$/, ""), size: st.size, mtime: st.mtimeMs });
  }
  return sessions.sort((a, b) => b.mtime - a.mtime);
}

async function handleAPI(req, res, logsDir) {
  const url = new URL(req.url, "http://localhost");
  const parts = url.pathname.split("/").filter(Boolean);

  // GET /api/sessions
  if (parts[0] === "api" && parts[1] === "sessions" && !parts[2]) {
    return jsonResponse(res, await listSessions(logsDir));
  }
  // GET /api/sessions/:id
  if (parts[0] === "api" && parts[1] === "sessions" && parts[2]) {
    const sid = parts[2];
    const events = await parseJSONL(join(logsDir, `${sid}.jsonl`));

    // Look for per-game logs in subdirectory
    const gameDir = join(logsDir, sid);
    let games = [];
    try {
      const entries = await readdir(gameDir);
      games = entries
        .filter(f => f.startsWith("GAME-") && f.endsWith(".jsonl"))
        .sort()
        .map(f => ({ id: f.replace(/\.jsonl$/, ""), file: f }));
    } catch { /* no game dir yet */ }

    return jsonResponse(res, { id: sid, events, games });
  }
  // GET /api/sessions/:id/games/:gid
  if (parts[0] === "api" && parts[1] === "sessions" && parts[2] &&
      parts[3] === "games" && parts[4]) {
    const sid = parts[2], gid = parts[4];
    const events = await parseJSONL(join(logsDir, sid, `${gid}.jsonl`));
    return jsonResponse(res, { id: gid, session: sid, events });
  }

  return jsonResponse(res, { error: "not found" }, 404);
}

// ── Static file serving ────────────────────────────────────────────

async function serveStatic(req, res, publicDir) {
  let urlPath = new URL(req.url, "http://localhost").pathname;
  if (urlPath === "/") urlPath = "/index.html";
  const filepath = join(publicDir, urlPath);
  try {
    const content = await readFile(filepath);
    const ext = extname(filepath).toLowerCase();
    res.writeHead(200, { "Content-Type": MIME[ext] || "application/octet-stream" });
    res.end(content);
  } catch {
    res.writeHead(404);
    res.end("Not found");
  }
}

// ── Main ───────────────────────────────────────────────────────────

createServer(async (req, res) => {
  if (req.url.startsWith("/api/")) {
    await handleAPI(req, res, LOGS_DIR);
  } else {
    await serveStatic(req, res, PUBLIC_DIR);
  }
}).listen(PORT, () => {
  const resolved = LOGS_DIR.replace(process.env.HOME || "/home", "~");
  console.log(`\n  Among-I Log Viewer`);
  console.log(`  ─────────────────`);
  console.log(`  Logs:  ${resolved}`);
  console.log(`  Open:  http://localhost:${PORT}`);
  console.log();
});
