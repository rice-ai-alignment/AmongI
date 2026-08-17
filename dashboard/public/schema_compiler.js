/**
 * schema_compiler.js — THE config compiler. Single source of truth.
 *
 * Validates experiment configs against schema.json (exported from the
 * Python component registry). Used by:
 *   - The website (ConfigCard [ validate ] tab) — runs natively in browser
 *   - The engine/server (check.sh + validate_configs.py) — runs under Node
 *
 * Pure JS with no imports — works in both environments.
 * In Node:       module.exports = { validateConfig }
 * In browser:    window.validateConfig = validateConfig
 */

const META_KEYS = new Set(["id", "name", "description"]);
const IGNORED_KEYS = new Set(["type", "class"]);

/**
 * Validate a config object against the schema.
 * @param {object} config - parsed config JSON
 * @param {object} schema - parsed schema.json ({Type: {classes: {Class: {params}}}})
 * @returns {{errors: string[], warnings: string[]}}
 */
function validateConfig(config, schema) {
  const errors = [];
  const warnings = [];

  if (!config || typeof config !== "object") {
    return { errors: ["config is not an object"], warnings };
  }

  if (!config.type || !config.class) {
    errors.push("config missing 'type'/'class' fields");
    return { errors, warnings };
  }

  // Root-level warnings
  if (config.type === "Experiment") {
    warnings.push("Legacy 'Experiment' type — consider migrating to a Game type.");
  }
  if (config.type === "Game" && (!config.phases || !config.phases.length)) {
    warnings.push("No 'phases' defined.");
  }

  validateNode(config, config.type, schema, errors, warnings);
  return { errors, warnings };
}

function validateNode(node, path, schema, errors, warnings) {
  if (!node || typeof node !== "object") return;
  if (Array.isArray(node)) {
    node.forEach((item, i) => validateNode(item, `${path}[${i}]`, schema, errors, warnings));
    return;
  }

  const t = node.type;
  const c = node.class;
  if (!t || !c) return;

  const typeInfo = schema[t];
  if (!typeInfo) {
    errors.push(`${path}: unknown type "${t}"`);
    return;
  }
  const classInfo = (typeInfo.classes || {})[c];
  if (!classInfo) {
    errors.push(`${path}: unknown class "${t}::${c}"`);
    return;
  }

  const params = classInfo.params || {};
  for (const [key, val] of Object.entries(node)) {
    if (IGNORED_KEYS.has(key)) continue;

    const p = params[key];

    // Unused parameter — hard error (matches Python's ValueError)
    if (p === undefined) {
      if (!META_KEYS.has(key)) {
        errors.push(`${path}.${key}: unused parameter — known: ${Object.keys(params).join(", ")}`);
      }
      if (val && typeof val === "object") validateNode(val, `${path}.${key}`, schema, errors, warnings);
      continue;
    }

    if (val === null || val === undefined) continue;

    // Type checking (matches Python ExperimentComponent._validate)
    const ptype = p.type;
    const jsType = Array.isArray(val) ? "list" : typeof val;
    if (ptype === "int" || ptype === "float") {
      if (typeof val !== "number") errors.push(`${path}.${key}: expected ${ptype}, got ${jsType}`);
    } else if (ptype === "str") {
      if (typeof val !== "string") errors.push(`${path}.${key}: expected str, got ${jsType}`);
    } else if (ptype === "bool") {
      if (typeof val !== "boolean") errors.push(`${path}.${key}: expected bool, got ${jsType}`);
    } else if (ptype === "list") {
      if (!Array.isArray(val)) {
        errors.push(`${path}.${key}: expected list, got ${jsType}`);
      } else if (p.element_type && p.element_type !== "component") {
        for (let i = 0; i < val.length; i++) {
          if (p.element_type === "str" && typeof val[i] !== "string")
            errors.push(`${path}.${key}[${i}]: expected str, got ${typeof val[i]}`);
        }
      }
    }

    // Recurse into nested components
    if (val && typeof val === "object") {
      validateNode(val, `${path}.${key}`, schema, errors, warnings);
    }
  }
}

// ── Environment export ───────────────────────────────────────────
if (typeof module !== "undefined" && module.exports) {
  module.exports = { validateConfig };
}
if (typeof window !== "undefined") {
  window.validateConfig = validateConfig;
}
