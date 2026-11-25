"""Answer questions about a week of access logs (84,000 lines)."""
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from ._util import load_json, result, write

META = {
    "id": "log_analysis",
    "title": "Analyse a week of access logs",
    "category": "data analysis",
    "hypothesis": "Unclear: both arms can write one script; Code Mode may save a round trip or two.",
    "timeout_s": 900,
}

PROMPT = (
    "The logs/ directory holds a week of access logs (format described in logs/README.md). Analyse all of "
    "them and write answers.json in the repository root with exactly these keys:\n"
    "- total_requests: number of log lines\n"
    "- error_rate_5xx_pct: percentage of requests with a 5xx status, rounded to 2 decimal places\n"
    "- slowest_endpoint: the path with the highest mean latency\n"
    "- top_users: the 5 user ids with the most requests, most active first\n"
    "- busiest_hour: the UTC hour with the most requests, formatted like 2026-03-04T15\n"
    "- errors_5xx_by_endpoint: object mapping every path to its number of 5xx responses"
)

ENDPOINTS = [  # path, method, weight, mean latency ms, 5xx probability
    ("/api/orders", "GET", 30, 120, 0.010), ("/api/orders", "POST", 8, 260, 0.030),
    ("/api/products", "GET", 40, 60, 0.004), ("/api/search", "GET", 25, 340, 0.020),
    ("/api/cart", "POST", 15, 90, 0.008), ("/api/checkout", "POST", 6, 480, 0.050),
    ("/api/users/me", "GET", 20, 45, 0.003), ("/api/reports/export", "GET", 2, 1900, 0.080),
    ("/healthz", "GET", 10, 5, 0.001),
]
DAYS, PER_DAY, USERS = 7, 12000, 300
HOUR_WEIGHTS = [2, 1, 1, 1, 1, 2, 4, 7, 10, 12, 13, 13, 12, 12, 13, 14, 12, 10, 8, 7, 6, 5, 4, 3]


def _generate(ws):
    rng = random.Random(505)
    user_w = [1.0 / (u + 1) ** 0.9 for u in range(USERS)]
    ep_w = [e[2] for e in ENDPOINTS]
    ids = rng.sample(range(1000, 10000), USERS)  # activity rank must not be guessable from the id
    total = errors = 0
    lat_sum, lat_n = defaultdict(int), Counter()
    users, hours, err_by = Counter(), Counter(), Counter({e[0]: 0 for e in ENDPOINTS})
    for d in range(DAYS):
        day = f"2026-03-{d + 1:02d}"
        boost = rng.randrange(24)  # each day has one unusually busy hour
        weights = [w * (1.6 if h == boost else 1) for h, w in enumerate(HOUR_WEIGHTS)]
        stamps = sorted((h, rng.randrange(3600)) for h in rng.choices(range(24), weights, k=PER_DAY))
        lines = []
        for h, s in stamps:
            path, method, _, mean, p5 = rng.choices(ENDPOINTS, ep_w)[0]
            user = f"u{ids[rng.choices(range(USERS), user_w)[0]]}"
            roll = rng.random()
            status = rng.choice([500, 502, 503]) if roll < p5 else (rng.choice([400, 401, 404]) if roll < p5 + 0.03 else (201 if method == "POST" else 200))
            ms = max(1, int(rng.gauss(mean, mean * 0.25)))
            lines.append(f"{day}T{h:02d}:{s // 60:02d}:{s % 60:02d}Z {method} {path} {status} {ms}ms user={user}")
            total += 1
            errors += status >= 500
            err_by[path] += status >= 500
            lat_sum[path] += ms
            lat_n[path] += 1
            users[user] += 1
            hours[f"{day}T{h:02d}"] += 1
        if ws is not None:
            write(ws, f"logs/access-{day}.log", "\n".join(lines) + "\n")
    top = users.most_common(6)
    busiest = hours.most_common(2)
    assert len({c for _, c in top}) == 6 and busiest[0][1] != busiest[1][1], "fixture has ties; change the seed"
    return {
        "total_requests": total,
        "error_rate_5xx_pct": round(100 * errors / total, 2),
        "slowest_endpoint": max(lat_n, key=lambda p: lat_sum[p] / lat_n[p]),
        "top_users": [u for u, _ in top[:5]],
        "busiest_hour": busiest[0][0],
        "errors_5xx_by_endpoint": dict(err_by),
    }


def setup(ws, truth):
    answers = _generate(ws)
    write(ws, "logs/README.md", "# Access logs\n\nOne file per UTC day. One request per line:\n\n"
          "    <ISO timestamp, UTC> <METHOD> <path> <status> <latency>ms user=<user id>\n\n"
          "Example: `2026-03-01T09:14:07Z GET /api/orders 200 131ms user=u1042`\n")
    write(truth, "answers.json", json.dumps(answers, indent=2))


def solve(ws, truth):
    write(ws, "answers.json", (Path(truth) / "answers.json").read_text())


def verify(ws, truth):
    want = load_json(Path(truth) / "answers.json")
    got = load_json(Path(ws) / "answers.json")
    if not isinstance(got, dict):
        return result(False, "answers.json missing or not a JSON object", 0)
    wrong = []
    for key, value in want.items():
        mine = got.get(key)
        if key == "error_rate_5xx_pct":
            ok = isinstance(mine, (int, float)) and abs(mine - value) <= 0.011
        else:
            ok = mine == value
        if not ok:
            wrong.append(f"{key}: got {json.dumps(mine)[:200]}, want {json.dumps(value)[:200]}")
    return result(not wrong, "; ".join(wrong) or "all answers correct", 1 - len(wrong) / len(want))
