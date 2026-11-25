"""Generate a validator module and test file for 11 entities, following one worked example."""
import json
from pathlib import Path

from ._util import load_json, pkg, result, run, write

META = {
    "id": "codegen_scaffold",
    "title": "Scaffold 22 files from a schema and one example",
    "category": "code generation",
    "hypothesis": "Unclear: many similar files to write, but output tokens dominate either way.",
    "timeout_s": 1200,
}

PROMPT = (
    "src/validators/user.js and test/validators/user.test.js implement the validator for the `user` "
    "entity in schema/entities.json, following the contract in docs/validators.md. Create the equivalent "
    "validator module and test file for every other entity in the schema, following the same pattern. "
    "`npm test` must pass."
)

S, I, B, E, N = "string", "integer", "boolean", "email", "enum"
ENTITIES = {
    "user": [("name", S, True, 2, 50), ("email", E, True), ("age", I, False, 13, 120), ("role", N, True, ["admin", "member", "guest"]), ("active", B, False)],
    "product": [("sku", S, True, 4, 12), ("title", S, True, 1, 80), ("pricePence", I, True, 1, 1000000), ("status", N, True, ["draft", "live", "retired"]), ("taxable", B, False)],
    "order": [("reference", S, True, 6, 20), ("customerEmail", E, True), ("itemCount", I, True, 1, 500), ("state", N, True, ["pending", "paid", "shipped", "cancelled"]), ("gift", B, False)],
    "invoice": [("number", S, True, 5, 16), ("billingEmail", E, True), ("totalPence", I, True, 0, 50000000), ("currency", N, True, ["GBP", "USD", "EUR"]), ("paid", B, True)],
    "address": [("line1", S, True, 1, 100), ("line2", S, False, 1, 100), ("city", S, True, 1, 60), ("postcode", S, True, 3, 10), ("country", N, True, ["GB", "IE", "FR", "DE", "US"])],
    "shipment": [("trackingCode", S, True, 8, 30), ("carrier", N, True, ["royalmail", "dpd", "ups"]), ("weightGrams", I, True, 1, 30000), ("signed", B, False), ("contactEmail", E, False)],
    "coupon": [("code", S, True, 4, 16), ("percentOff", I, True, 1, 100), ("kind", N, True, ["single", "multi"]), ("maxUses", I, False, 1, 100000), ("enabled", B, True)],
    "review": [("title", S, True, 3, 80), ("body", S, False, 10, 2000), ("rating", I, True, 1, 5), ("authorEmail", E, True), ("verified", B, False)],
    "subscription": [("plan", N, True, ["free", "team", "enterprise"]), ("seats", I, True, 1, 5000), ("ownerEmail", E, True), ("autoRenew", B, True), ("note", S, False, 1, 200)],
    "warehouse": [("code", S, True, 3, 8), ("name", S, True, 2, 60), ("capacity", I, True, 0, 1000000), ("region", N, True, ["north", "south", "east", "west"]), ("refrigerated", B, False)],
    "supplier": [("name", S, True, 2, 80), ("contactEmail", E, True), ("leadTimeDays", I, False, 0, 365), ("tier", N, True, ["gold", "silver", "bronze"]), ("approved", B, True)],
    "ticket": [("subject", S, True, 5, 120), ("requesterEmail", E, True), ("priority", N, True, ["low", "normal", "high", "urgent"]), ("reopenCount", I, False, 0, 50), ("escalated", B, False)],
}

DOCS = """# Validator contract

Each entity in `schema/entities.json` has a module `src/validators/<entity>.js` exporting
`validate(input)` and a test file `test/validators/<entity>.test.js`.

`validate(input)` returns `{ valid, errors }`. `errors` is an array of `{ field, rule }` objects and
`valid` is `true` exactly when `errors` is empty. If `input` is not a plain object the result is
`{ valid: false, errors: [{ field: null, rule: 'type' }] }`.

Rules, applied per field (at most one error per field):

1. A field that is `undefined` or `null` is missing. Missing + `required: true` gives rule `required`.
   Missing optional fields are skipped.
2. `string`: must be a string (rule `type`); length must be within `minLength..maxLength` (rule `length`).
3. `integer`: must be an integer number, not a numeric string (rule `type`); must be within `min..max` (rule `range`).
4. `boolean`: must be `true` or `false` (rule `type`).
5. `email`: must be a string (rule `type`) matching `/^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$/` (rule `format`).
6. `enum`: must be one of `values` (rule `enum`).

Unknown properties are ignored.
"""


def _schema():
    out = {}
    for name, fields in ENTITIES.items():
        specs = []
        for f in fields:
            spec = {"name": f[0], "type": f[1], "required": f[2]}
            if f[1] == S:
                spec.update(minLength=f[3], maxLength=f[4])
            elif f[1] == I:
                spec.update(min=f[3], max=f[4])
            elif f[1] == N:
                spec["values"] = f[3]
            specs.append(spec)
        out[name] = {"fields": specs}
    return out


def _check(f):
    v = f"input.{f['name']}"
    q = f"'{f['name']}'"
    t = f["type"]
    if t == S:
        body = (f"else if (typeof {v} !== 'string') errors.push({{ field: {q}, rule: 'type' }});\n"
                f"  else if ({v}.length < {f['minLength']} || {v}.length > {f['maxLength']}) errors.push({{ field: {q}, rule: 'length' }});")
    elif t == I:
        body = (f"else if (!Number.isInteger({v})) errors.push({{ field: {q}, rule: 'type' }});\n"
                f"  else if ({v} < {f['min']} || {v} > {f['max']}) errors.push({{ field: {q}, rule: 'range' }});")
    elif t == B:
        body = f"else if (typeof {v} !== 'boolean') errors.push({{ field: {q}, rule: 'type' }});"
    elif t == E:
        body = (f"else if (typeof {v} !== 'string') errors.push({{ field: {q}, rule: 'type' }});\n"
                f"  else if (!EMAIL.test({v})) errors.push({{ field: {q}, rule: 'format' }});")
    else:
        body = f"else if (!{json.dumps(f['values'])}.includes({v})) errors.push({{ field: {q}, rule: 'enum' }});"
    missing = f"errors.push({{ field: {q}, rule: 'required' }});" if f["required"] else "/* optional */;"
    return f"  // {f['name']}: {t}{', required' if f['required'] else ''}\n  if ({v} === undefined || {v} === null) {missing}\n  {body}\n"


def _validator(name, fields):
    return (
        "'use strict';\n"
        f"// Validator for the \"{name}\" entity. Contract: docs/validators.md\n"
        "const EMAIL = /^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$/;\n\n"
        "function validate(input) {\n"
        "  if (input === null || typeof input !== 'object' || Array.isArray(input)) {\n"
        "    return { valid: false, errors: [{ field: null, rule: 'type' }] };\n"
        "  }\n"
        "  const errors = [];\n"
        + "".join(_check(f) for f in fields)
        + "  return { valid: errors.length === 0, errors };\n}\n\nmodule.exports = { validate };\n"
    )


def _good(f):
    t = f["type"]
    if t == S:
        return "a" * ((f["minLength"] + f["maxLength"]) // 2)
    if t == I:
        return (f["min"] + f["max"]) // 2
    if t == B:
        return True
    if t == E:
        return "someone@example.com"
    return f["values"][0]


def _samples(fields):
    """Inputs with the expected verdict and, for invalid ones, the field that must be reported."""
    valid = {f["name"]: _good(f) for f in fields}
    out = [{"input": valid, "valid": True, "field": None},
           {"input": {f["name"]: _good(f) for f in fields if f["required"]}, "valid": True, "field": None},
           {"input": dict(valid, unknownExtra=1), "valid": True, "field": None},
           {"input": None, "valid": False, "field": None},
           {"input": "text", "valid": False, "field": None}]
    for f in fields:
        t, bad = f["type"], []
        if t == S:
            bad = [123, "a" * (f["maxLength"] + 1)] + (["a" * (f["minLength"] - 1)] if f["minLength"] > 0 else [])
        elif t == I:
            bad = [str(_good(f)), f["min"] + 0.5, f["max"] + 1, f["min"] - 1]
        elif t == B:
            bad = ["true", 1]
        elif t == E:
            bad = ["not-an-email", "two@@example.com", 42]
        else:
            bad = ["__not_a_member__"]
        for value in bad:
            out.append({"input": dict(valid, **{f["name"]: value}), "valid": False, "field": f["name"]})
        if f["required"]:
            out.append({"input": {k: v for k, v in valid.items() if k != f["name"]}, "valid": False, "field": f["name"]})
            out.append({"input": dict(valid, **{f["name"]: None}), "valid": False, "field": f["name"]})
        else:
            out.append({"input": dict(valid, **{f["name"]: None}), "valid": True, "field": None})
    return out


def _test(name, fields):
    lines = ["'use strict';", "const test = require('node:test');", "const assert = require('node:assert');",
             f"const {{ validate }} = require('../../src/validators/{name}');", "",
             f"const valid = {json.dumps({f['name']: _good(f) for f in fields})};", "",
             f"test('{name}: accepts a valid object', () => {{ assert.deepStrictEqual(validate(valid), {{ valid: true, errors: [] }}); }});",
             f"test('{name}: rejects non-objects', () => {{ assert.strictEqual(validate(null).valid, false); }});"]
    for f in fields:
        if f["required"]:
            lines.append(f"test('{name}: {f['name']} is required', () => {{ const input = {{ ...valid }}; delete input.{f['name']}; "
                         f"assert.deepStrictEqual(validate(input).errors, [{{ field: '{f['name']}', rule: 'required' }}]); }});")
        else:
            lines.append(f"test('{name}: {f['name']} is optional', () => {{ const input = {{ ...valid }}; delete input.{f['name']}; "
                         f"assert.strictEqual(validate(input).valid, true); }});")
    return "\n".join(lines) + "\n"


RUNNER = """'use strict';
const fs = require('node:fs');
const path = require('node:path');
const samples = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const out = {};
for (const [name, list] of Object.entries(samples)) {
  try {
    const { validate } = require(path.resolve('src/validators', name + '.js'));
    out[name] = list.every((s) => {
      const r = validate(s.input);
      if (!r || r.valid !== s.valid) return false;
      if (s.valid) return Array.isArray(r.errors) && r.errors.length === 0;
      return s.field === null || (Array.isArray(r.errors) && r.errors.some((e) => e && e.field === s.field));
    });
  } catch (err) { out[name] = false; }
}
console.log(JSON.stringify(out));
"""


def setup(ws, truth):
    schema = _schema()
    pkg(ws, "entity-validators")
    write(ws, "README.md", "# entity-validators\n\nSee docs/validators.md. Run `npm test`.\n")
    write(ws, "docs/validators.md", DOCS)
    write(ws, "schema/entities.json", json.dumps(schema, indent=2) + "\n")
    write(ws, "src/validators/user.js", _validator("user", schema["user"]["fields"]))
    write(ws, "test/validators/user.test.js", _test("user", schema["user"]["fields"]))
    write(truth, "samples.json", json.dumps({n: _samples(e["fields"]) for n, e in schema.items()}))
    write(truth, "check.js", RUNNER)


def solve(ws, truth):
    for name, entity in _schema().items():
        write(ws, f"src/validators/{name}.js", _validator(name, entity["fields"]))
        write(ws, f"test/validators/{name}.test.js", _test(name, entity["fields"]))


def verify(ws, truth):
    code, out = run(["node", str(Path(truth) / "check.js"), str(Path(truth) / "samples.json")], ws)
    try:
        verdicts = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return result(False, f"checker failed: {out}", 0)
    names = list(ENTITIES)
    missing_tests = [n for n in names if not (Path(ws) / f"test/validators/{n}.test.js").exists()]
    ok = [n for n in names if verdicts.get(n) and n not in missing_tests]
    suite_code, suite_out = run(["node", "--test"], ws)
    passed = len(ok) == len(names) and suite_code == 0
    detail = (f"correct entities {len(ok)}/{len(names)}; wrong validators: {[n for n in names if not verdicts.get(n)]}; "
              f"missing tests: {missing_tests}; npm test exit {suite_code}\n{suite_out[-600:] if suite_code else ''}")
    return result(passed, detail, len(ok) / len(names) * (1 if suite_code == 0 else 0.5))
