"""Run a large unit-test suite (1,200 tests), find the failures and fix the root causes."""
import json
import random
import re

from ._util import node_test, pkg, result, write

META = {
    "id": "test_triage",
    "title": "Triage a large unit-test suite",
    "category": "testing",
    "hypothesis": "Code Mode may help: test output can be filtered before it reaches the context.",
    "timeout_s": 900,
}

PROMPT = (
    "Some tests in this repository are failing. Run the test suite with `npm test`, work out the "
    "root causes and fix them in the source code under src/. Do not modify the tests. "
    "You are done when the whole suite passes."
)

N_MODULES = 40
BUGS = {7: "chunk", 15: "median", 23: "isLeap", 31: "clamp"}
PHRASES = ["Hello, World!", "Quick  Brown Fox", "order #42 shipped", "A/B test: variant-C", "  spaced   out  ", "Alpha_Beta.Gamma"]


def _module(i, bug=None):
    clamp = (
        "if (x < lo) return lo; if (x > hi) return lo; return x;"
        if bug == "clamp"
        else "if (x < lo) return lo; if (x > hi) return hi; return x;"
    )
    loop = "j + size <= arr.length" if bug == "chunk" else "j < arr.length"
    sort = "sort()" if bug == "median" else "sort((a, b) => a - b)"
    leap = (
        "year % 4 === 0 && year % 100 !== 0"
        if bug == "isLeap"
        else "(year % 4 === 0 && year % 100 !== 0) || year % 400 === 0"
    )
    return f"""'use strict';
// Utility module {i:02d}.
const K = {i + 2};

function scale(x) {{ return x * K + {i}; }}

function clamp(x, lo, hi) {{ {clamp} }}

function chunk(arr, size) {{
  const out = [];
  for (let j = 0; {loop}; j += size) out.push(arr.slice(j, j + size));
  return out;
}}

function median(arr) {{
  const sorted = [...arr].{sort};
  return sorted[Math.floor(sorted.length / 2)];
}}

function isLeap(year) {{ return {leap}; }}

function slug(s) {{
  return 'm{i}-' + s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}}

function rangeSum(a, b) {{ let t = 0; for (let n = a; n <= b; n++) t += n; return t; }}

function dedupe(arr) {{ return [...new Set(arr)]; }}

function pad(n, width) {{ return String(n).padStart(width, '0'); }}

function wordCount(s) {{ return s.split(/\\s+/).filter(Boolean).length; }}

module.exports = {{ scale, clamp, chunk, median, isLeap, slug, rangeSum, dedupe, pad, wordCount }};
"""


def _expected(i, fn, args):
    if fn == "scale":
        return args[0] * (i + 2) + i
    if fn == "clamp":
        x, lo, hi = args
        return max(lo, min(hi, x))
    if fn == "chunk":
        arr, size = args
        return [arr[j:j + size] for j in range(0, len(arr), size)]
    if fn == "median":
        return sorted(args[0])[len(args[0]) // 2]
    if fn == "isLeap":
        y = args[0]
        return (y % 4 == 0 and y % 100 != 0) or y % 400 == 0
    if fn == "slug":
        return f"m{i}-" + re.sub(r"^-+|-+$", "", re.sub(r"[^a-z0-9]+", "-", args[0].lower()))
    if fn == "rangeSum":
        return sum(range(args[0], args[1] + 1))
    if fn == "dedupe":
        return list(dict.fromkeys(args[0]))
    if fn == "pad":
        return str(args[0]).zfill(args[1])
    if fn == "wordCount":
        return len(args[0].split())
    raise ValueError(fn)


def _cases(i, rng):
    r = rng.randint
    return [
        ("scale", [r(-50, 50)]), ("scale", [r(0, 1000)]), ("scale", [0]),
        ("clamp", [r(20, 80), r(0, 20), r(80, 100)]), ("clamp", [r(-60, -1), 0, 50]), ("clamp", [r(101, 150), 10, 100]),
        ("chunk", [[r(0, 9) for _ in range(6)], 3]), ("chunk", [[r(0, 9) for _ in range(4)], 1]), ("chunk", [[1, 2, 3, 4, 5], 2]),
        ("median", [rng.sample(range(100, 999), 5)]), ("median", [rng.sample(range(10, 99), 3)]), ("median", [[9, 10, 100]]),
        ("isLeap", [rng.choice([2023, 2024, 2025, 2028])]), ("isLeap", [1900]), ("isLeap", [2000]),
        ("slug", [rng.choice(PHRASES)]), ("slug", [rng.choice(PHRASES) + " " + str(r(1, 99))]), ("slug", ["--Trim Me--"]),
        ("rangeSum", [r(1, 10), r(11, 40)]), ("rangeSum", [5, 5]), ("rangeSum", [r(-10, 0), r(1, 10)]),
        ("dedupe", [[r(0, 4) for _ in range(8)]]), ("dedupe", [["a", "b", "a", "c", "b"]]), ("dedupe", [[]]),
        ("pad", [r(0, 99), 4]), ("pad", [r(100, 999), 2]), ("pad", [7, 3]),
        ("wordCount", [rng.choice(PHRASES)]), ("wordCount", [""]), ("wordCount", ["one two\tthree\nfour"]),
    ]


def _test_file(i, rng):
    lines = [
        "'use strict';",
        "const test = require('node:test');",
        "const assert = require('node:assert');",
        f"const m = require('../src/mod_{i:02d}');",
        "",
    ]
    for n, (fn, args) in enumerate(_cases(i, rng), 1):
        call = f"m.{fn}(...{json.dumps(args)})"
        lines.append(
            f"test('mod_{i:02d} {fn} #{n}', () => {{ assert.deepStrictEqual({call}, {json.dumps(_expected(i, fn, args))}); }});"
        )
    return "\n".join(lines) + "\n"


def _write_tests(ws):
    rng = random.Random(101)
    files = []
    for i in range(N_MODULES):
        files.append(write(ws, f"test/mod_{i:02d}.test.js", _test_file(i, rng)))
    return files


def setup(ws, truth):
    pkg(ws, "utility-belt")
    write(ws, "README.md", "# utility-belt\n\nSmall utility modules. Run the tests with `npm test`.\n")
    for i in range(N_MODULES):
        write(ws, f"src/mod_{i:02d}.js", _module(i, BUGS.get(i)))
    _write_tests(ws)


def solve(ws, truth):
    for i in BUGS:
        write(ws, f"src/mod_{i:02d}.js", _module(i))


def verify(ws, truth):
    files = _write_tests(ws)  # restore pristine tests, so edited tests cannot mask a failure
    code, out = node_test(ws, files)
    return result(code == 0, out)
