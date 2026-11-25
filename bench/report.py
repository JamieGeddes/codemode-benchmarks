"""Aggregate per-run records into summary.csv and report.md."""
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import median

ARMS = ("baseline", "codemode")
METRICS = [  # key, label, format
    ("cost_usd", "Cost $", "{:.4f}"),
    ("tokens_total", "Tokens", "{:,.0f}"),
    ("requests", "API requests", "{:.0f}"),
    ("wall_s", "Wall s", "{:.0f}"),
]
CSV_METRICS = ["cost_usd", "cost_input_usd", "cost_output_usd", "cost_cache_read_usd", "cost_cache_write_usd",
               "tokens_total", "tokens_input", "tokens_output", "tokens_cache_read", "tokens_cache_write",
               "requests", "tool_calls_total", "peak_context_tokens", "wall_s"]


def load(results_dir):
    path = Path(results_dir) / "results.jsonl"
    if not path.exists():
        return []
    latest = {}
    for line in path.read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            latest[rec["run_key"]] = rec  # a re-run replaces the earlier record
    return list(latest.values())


def flat(rec):
    """Flatten one record to the numeric fields used in the tables."""
    tok, cost = rec.get("tokens") or {}, rec.get("cost_by_category_usd") or {}
    return {
        "cost_usd": rec.get("cost_usd"),
        "cost_input_usd": cost.get("input"),
        "cost_output_usd": cost.get("output"),
        "cost_cache_read_usd": cost.get("cache_read"),
        "cost_cache_write_usd": (cost.get("cache_write_5m") or 0) + (cost.get("cache_write_1h") or 0) if cost else None,
        "tokens_total": tok.get("total"),
        "tokens_input": tok.get("input"),
        "tokens_output": tok.get("output"),
        "tokens_cache_read": tok.get("cache_read"),
        "tokens_cache_write": (tok.get("cache_write_5m") or 0) + (tok.get("cache_write_1h") or 0) if tok else None,
        "requests": rec.get("requests"),
        "tool_calls_total": rec.get("tool_calls_total"),
        "peak_context_tokens": rec.get("peak_context_tokens"),
        "wall_s": rec.get("wall_s"),
    }


def stats(values):
    values = [v for v in values if v is not None]
    if not values:
        return None
    return {"median": median(values), "min": min(values), "max": max(values), "n": len(values)}


def aggregate(records):
    """Group valid runs by (model, scenario, arm). Invalid runs (harness faults) are excluded and counted."""
    groups = defaultdict(list)
    for rec in records:
        groups[(rec["model"], rec["scenario"], rec["arm"])].append(rec)
    out = {}
    for key, recs in groups.items():
        valid = [r for r in recs if r.get("valid")]
        rows = [flat(r) for r in valid]
        out[key] = {
            "runs": len(recs), "valid": len(valid), "passed": sum(1 for r in valid if r.get("passed")),
            "mean_score": sum(r.get("score") or 0 for r in valid) / len(valid) if valid else None,
            "stats": {m: stats([row[m] for row in rows]) for m in CSV_METRICS},
        }
    return out


def delta(base, code):
    """Percentage change of the Code Mode median against the baseline median, and whether ranges are disjoint."""
    if not base or not code or not base["median"]:
        return None, False
    pct = 100 * (code["median"] - base["median"]) / base["median"]
    disjoint = code["max"] < base["min"] or code["min"] > base["max"]
    return pct, disjoint


def _cell(stat, fmt):
    return fmt.format(stat["median"]) if stat else "n/a"


def _delta_cell(base, code):
    pct, disjoint = delta(base, code)
    if pct is None:
        return "n/a"
    return f"{pct:+.0f}%" + ("" if disjoint else " ~")


def write_csv(results_dir, agg):
    path = Path(results_dir) / "summary.csv"
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["model", "scenario", "arm", "runs", "valid_runs", "passed", "mean_score"]
                   + [f"{m}_{s}" for m in CSV_METRICS for s in ("median", "min", "max")])
        for (model, scenario, arm), g in sorted(agg.items()):
            row = [model, scenario, arm, g["runs"], g["valid"], g["passed"], g["mean_score"]]
            for m in CSV_METRICS:
                st = g["stats"][m]
                row += [st["median"], st["min"], st["max"]] if st else ["", "", ""]
            w.writerow(row)
    return path


def render(results_dir, records, manifest=None, scenario_meta=None):
    agg = aggregate(records)
    scenario_meta = scenario_meta or {}
    models = sorted({k[0] for k in agg})
    lines = ["# Code Mode benchmark report", ""]
    if manifest:
        lines += [f"- Run: `{manifest.get('run_id')}` started {manifest.get('started_at')}",
                  f"- Claude Code: {manifest.get('claude_version')}; permission mode `{manifest.get('permission_mode')}`; "
                  f"effort `{manifest.get('effort') or 'default'}`",
                  f"- Repeats per scenario and arm: {manifest.get('repeats')}", ""]
    lines += ["Both arms use the same prompts, fixtures, model, settings and harness; the only difference is "
              "`CLAUDE_CODE_EXPERIMENTAL_CODE_MODE`. Figures are medians over valid runs. Δ is Code Mode relative to "
              "baseline (negative means Code Mode used less). A trailing `~` means the two arms' min-max ranges overlap, "
              "so the difference is within run-to-run noise.", ""]

    lines += ["## Totals", "", "| Model | Arm | Runs | Valid | Passed | Input tok | Output tok | Cache read tok | Cache write tok | "
              "Input $ | Output $ | Cache read $ | Cache write $ | Total $ |", "|" + "---|" * 14]
    grand = 0.0
    for model in models:
        for arm in ARMS:
            recs = [r for r in records if r["model"] == model and r["arm"] == arm]
            if not recs:
                continue
            rows = [flat(r) for r in recs]  # totals include invalid runs: they were still paid for
            s = lambda k: sum(row[k] or 0 for row in rows)
            grand += s("cost_usd")
            lines.append(f"| {model} | {arm} | {len(recs)} | {sum(1 for r in recs if r.get('valid'))} | "
                         f"{sum(1 for r in recs if r.get('valid') and r.get('passed'))} | {s('tokens_input'):,.0f} | "
                         f"{s('tokens_output'):,.0f} | {s('tokens_cache_read'):,.0f} | {s('tokens_cache_write'):,.0f} | "
                         f"{s('cost_input_usd'):.2f} | {s('cost_output_usd'):.2f} | {s('cost_cache_read_usd'):.2f} | "
                         f"{s('cost_cache_write_usd'):.2f} | {s('cost_usd'):.2f} |")
    lines += ["", f"**Total cost of this benchmark run: ${grand:.2f}** (list prices as reported by Claude Code).", ""]

    for model in models:
        lines += [f"## {model}", "", "| Scenario | Category | Pass base | Pass code | "
                  + " | ".join(f"{label} base | {label} code | Δ" for _, label, _ in METRICS) + " |",
                  "|" + "---|" * (4 + 3 * len(METRICS))]
        scenarios = sorted({k[1] for k in agg if k[0] == model}, key=lambda s: list(scenario_meta).index(s) if s in scenario_meta else 99)
        for scenario in scenarios:
            b, c = agg.get((model, scenario, "baseline")), agg.get((model, scenario, "codemode"))
            cells = [scenario, scenario_meta.get(scenario, {}).get("category", ""),
                     f"{b['passed']}/{b['valid']}" if b else "n/a", f"{c['passed']}/{c['valid']}" if c else "n/a"]
            for key, _, fmt in METRICS:
                bs, cs = (b or {}).get("stats", {}).get(key), (c or {}).get("stats", {}).get(key)
                cells += [_cell(bs, fmt), _cell(cs, fmt), _delta_cell(bs, cs)]
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")

    invalid = [r for r in records if not r.get("valid")]
    if invalid:
        lines += ["## Invalid runs (excluded from medians, included in totals)", ""]
        lines += [f"- `{r['run_key']}`: {r.get('status')} {r.get('invalid_reason') or ''}".rstrip() for r in invalid]
        lines.append("")
    inexact = [r["run_key"] for r in records if r.get("cost_usd") and not r.get("cost_split_exact")]
    if inexact:
        lines += ["## Notes", "", f"- The per-category cost split differs from the reported total by more than 1% in "
                  f"{len(inexact)} run(s) (for example `{inexact[0]}`); the reported total is used for Cost $.", ""]
    path = Path(results_dir) / "report.md"
    path.write_text("\n".join(lines) + "\n")
    write_csv(results_dir, agg)
    return path
