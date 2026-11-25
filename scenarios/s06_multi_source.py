"""Join a SQLite database, a CSV file and two MCP-backed APIs into one report."""
import json
import random
import sqlite3
from pathlib import Path

from ._util import load_json, result, write

META = {
    "id": "multi_source",
    "title": "Combine SQLite, CSV and MCP APIs into a report",
    "category": "multi-source data",
    "hypothesis": "Code Mode should help: dozens of MCP calls whose results only need combining.",
    "timeout_s": 1200,
    "mcp": True,
}

PROMPT = (
    "I need an account-risk report for the Q1 2026 business review (1 January to 31 March 2026 inclusive).\n"
    "1. From data/crm.sqlite, find the 10 customers with the highest revenue in Q1 2026, counting only orders "
    "with status 'completed'.\n"
    "2. For each of them, use the issue tracker (available through the `bench` MCP server) to count their "
    "open issues with priority P1.\n"
    "3. data/tenants.csv maps each customer to the service that hosts them. Use the metrics API (also on the "
    "`bench` MCP server) to get that service's Q1 error rate.\n"
    "Write report.json in the repository root: a JSON array ordered by revenue, highest first, of objects with "
    "the keys customer_id, name, revenue_pence, open_p1_issues, error_rate_pct and at_risk. at_risk is true "
    "when open_p1_issues is at least 1 and error_rate_pct is above 2.0."
)

N_CUSTOMERS = 40
WORDS_A = ["Northwind", "Bluebird", "Ironbridge", "Saffron", "Kestrel", "Marlow", "Thistle", "Harbour", "Quill", "Ember"]
WORDS_B = ["Logistics", "Foods", "Systems", "Retail", "Media", "Health", "Energy", "Labs"]


def _build():
    rng = random.Random(606)
    customers, orders, issues, metrics, tenants = [], [], {}, {}, []
    names = rng.sample([f"{a} {b}" for a in WORDS_A for b in WORDS_B], N_CUSTOMERS)
    for n in range(N_CUSTOMERS):
        cid = f"C{n + 1:03d}"
        customers.append((cid, names[n], rng.choice(["enterprise", "growth", "starter"]), rng.choice(["UK", "EU", "US"])))
        service = f"svc-{names[n].split()[0].lower()}-{n + 1:02d}"
        tenants.append((cid, service))
        metrics[service] = {"service": service, "window": "2026-Q1", "requests": rng.randint(200000, 9000000),
                            "error_rate_pct": round(rng.choice([rng.uniform(0.1, 1.9), rng.uniform(2.1, 6.0)]), 2),
                            "p50_ms": rng.randint(20, 400)}
        scale = rng.uniform(0.3, 3.0)
        for _ in range(rng.randint(20, 60)):
            month = rng.choice(["2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04"])
            placed = f"{month}-{rng.randint(1, 28):02d}T{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}:00Z"
            status = rng.choices(["completed", "cancelled", "refunded"], [80, 12, 8])[0]
            orders.append((len(orders) + 1, cid, int(rng.randint(5000, 400000) * scale), placed, status))
        for _ in range(rng.randint(2, 9)):
            iid = f"ISS-{1000 + len(issues)}"
            issues[iid] = {"id": iid, "customer_id": cid,
                           "title": f"{rng.choice(['Timeouts on', 'Wrong totals in', 'Cannot access', 'Slow loading of'])} {rng.choice(['dashboard', 'exports', 'checkout', 'API', 'invoices'])}",
                           "status": rng.choices(["open", "closed"], [55, 45])[0],
                           "priority": rng.choices(["P1", "P2", "P3", "P4"], [25, 30, 30, 15])[0],
                           "created_at": f"2026-0{rng.randint(1, 3)}-{rng.randint(1, 28):02d}"}
    return customers, orders, issues, metrics, tenants


def _report(customers, orders, issues, metrics, tenants):
    revenue = {c[0]: 0 for c in customers}
    for _, cid, amount, placed, status in orders:
        if status == "completed" and "2026-01-01" <= placed[:10] <= "2026-03-31":
            revenue[cid] += amount
    ranked = sorted(revenue.items(), key=lambda kv: -kv[1])
    assert len({v for _, v in ranked[:11]}) == 11, "fixture has a revenue tie; change the seed"
    names, service = {c[0]: c[1] for c in customers}, dict(tenants)
    rows = []
    for cid, value in ranked[:10]:
        p1 = sum(1 for i in issues.values() if i["customer_id"] == cid and i["status"] == "open" and i["priority"] == "P1")
        rate = metrics[service[cid]]["error_rate_pct"]
        rows.append({"customer_id": cid, "name": names[cid], "revenue_pence": value, "open_p1_issues": p1,
                     "error_rate_pct": rate, "at_risk": p1 >= 1 and rate > 2.0})
    return rows


def setup(ws, truth):
    customers, orders, issues, metrics, tenants = _build()
    db_path = Path(ws) / "data" / "crm.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)
    db = sqlite3.connect(db_path)
    db.execute("CREATE TABLE customers (id TEXT PRIMARY KEY, name TEXT NOT NULL, tier TEXT NOT NULL, region TEXT NOT NULL)")
    db.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id), "
               "amount_pence INTEGER NOT NULL, placed_at TEXT NOT NULL, status TEXT NOT NULL)")
    db.executemany("INSERT INTO customers VALUES (?,?,?,?)", customers)
    db.executemany("INSERT INTO orders VALUES (?,?,?,?,?)", orders)
    db.commit()
    db.close()
    write(ws, "data/tenants.csv", "customer_id,service\n" + "".join(f"{c},{s}\n" for c, s in tenants))
    write(ws, "README.md", "# account-review\n\n- data/crm.sqlite: customers and orders (amounts in pence, timestamps in UTC)\n"
          "- data/tenants.csv: which service hosts each customer\n- Issue tracker and service metrics: `bench` MCP server\n")
    # The MCP server reads its data from outside the workspace, so the only route to it is the tools.
    write(truth, "mcp_data.json", json.dumps({"issues": issues, "metrics": metrics}))
    write(truth, "report.json", json.dumps(_report(customers, orders, issues, metrics, tenants), indent=2))


def solve(ws, truth):
    write(ws, "report.json", (Path(truth) / "report.json").read_text())


def verify(ws, truth):
    want = load_json(Path(truth) / "report.json")
    got = load_json(Path(ws) / "report.json")
    if not isinstance(got, list):
        return result(False, "report.json missing or not a JSON array", 0)
    good, notes = 0, []
    for pos, row in enumerate(want):
        mine = got[pos] if pos < len(got) and isinstance(got[pos], dict) else {}
        ok = all(mine.get(k) == row[k] for k in ("customer_id", "name", "revenue_pence", "open_p1_issues", "at_risk"))
        rate = mine.get("error_rate_pct")
        ok = ok and isinstance(rate, (int, float)) and abs(rate - row["error_rate_pct"]) <= 0.011
        good += ok
        if not ok:
            notes.append(f"row {pos}: got {json.dumps(mine)[:160]}, want {json.dumps(row)[:160]}")
    passed = good == len(want) and len(got) == len(want)
    return result(passed, "; ".join(notes[:4]) or "report correct", good / len(want))
