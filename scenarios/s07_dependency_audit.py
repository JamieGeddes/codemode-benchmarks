"""Audit 60 packages of a monorepo for undeclared and unused dependencies."""
import json
import random
from pathlib import Path

from ._util import load_json, result, write

META = {
    "id": "dependency_audit",
    "title": "Audit dependencies across a 60-package monorepo",
    "category": "code search",
    "hypothesis": "Code Mode may help: search results across many files need filtering before they are read.",
    "timeout_s": 900,
}

PROMPT = (
    "Audit the dependencies of every package under packages/. For each package compare the modules its "
    "source files (src/, both .js and .mjs) import with the `dependencies` in its package.json.\n"
    "- undeclared: imported but not listed in dependencies\n"
    "- unused: listed in dependencies but never imported\n"
    "Ignore relative imports and Node built-ins (always written with the `node:` prefix). A subpath import "
    "counts as its package: `lodash/fp` is `lodash`, `@acme/ui/button` is `@acme/ui`.\n"
    "Write audit.json in the repository root as "
    '{"undeclared": {"<package dir name>": ["<dependency>", ...]}, "unused": {...}}, '
    "including only packages that have findings."
)

DEPS = ["lodash", "express", "zod", "dayjs", "axios", "uuid", "chalk", "yargs", "pino", "ws", "ajv", "nanoid", "debug",
        "semver", "glob", "@acme/ui", "@acme/config", "@acme/logger", "@acme/auth", "@scope/metrics", "@scope/cache",
        "react", "react-dom", "pg", "redis", "ioredis", "jsonwebtoken", "bcryptjs", "commander", "dotenv"]
SUBPATHS = {"lodash": "fp", "@acme/ui": "button", "dayjs": "plugin/utc", "@scope/metrics": "client", "react-dom": "client"}
AREAS = ["api", "web", "worker", "cli", "sdk", "admin"]
TOPICS = ["orders", "billing", "search", "auth", "catalogue", "reports", "notify", "audit", "export", "import"]


def _ident(dep):
    return "".join(ch if ch.isalnum() else "_" for ch in dep).strip("_")


def _build():
    rng = random.Random(707)
    names = [f"{a}-{t}" for a in AREAS for t in TOPICS]
    undeclared_in = set(rng.sample(names, 7))
    unused_in = set(rng.sample([n for n in names if n not in undeclared_in], 5)) | set(rng.sample(sorted(undeclared_in), 1))
    packages, truth = {}, {"undeclared": {}, "unused": {}}
    for name in names:
        used = rng.sample(DEPS, rng.randint(3, 7))
        declared = list(used)
        if name in undeclared_in:
            gone = rng.sample(used, rng.choice([1, 1, 2]))
            declared = [d for d in declared if d not in gone]
            truth["undeclared"][name] = sorted(gone)
        if name in unused_in:
            extra = rng.sample([d for d in DEPS if d not in used], rng.choice([1, 2]))
            declared += extra
            truth["unused"][name] = sorted(extra)
        rng.shuffle(declared)
        n_files = rng.randint(2, 3)
        files = {f"src/{['index', 'service', 'util'][k]}.{'mjs' if rng.random() < 0.35 else 'js'}": [] for k in range(n_files)}
        paths = list(files)
        for k, dep in enumerate(used):
            files[paths[k % n_files]].append(dep)
        for dep in rng.sample(used, min(2, len(used))):  # some dependencies are imported from two files
            target = rng.choice(paths)
            if dep not in files[target]:
                files[target].append(dep)
        sources = {}
        for path, deps in files.items():
            esm = path.endswith(".mjs")
            lines = ["import fs from 'node:fs';" if esm else "const path = require('node:path');"]
            for dep in deps:
                spec = f"{dep}/{SUBPATHS[dep]}" if dep in SUBPATHS and rng.random() < 0.5 else dep
                var = _ident(dep)
                if esm:
                    lines.append(rng.choice([f"import {var} from '{spec}';", f"import {{ create as {var} }} from \"{spec}\";"]))
                else:
                    lines.append(rng.choice([f"const {var} = require('{spec}');", f"const {{ create: {var} }} = require(\"{spec}\");"]))
            if path != paths[0]:
                lines.append("import helper from './index.mjs';" if esm else "const helper = require('./index');")
            body = ", ".join(_ident(d) for d in deps)
            lines += ["", f"export const used = [{body}];" if esm else f"module.exports = {{ used: [{body}] }};"]
            sources[path] = "\n".join(lines) + "\n"
        manifest = {"name": f"@mono/{name}", "version": "1.0.0", "private": True,
                    "dependencies": {d: f"^{rng.randint(1, 9)}.{rng.randint(0, 20)}.0" for d in declared}}
        packages[name] = (manifest, sources)
    return packages, truth


def setup(ws, truth):
    packages, answers = _build()
    write(ws, "package.json", json.dumps({"name": "mono", "private": True, "workspaces": ["packages/*"]}, indent=2) + "\n")
    write(ws, "README.md", "# mono\n\nMonorepo with one package per directory under packages/.\n")
    for name, (manifest, sources) in packages.items():
        write(ws, f"packages/{name}/package.json", json.dumps(manifest, indent=2) + "\n")
        for path, text in sources.items():
            write(ws, f"packages/{name}/{path}", text)
    write(truth, "audit.json", json.dumps(answers, indent=2))


def solve(ws, truth):
    write(ws, "audit.json", (Path(truth) / "audit.json").read_text())


def _norm(section):
    if not isinstance(section, dict):
        return None
    return {k: sorted(v) for k, v in section.items() if isinstance(v, list) and v}


def verify(ws, truth):
    want = load_json(Path(truth) / "audit.json")
    got = load_json(Path(ws) / "audit.json")
    if not isinstance(got, dict):
        return result(False, "audit.json missing or not a JSON object", 0)
    notes, good = [], 0
    for key in ("undeclared", "unused"):
        mine = _norm(got.get(key))
        if mine == _norm(want[key]):
            good += 1
        else:
            notes.append(f"{key}: got {json.dumps(mine)[:400]}, want {json.dumps(want[key])[:400]}")
    return result(good == 2, "; ".join(notes) or "audit correct", good / 2)
