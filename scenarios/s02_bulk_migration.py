"""Migrate a deprecated function signature across 48 files."""
import json
import random

from ._util import node_test, pkg, result, write

META = {
    "id": "bulk_migration",
    "title": "Repeat an API migration across 48 files",
    "category": "refactoring",
    "hypothesis": "Code Mode may help: the same edit repeats across many files.",
    "timeout_s": 900,
}

PROMPT = (
    "The positional signature `formatMoney(amount, currency, showSymbol)` in src/lib/money.js is "
    "deprecated in favour of the options form `formatMoney(amount, { currency, symbol })`. "
    "Migrate every call site under src/services/ to the options form, then remove support for the "
    "positional form from src/lib/money.js. Behaviour must not change and `npm test` must still pass."
)

DOMAINS = ["billing", "checkout", "invoice", "refund", "payout", "ledger", "pricing", "quote"]
NOUNS = ["summary", "email", "receipt", "export", "report", "notice"]
SYMBOLS = {"GBP": "£", "USD": "$", "EUR": "€"}

MONEY_HEAD = """'use strict';
const SYMBOLS = { GBP: '£', USD: '$', EUR: '€' };

/**
 * Format an amount in minor units (pence, cents).
 * Preferred:   formatMoney(amount, { currency, symbol })
 * Deprecated:  formatMoney(amount, currency, showSymbol)
 */
function formatMoney(amount, a, b) {
  let currency = 'GBP';
  let symbol = true;
"""
MONEY_LEGACY = """  if (a !== null && typeof a === 'object') {
    if (a.currency !== undefined) currency = a.currency;
    if (a.symbol !== undefined) symbol = a.symbol;
  } else {
    // Deprecated positional form.
    if (a !== undefined) currency = a;
    if (b !== undefined) symbol = b;
  }
"""
MONEY_STRICT = """  if (arguments.length > 2 || (a !== undefined && (a === null || typeof a !== 'object'))) {
    throw new TypeError('formatMoney: positional arguments are no longer supported');
  }
  if (a && a.currency !== undefined) currency = a.currency;
  if (a && a.symbol !== undefined) symbol = a.symbol;
"""
MONEY_TAIL = """  const value = (amount / 100).toFixed(2);
  return symbol ? SYMBOLS[currency] + value : value + ' ' + currency;
}

module.exports = { formatMoney };
"""


def _fmt(amount, currency="GBP", symbol=True):
    value = f"{amount / 100:.2f}"
    return SYMBOLS[currency] + value if symbol else f"{value} {currency}"


def _plan():
    """Deterministic description of every service module and its call sites."""
    rng = random.Random(202)
    services = []
    for d in DOMAINS:
        for n in NOUNS:
            alias = rng.random() < 0.15
            funcs = []
            for k in range(rng.randint(2, 4)):
                funcs.append({
                    "name": f"{rng.choice(['render', 'build', 'describe', 'format'])}{rng.choice(['Total', 'Line', 'Header', 'Footer'])}{k}",
                    "label": rng.choice(["Total", "Amount due", "Subtotal", "Shipping", "Balance"]),
                    "form": rng.choice("AABCCDE"),
                    "cur": rng.choice(list(SYMBOLS)),
                    "sym": rng.random() < 0.5,
                })
            services.append({"name": f"{d}_{n}", "alias": alias, "funcs": funcs})
    return services


def _call(fn, f, migrated):
    cur, sym = f"'{f['cur']}'", "true" if f["sym"] else "false"
    form = f["form"]
    if form == "A":
        return f"{fn}(order.total, {{ currency: {cur}, symbol: {sym} }})" if migrated else f"{fn}(order.total, {cur}, {sym})"
    if form == "B":
        return f"{fn}(order.total, {{ currency: order.currency }})" if migrated else f"{fn}(order.total, order.currency)"
    if form == "C":
        if migrated:
            return f"{fn}(\n    order.total + order.shipping,\n    {{ currency: order.currency, symbol: {sym} }}\n  )"
        return f"{fn}(\n    order.total + order.shipping,\n    order.currency,\n    {sym}\n  )"
    if form == "D":
        return f"{fn}(order.total)"
    if migrated:
        return f"{fn}(order.shipping, {{ currency: {cur}, symbol: opts.showSymbol }})"
    return f"{fn}(order.shipping, {cur}, opts.showSymbol)"


def _expected(f, order, show):
    form = f["form"]
    if form == "A":
        value = _fmt(order["total"], f["cur"], f["sym"])
    elif form == "B":
        value = _fmt(order["total"], order["currency"])
    elif form == "C":
        value = _fmt(order["total"] + order["shipping"], order["currency"], f["sym"])
    elif form == "D":
        value = _fmt(order["total"])
    else:
        value = _fmt(order["shipping"], f["cur"], show)
    return f"{f['label']}: {value}"


def _service(svc, migrated):
    fn = "fmt" if svc["alias"] else "formatMoney"
    imp = "const { formatMoney: fmt } = require('../lib/money');" if svc["alias"] else "const { formatMoney } = require('../lib/money');"
    out = ["'use strict';", imp, ""]
    for f in svc["funcs"]:
        out += [f"function {f['name']}(order, opts = {{}}) {{", f"  return `{f['label']}: ${{{_call(fn, f, migrated)}}}`;", "}", ""]
    out.append("module.exports = { " + ", ".join(f["name"] for f in svc["funcs"]) + " };")
    return "\n".join(out) + "\n"


def _write_tests(ws):
    rng = random.Random(303)
    files = []
    for svc in _plan():
        lines = ["'use strict';", "const test = require('node:test');", "const assert = require('node:assert');",
                 f"const m = require('../../src/services/{svc['name']}');", ""]
        for f in svc["funcs"]:
            for show in (True, False):
                order = {"total": rng.randint(100, 99999), "shipping": rng.randint(0, 1500), "currency": rng.choice(list(SYMBOLS))}
                lines.append(
                    f"test('{svc['name']} {f['name']} symbol={str(show).lower()}', () => {{ assert.strictEqual("
                    f"m.{f['name']}({json.dumps(order)}, {{ showSymbol: {str(show).lower()} }}), {json.dumps(_expected(f, order, show), ensure_ascii=False)}); }});"
                )
        files.append(write(ws, f"test/services/{svc['name']}.test.js", "\n".join(lines) + "\n"))
    return files


def setup(ws, truth):
    pkg(ws, "storefront-notifications")
    write(ws, "README.md", "# storefront-notifications\n\nRenders money strings for customer messages. Run `npm test`.\n")
    write(ws, "src/lib/money.js", MONEY_HEAD + MONEY_LEGACY + MONEY_TAIL)
    for svc in _plan():
        write(ws, f"src/services/{svc['name']}.js", _service(svc, migrated=False))
    _write_tests(ws)


def solve(ws, truth):
    write(ws, "src/lib/money.js", MONEY_HEAD + MONEY_STRICT + MONEY_TAIL)
    for svc in _plan():
        write(ws, f"src/services/{svc['name']}.js", _service(svc, migrated=True))


def verify(ws, truth):
    # A strict options-only formatMoney makes any unmigrated call site throw; pristine tests check behaviour.
    write(ws, "src/lib/money.js", MONEY_HEAD + MONEY_STRICT + MONEY_TAIL)
    code, out = node_test(ws, _write_tests(ws))
    return result(code == 0, out)
