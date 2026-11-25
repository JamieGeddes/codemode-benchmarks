"""Control: answer a question that needs a handful of file reads and some reasoning."""
import json
from pathlib import Path

from ._util import load_json, pkg, result, write

META = {
    "id": "config_lookup",
    "title": "Answer a codebase question (control)",
    "category": "control",
    "hypothesis": "Neutral: a few reads and reasoning; little to batch.",
    "timeout_s": 600,
}

PROMPT = (
    "When this service runs with NODE_ENV=production and no other environment variables set, what request "
    "timeout (in milliseconds) and how many retries does the payments client use? Write answers.json in the "
    'repository root as {"timeout_ms": <number>, "retries": <number>} and briefly explain how you got there.'
)

ANSWER = {"timeout_ms": 10000, "retries": 2}

FILES = {
    "config/default.json": json.dumps({"http": {"timeoutMs": 3000, "retries": 3}, "payments": {"baseUrl": "https://payments.internal"}, "logLevel": "debug"}, indent=2) + "\n",
    "config/production.json": json.dumps({"http": {"timeoutMs": 5000}, "logLevel": "info"}, indent=2) + "\n",
    "config/staging.json": json.dumps({"http": {"timeoutMs": 8000, "retries": 5}}, indent=2) + "\n",
    "src/config.js": """'use strict';
const fs = require('node:fs');
const path = require('node:path');

function readJson(name) {
  const file = path.join(__dirname, '..', 'config', `${name}.json`);
  return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : {};
}

function merge(base, extra) {
  const out = { ...base };
  for (const [key, value] of Object.entries(extra)) {
    out[key] = value && typeof value === 'object' && !Array.isArray(value) ? merge(base[key] || {}, value) : value;
  }
  return out;
}

/** default.json, then <NODE_ENV>.json, then environment variable overrides. */
function loadConfig(env = process.env) {
  let config = merge(readJson('default'), readJson(env.NODE_ENV || 'development'));
  if (env.HTTP_TIMEOUT_MS) config = merge(config, { http: { timeoutMs: Number(env.HTTP_TIMEOUT_MS) } });
  if (env.HTTP_RETRIES) config = merge(config, { http: { retries: Number(env.HTTP_RETRIES) } });
  return config;
}

module.exports = { loadConfig, merge };
""",
    "src/http/client.js": """'use strict';

/** Minimal HTTP client wrapper; every outbound client is built on this. */
function createClient({ baseUrl, timeoutMs, retries }) {
  return { baseUrl, timeoutMs, retries, get: (p) => ({ url: baseUrl + p, timeoutMs, retries }) };
}

module.exports = { createClient };
""",
    "src/payments/client.js": """'use strict';
const { createClient } = require('../http/client');

// Card authorisations are slow, so payments gets twice the standard timeout.
const TIMEOUT_FACTOR = 2;
// Retrying a charge is risky; never retry more than twice whatever the global setting says.
const MAX_RETRIES = 2;

function createPaymentsClient(config) {
  return createClient({
    baseUrl: config.payments.baseUrl,
    timeoutMs: config.http.timeoutMs * TIMEOUT_FACTOR,
    retries: Math.min(config.http.retries, MAX_RETRIES),
  });
}

module.exports = { createPaymentsClient };
""",
    "src/search/client.js": """'use strict';
const { createClient } = require('../http/client');

function createSearchClient(config) {
  return createClient({ baseUrl: 'https://search.internal', timeoutMs: Math.min(config.http.timeoutMs, 1500), retries: config.http.retries + 1 });
}

module.exports = { createSearchClient };
""",
    "src/index.js": """'use strict';
const { loadConfig } = require('./config');
const { createPaymentsClient } = require('./payments/client');
const { createSearchClient } = require('./search/client');

const config = loadConfig();
module.exports = { payments: createPaymentsClient(config), search: createSearchClient(config) };
""",
    "README.md": "# gateway\n\nOutbound clients for the gateway service. Configuration lives in config/.\n",
}


def setup(ws, truth):
    pkg(ws, "gateway")
    for rel, text in FILES.items():
        write(ws, rel, text)


def solve(ws, truth):
    write(ws, "answers.json", json.dumps(ANSWER))


def verify(ws, truth):
    got = load_json(Path(ws) / "answers.json")
    ok = isinstance(got, dict) and all(got.get(k) == v for k, v in ANSWER.items())
    return result(ok, f"got {json.dumps(got)[:200]}, want {json.dumps(ANSWER)}")
