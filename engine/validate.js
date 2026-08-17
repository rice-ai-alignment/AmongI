#!/usr/bin/env node
/**
 * validate.js — Node CLI for the shared config compiler.
 *
 * Usage:
 *   node validate.js path/to/config.json [more-configs...]
 *   node validate.js --schema path/to/schema.json path/to/config.json
 *
 * Exit codes: 0 = valid (no errors), 2 = errors, 1 = warnings only.
 */

const fs = require("fs");
const path = require("path");
const { validateConfig } = require("./schema_compiler.js");

function findSchema() {
  // Look for schema.json next to the script, then in the dashboard public dir
  const candidates = [
    path.join(__dirname, "schema.json"),
    path.join(__dirname, "..", "dashboard", "public", "schema.json"),
  ];
  for (const c of candidates) {
    if (fs.existsSync(c)) return c;
  }
  return null;
}

function main() {
  const args = process.argv.slice(2);
  let schemaPath = null;
  let configs = [];

  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--schema" && args[i + 1]) {
      schemaPath = args[++i];
    } else {
      configs.push(args[i]);
    }
  }

  schemaPath = schemaPath || findSchema();
  if (!schemaPath) {
    console.error("ERROR: schema.json not found");
    process.exit(2);
  }

  const schema = JSON.parse(fs.readFileSync(schemaPath, "utf8"));

  if (!configs.length) {
    console.error("Usage: node validate.js [--schema PATH] config.json [...]");
    process.exit(2);
  }

  let worst = 0;
  for (const cfg of configs) {
    console.log(`── ${cfg} ──`);
    if (!fs.existsSync(cfg)) {
      console.log(`  [ERROR] file not found`);
      worst = Math.max(worst, 2);
      continue;
    }
    let config;
    try {
      config = JSON.parse(fs.readFileSync(cfg, "utf8"));
    } catch (e) {
      console.log(`  [ERROR] invalid JSON: ${e.message}`);
      worst = Math.max(worst, 2);
      continue;
    }

    const { errors, warnings } = validateConfig(config, schema);
    for (const w of warnings) console.log(`  [WARN] ${w}`);
    for (const e of errors) console.log(`  [ERROR] ${e}`);
    if (!errors.length && !warnings.length) {
      const t = config.type || "?";
      const c = config.class || "?";
      console.log(`  OK   ${t} :: ${c}`);
    }
    if (errors.length) worst = Math.max(worst, 2);
    else if (warnings.length) worst = Math.max(worst, 1);
  }

  console.log("");
  console.log(worst >= 2 ? "ERRORS" : worst === 1 ? "WARNINGS" : "ALL OK");
  process.exit(worst);
}

main();
