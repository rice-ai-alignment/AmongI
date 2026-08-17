// experimentStats.js — shared parser for experiment stats.
//
// Turns a raw experiment doc ({stats..., config: {...}}) into display-ready
// data used across the website (landing page, charts, player tables).
// Winning groups come from the experiment CONFIG (win_conditions winners),
// never from hardcoded names — so new games/roles just work.

/**
 * Winning group labels from the experiment config's win_conditions.
 * @param {object} config - the experiment config object (config.win_conditions)
 * @returns {Array<{key: string, label: string, cls: string}>}
 */
export function winningGroups(config) {
  const conditions = config?.win_conditions || [];
  const groups = [];
  for (const wc of conditions) {
    const label = wc?.winner;
    if (!label) continue;
    groups.push({ key: String(label), label: String(label), cls: guessClass(label) });
  }
  return groups;
}

/**
 * Per-group wins + win-rate pct from the stats' by_winner map.
 * @param {object} stats - experiment stats doc (by_winner, total_games)
 * @param {Array} groups - from winningGroups()
 */
export function groupWins(stats, groups) {
  const by = stats?.by_winner || {};
  const total = stats?.total_games || 0;
  return groups.map((g) => ({
    ...g,
    wins: by[g.key] || 0,
    pct: total > 0 ? Math.round(((by[g.key] || 0) / total) * 100) : 0,
  }));
}

/**
 * Outcomes in by_winner that aren't config groups (timeout, token_limit, ...).
 * @param {object} stats - experiment stats doc
 * @param {Array} groups - from winningGroups()
 */
export function otherOutcomes(stats, groups) {
  const by = stats?.by_winner || {};
  const keys = new Set(groups.map((g) => g.key));
  return Object.entries(by)
    .filter(([k]) => !keys.has(k))
    .map(([k, v]) => ({ key: k, label: k, wins: v, cls: "a" }));
}

/**
 * Players sorted by wins desc, then games desc.
 * @param {object} stats - experiment stats doc (players array)
 */
export function sortedPlayers(stats) {
  const list = [...(stats?.players || [])];
  return list.sort((a, b) => (b.wins || 0) - (a.wins || 0) || (b.games || 0) - (a.games || 0));
}

/**
 * Terminal color class for a winner label (crew → green, imposter → red).
 * @param {string} label
 */
export function guessClass(label) {
  const l = String(label || "").toLowerCase();
  if (l.includes("impost")) return "r";
  if (l.includes("crew")) return "g";
  return "a";
}

const PALETTE = ["c-d3", "c-d4", "c-d5", "c-d6", "c-d2", "a"];

/**
 * Stable display color for a group label: known roles get their semantic
 * color, everything else gets a deterministic palette color (hash-based
 * so it never shifts between renders).
 * @param {string} label
 */
export function paletteCls(label) {
  const g = guessClass(label);
  if (g !== "a") return g;
  let h = 0;
  const s = String(label || "");
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return PALETTE[Math.abs(h) % PALETTE.length];
}

/**
 * Format a recap winner value for display, using config group names.
 * @param {*} w - recap winner value
 * @param {Array} groups - from winningGroups()
 */
export function fmtWinner(w, groups = []) {
  const g = groups.find((x) => x.key === String(w));
  if (g) return `[ ${g.label.toUpperCase()} WIN ]`;
  if (w === "timeout") return "[ TIMEOUT ]";
  if (w === "token_limit") return "[ TOKEN LIMIT ]";
  return "[ " + String(w || "?").toUpperCase() + " ]";
}
