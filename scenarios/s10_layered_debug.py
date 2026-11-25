"""Sequential debugging: four build failures, each hidden behind the previous one."""
import json
from pathlib import Path

from ._util import load_json, pkg, result, run, write

META = {
    "id": "layered_debug",
    "title": "Fix a build with four chained failures",
    "category": "sequential debugging",
    "hypothesis": "Neutral: each step depends on the previous result, so calls cannot be batched.",
    "timeout_s": 900,
}

PROMPT = (
    "`npm run build` is failing. Get the build working so that it completes successfully and produces the "
    "correct output in dist/. Fix the underlying problems; do not remove build steps or checks."
)

TITLE = "Parcel Tracker"
SOURCES = {
    "src/app/01-state.js": "// Application state\nconst state = { parcels: [], filter: 'all' };\n\nfunction setFilter(value) {\n  state.filter = value;\n}\n",
    "src/app/02-render.js": "// Rendering\nfunction render(root) {\n  // one row per parcel\n  root.textContent = state.parcels\n    .filter((p) => state.filter === 'all' || p.status === state.filter)\n    .map((p) => p.id + ' ' + p.status)\n    .join(', ');\n}\n",
    "src/app/03-main.js": "// Entry point\n\nfunction main() {\n  render(document.getElementById('app'));\n}\n\nmain();\n",
}
TEMPLATE = "<!doctype html>\n<html lang=\"en-GB\">\n<head><meta charset=\"utf-8\"><title>{{title}}</title></head>\n<body>\n<div id=\"app\"></div>\n<script src=\"{{bundle}}\"></script>\n</body>\n</html>\n"

CONFIG_BROKEN = '{\n  "title": "Parcel Tracker",\n  "srcDir": "src/app",\n  "outDir": "dist",\n  "bundle": "app.min.js",\n  "template": "templates/index.htm",\n}\n'
CONFIG_FIXED = '{\n  "title": "Parcel Tracker",\n  "srcDir": "src/app",\n  "outDir": "dist",\n  "bundle": "app.min.js",\n  "template": "templates/index.html"\n}\n'

BUILD = """'use strict';
const fs = require('node:fs');
const path = require('node:path');
const { loadConfig } = require('./steps/config');
const { %(minify)s } = require('./steps/minify');
const { renderTemplate } = require('./steps/template');
const { writeManifest } = require('./steps/manifest');

const root = path.join(__dirname, '..');

function main() {
  const config = loadConfig(path.join(root, 'build.config.json'));
  const dist = path.join(root, config.outDir);
  fs.rmSync(dist, { recursive: true, force: true });
  fs.mkdirSync(dist, { recursive: true });

  const srcDir = path.join(root, config.srcDir);
  const sources = fs.readdirSync(srcDir).filter((f) => f.endsWith('.js')).sort();
  const bundle = %(minify)s(sources.map((f) => fs.readFileSync(path.join(srcDir, f), 'utf8')));
  fs.writeFileSync(path.join(dist, config.bundle), bundle);

  const html = renderTemplate(path.join(root, config.template), { title: config.title, bundle: config.bundle });
  fs.writeFileSync(path.join(dist, 'index.html'), html);

  const outputs = [config.bundle, 'index.html'];
  const manifest = writeManifest(dist, outputs);
  if (manifest.files.length !== outputs.length) {
    throw new Error(`manifest incomplete: expected ${outputs.length} files, got ${manifest.files.length}`);
  }
  console.log(`build ok: ${manifest.files.length} files`);
}

main();
"""

STEPS = {
    "scripts/steps/config.js": """'use strict';
const fs = require('node:fs');

function loadConfig(file) {
  const config = JSON.parse(fs.readFileSync(file, 'utf8'));
  for (const key of ['title', 'srcDir', 'outDir', 'bundle', 'template']) {
    if (typeof config[key] !== 'string') throw new Error(`build.config.json: missing "${key}"`);
  }
  return config;
}

module.exports = { loadConfig };
""",
    "scripts/steps/minify.js": """'use strict';

/** Strip blank lines, comment lines and indentation, then join all sources. */
function minify(sources) {
  return sources
    .map((text) => text.split('\\n').map((line) => line.trim()).filter((line) => line && !line.startsWith('//')).join('\\n'))
    .join('\\n');
}

module.exports = { minify };
""",
    "scripts/steps/template.js": """'use strict';
const fs = require('node:fs');

function renderTemplate(file, values) {
  let html = fs.readFileSync(file, 'utf8');
  for (const [key, value] of Object.entries(values)) html = html.split(`{{${key}}}`).join(value);
  return html;
}

module.exports = { renderTemplate };
""",
}

MANIFEST = """'use strict';
const fs = require('node:fs');
const path = require('node:path');

/** Write dist/manifest.json listing every output file and its size in bytes. */
function writeManifest(dist, names) {
  const files = names%(slice)s.map((name) => ({ name, bytes: fs.statSync(path.join(dist, name)).size }));
  const manifest = { files };
  fs.writeFileSync(path.join(dist, 'manifest.json'), JSON.stringify(manifest, null, 2) + '\\n');
  return manifest;
}

module.exports = { writeManifest };
"""


def _expected():
    parts = []
    for name in sorted(SOURCES):
        lines = [line.strip() for line in SOURCES[name].split("\n")]
        parts.append("\n".join(line for line in lines if line and not line.startswith("//")))
    bundle = "\n".join(parts)
    html = TEMPLATE.replace("{{title}}", TITLE).replace("{{bundle}}", "app.min.js")
    manifest = {"files": [{"name": "app.min.js", "bytes": len(bundle.encode())}, {"name": "index.html", "bytes": len(html.encode())}]}
    return bundle, html, manifest


def setup(ws, truth):
    pkg(ws, "parcel-tracker", {"build": "node scripts/build.js"})
    write(ws, "README.md", "# parcel-tracker\n\n`npm run build` bundles src/app into dist/ and writes dist/manifest.json.\n")
    write(ws, ".gitignore", "dist/\n")
    for rel, text in SOURCES.items():
        write(ws, rel, text)
    write(ws, "templates/index.html", TEMPLATE)
    write(ws, "build.config.json", CONFIG_BROKEN)
    write(ws, "scripts/build.js", BUILD % {"minify": "minfy"})
    for rel, text in STEPS.items():
        write(ws, rel, text)
    write(ws, "scripts/steps/manifest.js", MANIFEST % {"slice": ".slice(1)"})


def solve(ws, truth):
    write(ws, "build.config.json", CONFIG_FIXED)
    write(ws, "scripts/build.js", BUILD % {"minify": "minify"})
    write(ws, "scripts/steps/manifest.js", MANIFEST % {"slice": ""})


def verify(ws, truth):
    code, out = run(["node", "scripts/build.js"], ws)
    if code != 0:
        return result(False, f"build failed: {out}")
    bundle, html, manifest = _expected()
    dist = Path(ws) / "dist"
    problems = []
    try:
        if (dist / "app.min.js").read_text() != bundle:
            problems.append("app.min.js differs from the expected bundle")
        if (dist / "index.html").read_text() != html:
            problems.append("index.html differs from the expected page")
    except OSError as err:
        problems.append(f"missing output: {err}")
    if load_json(dist / "manifest.json") != manifest:
        problems.append("manifest.json differs from the expected manifest")
    return result(not problems, "; ".join(problems) or "build output correct")
