"""Control: fix one small, well-described bug in one file."""
from ._util import node_test, pkg, result, write

META = {
    "id": "single_bugfix",
    "title": "Fix one reported bug (control)",
    "category": "control",
    "hypothesis": "Neutral or slightly worse for Code Mode: two or three tool calls, nothing to batch.",
    "timeout_s": 600,
}

PROMPT = (
    "Bug report: `parseCsvLine('a,\"b,c\",d')` in src/csv.js returns four fields instead of three, so quoted "
    "fields that contain commas are split. Fix the parser so that the tests in test/csv.test.js pass."
)

BUGGY = """'use strict';

/** Split one CSV line into fields. Unquoted fields are trimmed. */
function parseCsvLine(line) {
  return line.split(',').map((field) => field.trim().replace(/^"|"$/g, ''));
}

module.exports = { parseCsvLine };
"""

FIXED = """'use strict';

/** Split one CSV line into fields. Unquoted fields are trimmed; quoted fields are kept verbatim. */
function parseCsvLine(line) {
  const out = [];
  let cur = '';
  let inQuotes = false;
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (inQuotes) {
      if (c === '"' && line[i + 1] === '"') { cur += '"'; i++; }
      else if (c === '"') inQuotes = false;
      else cur += c;
    } else if (c === '"') { inQuotes = true; quoted = true; cur = ''; }
    else if (c === ',') { out.push(quoted ? cur : cur.trim()); cur = ''; quoted = false; }
    else if (!quoted) cur += c;
  }
  out.push(quoted ? cur : cur.trim());
  return out;
}

module.exports = { parseCsvLine };
"""

REPORT = """'use strict';
const { parseCsvLine } = require('./csv');

/** Sum the numeric third column of CSV text with a header row. */
function totalAmount(text) {
  return text.trim().split('\\n').slice(1).map(parseCsvLine).reduce((sum, row) => sum + Number(row[2]), 0);
}

module.exports = { totalAmount };
"""

TESTS = ''''use strict';
const test = require('node:test');
const assert = require('node:assert');
const { parseCsvLine } = require('../src/csv');

test('plain fields', () => { assert.deepStrictEqual(parseCsvLine('a,b,c'), ['a', 'b', 'c']); });
test('unquoted fields are trimmed', () => { assert.deepStrictEqual(parseCsvLine(' a , b '), ['a', 'b']); });
test('empty fields', () => { assert.deepStrictEqual(parseCsvLine('a,,c'), ['a', '', 'c']); });
test('empty line', () => { assert.deepStrictEqual(parseCsvLine(''), ['']); });
test('quoted field containing a comma', () => { assert.deepStrictEqual(parseCsvLine('a,"b,c",d'), ['a', 'b,c', 'd']); });
test('escaped quotes inside a quoted field', () => { assert.deepStrictEqual(parseCsvLine('"say ""hi""",x'), ['say "hi"', 'x']); });
test('quoted fields keep their spaces', () => { assert.deepStrictEqual(parseCsvLine('"  padded  ",z'), ['  padded  ', 'z']); });
'''

REPORT_TESTS = """'use strict';
const test = require('node:test');
const assert = require('node:assert');
const { totalAmount } = require('../src/report');

test('totals the amount column', () => {
  assert.strictEqual(totalAmount('name,note,amount\\nwidget,"small, blue",3\\ngadget,plain,4\\n'), 7);
});
"""


def _tests(ws):
    return [write(ws, "test/csv.test.js", TESTS), write(ws, "test/report.test.js", REPORT_TESTS)]


def setup(ws, truth):
    pkg(ws, "csv-report")
    write(ws, "README.md", "# csv-report\n\nTiny CSV reporting helpers. Run `npm test`.\n")
    write(ws, "src/csv.js", BUGGY)
    write(ws, "src/report.js", REPORT)
    _tests(ws)


def solve(ws, truth):
    write(ws, "src/csv.js", FIXED)


def verify(ws, truth):
    code, out = node_test(ws, _tests(ws))
    return result(code == 0, out)
