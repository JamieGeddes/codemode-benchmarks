"""Implement one module from a written specification."""
import shutil
from pathlib import Path

from ._util import node_test, pkg, result, write

META = {
    "id": "codegen_feature",
    "title": "Implement a module from a spec",
    "category": "code generation",
    "hypothesis": "Roughly neutral: mostly model reasoning and one file write, few tool calls to batch.",
    "timeout_s": 900,
}

PROMPT = (
    "Implement src/semver.js according to docs/semver-spec.md. The existing tests in "
    "test/semver.test.js must pass (`npm test`); add further tests for the behaviour the spec describes."
)

SPEC = """# semver module specification

`src/semver.js` exports four functions. Versions are always `MAJOR.MINOR.PATCH`: three non-negative
integers without leading zeros (`0` itself is allowed). Pre-release and build suffixes are not supported.

## parse(version)
Returns `{ major, minor, patch }` as numbers. Throws `TypeError` when `version` is not a string or is not
a valid version (for example `1.2`, `1.2.3.4`, `01.2.3`, `1.2.x`, `v1.2.3`).

## compare(a, b)
Returns `-1`, `0` or `1` when version `a` is lower than, equal to or higher than `b`. Comparison is numeric
(`1.10.0` is higher than `1.9.0`). Throws `TypeError` for invalid versions.

## satisfies(version, range)
Returns `true` when `version` matches `range`. Throws `TypeError` for an invalid version or range.

A range is one or more comparator sets joined by `||`; the version must satisfy at least one set.
A comparator set is one or more comparators separated by spaces; the version must satisfy all of them.

Comparators:

| Form | Meaning |
|---|---|
| `1.2.3` or `=1.2.3` | exactly 1.2.3 |
| `>1.2.3`, `>=1.2.3`, `<1.2.3`, `<=1.2.3` | ordinary comparisons |
| `~1.2.3` | `>=1.2.3 <1.3.0` |
| `^1.2.3` | `>=1.2.3 <2.0.0` |
| `^0.2.3` | `>=0.2.3 <0.3.0` (major is 0, minor is not) |
| `^0.0.3` | `>=0.0.3 <0.0.4` (major and minor are 0) |
| `*` | any version |
| `1.x` | any version with major 1 |
| `1.2.x` | any version with major 1 and minor 2 |

Operators are written without a space before the version (`>=1.2.3`). Operators, `^` and `~` take a
full version only (`^1.x` is invalid).

## maxSatisfying(versions, range)
Returns the highest version in the array `versions` that satisfies `range`, or `null` when none does.
"""

STUB = """'use strict';
// TODO: implement according to docs/semver-spec.md

function parse(version) { throw new Error('not implemented'); }
function compare(a, b) { throw new Error('not implemented'); }
function satisfies(version, range) { throw new Error('not implemented'); }
function maxSatisfying(versions, range) { throw new Error('not implemented'); }

module.exports = { parse, compare, satisfies, maxSatisfying };
"""

REFERENCE = """'use strict';

function parse(version) {
  if (typeof version !== 'string') throw new TypeError('version must be a string');
  const m = /^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.(0|[1-9]\\d*)$/.exec(version);
  if (!m) throw new TypeError(`invalid version: ${version}`);
  return { major: Number(m[1]), minor: Number(m[2]), patch: Number(m[3]) };
}

function tuple(version) { const p = parse(version); return [p.major, p.minor, p.patch]; }

function cmp(a, b) {
  for (let i = 0; i < 3; i++) if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1;
  return 0;
}

function compare(a, b) { return cmp(tuple(a), tuple(b)); }

function comparator(token) {
  if (token === '*') return () => true;
  let m = /^(0|[1-9]\\d*)\\.x$/.exec(token);
  if (m) { const major = Number(m[1]); return (v) => v[0] === major; }
  m = /^(0|[1-9]\\d*)\\.(0|[1-9]\\d*)\\.x$/.exec(token);
  if (m) { const major = Number(m[1]); const minor = Number(m[2]); return (v) => v[0] === major && v[1] === minor; }
  m = /^(\\^|~|>=|<=|>|<|=)?(.*)$/.exec(token);
  const op = m[1] || '=';
  const t = tuple(m[2]);
  switch (op) {
    case '=': return (v) => cmp(v, t) === 0;
    case '>': return (v) => cmp(v, t) > 0;
    case '>=': return (v) => cmp(v, t) >= 0;
    case '<': return (v) => cmp(v, t) < 0;
    case '<=': return (v) => cmp(v, t) <= 0;
    case '~': { const hi = [t[0], t[1] + 1, 0]; return (v) => cmp(v, t) >= 0 && cmp(v, hi) < 0; }
    default: {
      const hi = t[0] > 0 ? [t[0] + 1, 0, 0] : t[1] > 0 ? [0, t[1] + 1, 0] : [0, 0, t[2] + 1];
      return (v) => cmp(v, t) >= 0 && cmp(v, hi) < 0;
    }
  }
}

function compile(range) {
  if (typeof range !== 'string' || range.trim() === '') throw new TypeError('invalid range');
  return range.split('||').map((set) => {
    const tokens = set.trim().split(/\\s+/).filter(Boolean);
    if (tokens.length === 0) throw new TypeError('invalid range');
    return tokens.map(comparator);
  });
}

function satisfies(version, range) {
  const v = tuple(version);
  return compile(range).some((set) => set.every((test) => test(v)));
}

function maxSatisfying(versions, range) {
  const sets = compile(range);
  let best = null;
  for (const version of versions) {
    const v = tuple(version);
    if (sets.some((set) => set.every((test) => test(v))) && (best === null || compare(version, best) > 0)) best = version;
  }
  return best;
}

module.exports = { parse, compare, satisfies, maxSatisfying };
"""

VISIBLE_TESTS = """'use strict';
const test = require('node:test');
const assert = require('node:assert');
const semver = require('../src/semver');

test('parse returns numeric parts', () => {
  assert.deepStrictEqual(semver.parse('1.2.3'), { major: 1, minor: 2, patch: 3 });
});
test('parse rejects short versions', () => { assert.throws(() => semver.parse('1.2'), TypeError); });
test('compare is numeric', () => { assert.strictEqual(semver.compare('1.10.0', '1.9.0'), 1); });
test('caret range', () => {
  assert.strictEqual(semver.satisfies('1.4.0', '^1.2.3'), true);
  assert.strictEqual(semver.satisfies('2.0.0', '^1.2.3'), false);
});
test('maxSatisfying picks the highest match', () => {
  assert.strictEqual(semver.maxSatisfying(['1.0.0', '1.5.0', '2.0.0'], '1.x'), '1.5.0');
});
"""

# (version, range, expected) triples; every case is decided explicitly by the spec.
SATISFIES = [
    ("1.2.3", "1.2.3", True), ("1.2.4", "1.2.3", False), ("1.2.3", "=1.2.3", True),
    ("1.2.4", ">1.2.3", True), ("1.2.3", ">1.2.3", False), ("1.2.3", ">=1.2.3", True),
    ("1.2.2", "<1.2.3", True), ("1.2.3", "<1.2.3", False), ("1.2.3", "<=1.2.3", True),
    ("1.2.9", "~1.2.3", True), ("1.3.0", "~1.2.3", False), ("1.2.2", "~1.2.3", False),
    ("1.9.9", "^1.2.3", True), ("1.2.2", "^1.2.3", False), ("2.0.0", "^1.2.3", False),
    ("0.2.9", "^0.2.3", True), ("0.3.0", "^0.2.3", False), ("0.0.3", "^0.0.3", True), ("0.0.4", "^0.0.3", False),
    ("9.9.9", "*", True), ("1.0.0", "1.x", True), ("2.0.0", "1.x", False),
    ("1.2.7", "1.2.x", True), ("1.3.0", "1.2.x", False),
    ("1.5.0", ">=1.2.0 <2.0.0", True), ("2.0.0", ">=1.2.0 <2.0.0", False),
    ("3.1.0", "^1.0.0 || ^3.0.0", True), ("2.1.0", "^1.0.0 || ^3.0.0", False),
    ("1.10.0", ">1.9.0", True), ("10.0.0", ">9.9.9", True),
]


def _hidden():
    lines = ["'use strict';", "const test = require('node:test');", "const assert = require('node:assert');",
             "const s = require('../src/semver');", ""]
    for n, (v, r, exp) in enumerate(SATISFIES):
        lines.append(f"test('satisfies {n}: {v} in {r}', () => {{ assert.strictEqual(s.satisfies('{v}', '{r}'), {str(exp).lower()}); }});")
    for bad in ["1.2", "1.2.3.4", "01.2.3", "1.2.x", "v1.2.3", ""]:
        lines.append(f"test('parse rejects [{bad}]', () => {{ assert.throws(() => s.parse('{bad}'), TypeError); }});")
    lines += [
        "test('parse rejects non-strings', () => { assert.throws(() => s.parse(123), TypeError); });",
        "test('parse zero', () => { assert.deepStrictEqual(s.parse('0.0.0'), { major: 0, minor: 0, patch: 0 }); });",
        "test('compare', () => { assert.strictEqual(s.compare('1.2.3', '1.2.3'), 0); assert.strictEqual(s.compare('1.2.3', '1.3.0'), -1); assert.strictEqual(s.compare('2.0.0', '1.99.99'), 1); });",
        "test('compare rejects invalid', () => { assert.throws(() => s.compare('1.2', '1.2.3'), TypeError); });",
        "test('satisfies rejects invalid version', () => { assert.throws(() => s.satisfies('banana', '*'), TypeError); });",
        "test('satisfies rejects invalid range', () => { assert.throws(() => s.satisfies('1.0.0', 'banana'), TypeError); });",
        "test('satisfies rejects caret with wildcard', () => { assert.throws(() => s.satisfies('1.0.0', '^1.x'), TypeError); });",
        "test('maxSatisfying', () => { assert.strictEqual(s.maxSatisfying(['1.2.0', '1.10.0', '1.9.0', '2.0.0'], '^1.0.0'), '1.10.0'); });",
        "test('maxSatisfying none', () => { assert.strictEqual(s.maxSatisfying(['1.0.0', '1.1.0'], '>=2.0.0'), null); });",
        "test('maxSatisfying empty', () => { assert.strictEqual(s.maxSatisfying([], '*'), null); });",
    ]
    return "\n".join(lines) + "\n"


def setup(ws, truth):
    pkg(ws, "mini-semver")
    write(ws, "README.md", "# mini-semver\n\nSee docs/semver-spec.md. Run `npm test`.\n")
    write(ws, "docs/semver-spec.md", SPEC)
    write(ws, "src/semver.js", STUB)
    write(ws, "test/semver.test.js", VISIBLE_TESTS)


def solve(ws, truth):
    write(ws, "src/semver.js", REFERENCE)


def verify(ws, truth):
    visible = write(ws, ".bench_verify/visible.test.js", VISIBLE_TESTS)
    hidden = write(ws, ".bench_verify/hidden.test.js", _hidden())
    code, out = node_test(ws, [visible, hidden])
    shutil.rmtree(Path(ws) / ".bench_verify", ignore_errors=True)
    return result(code == 0, out)
