"""Extract tokens, cost, requests and tool calls from Claude Code session transcripts (JSONL)."""
import json
from collections import Counter
from pathlib import Path

PRICING_FILE = Path(__file__).with_name("pricing.json")
CATEGORIES = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")
CODE_MODE_TOOLS = {"REPL", "Poll"}


def load_pricing(path=PRICING_FILE):
    return json.loads(Path(path).read_text())["models"]


def _rows(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def _usage_tokens(usage):
    creation = usage.get("cache_creation") or {}
    w1h = creation.get("ephemeral_1h_input_tokens", 0) or 0
    total_write = usage.get("cache_creation_input_tokens", 0) or 0
    return {
        "input": usage.get("input_tokens", 0) or 0,
        "output": usage.get("output_tokens", 0) or 0,
        "cache_read": usage.get("cache_read_input_tokens", 0) or 0,
        "cache_write_1h": w1h,
        "cache_write_5m": max(creation.get("ephemeral_5m_input_tokens", total_write - w1h) or 0, 0),
    }


def _model_usage_tokens(mu):
    w1h = mu.get("cacheCreationEphemeral1hInputTokens", 0) or 0
    return {
        "input": mu.get("inputTokens", 0) or 0,
        "output": mu.get("outputTokens", 0) or 0,
        "cache_read": mu.get("cacheReadInputTokens", 0) or 0,
        "cache_write_1h": w1h,
        "cache_write_5m": mu.get("cacheCreationEphemeral5mInputTokens", (mu.get("cacheCreationInputTokens", 0) or 0) - w1h) or 0,
    }


def price(tokens_by_model, pricing):
    """Split cost by category. Returns (cost per category, total) or (None, None) for an unpriced model."""
    cost = dict.fromkeys(CATEGORIES, 0.0)
    for model, tokens in tokens_by_model.items():
        rates = pricing.get(model)
        if rates is None:
            return None, None
        for cat in CATEGORIES:
            cost[cat] += tokens[cat] * rates[cat] / 1_000_000
    return cost, sum(cost.values())


def parse_session(paths, pricing=None):
    """Summarise one session. `paths` is the main transcript followed by any subagent transcripts."""
    pricing = load_pricing() if pricing is None else pricing
    messages = {}  # API message id -> (model, usage, is_sidechain); streamed blocks repeat the same usage
    tool_ids, tools, inner_tools = set(), Counter(), Counter()
    cost_state, repl_mode, timestamps, efforts, versions = None, False, [], set(), set()
    for path in paths:
        for row in _rows(path):
            kind = row.get("type")
            if row.get("timestamp") and kind in ("user", "assistant"):
                timestamps.append(row["timestamp"])
            if row.get("version"):
                versions.add(row["version"])
            if kind == "cost-state":
                cost_state = row
            elif kind == "repl-mode":
                repl_mode = repl_mode or row.get("replMode") is True
            elif kind == "assistant":
                msg = row.get("message") or {}
                if msg.get("model") == "<synthetic>" or not msg.get("usage"):
                    continue
                messages[msg.get("id") or row.get("uuid")] = (msg.get("model"), msg["usage"], bool(row.get("isSidechain")))
                if row.get("effort"):
                    efforts.add(row["effort"])
                for block in msg.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("id") not in tool_ids:
                        tool_ids.add(block.get("id"))
                        tools[block.get("name")] += 1
            elif kind == "user":
                res = row.get("toolUseResult")
                if isinstance(res, dict) and isinstance(res.get("toolsUsed"), list):
                    inner_tools.update(str(t) for t in res["toolsUsed"])

    by_model, peak = {}, 0
    for model, usage, _ in messages.values():
        t = _usage_tokens(usage)
        agg = by_model.setdefault(model, dict.fromkeys(CATEGORIES, 0))
        for cat in CATEGORIES:
            agg[cat] += t[cat]
        peak = max(peak, t["input"] + t["cache_read"] + t["cache_write_5m"] + t["cache_write_1h"])

    source = "transcript-messages"
    reported = None
    if cost_state and cost_state.get("modelUsage"):
        # The CLI's own session accounting: includes auxiliary requests (titles, summaries) and subagents.
        by_model = {m: _model_usage_tokens(mu) for m, mu in cost_state["modelUsage"].items()}
        reported = cost_state.get("totalCostUSD")
        source = "cli-cost-state"

    tokens = dict.fromkeys(CATEGORIES, 0)
    for t in by_model.values():
        for cat in CATEGORIES:
            tokens[cat] += t[cat]
    tokens["total"] = sum(tokens[c] for c in CATEGORIES)
    cost, computed = price(by_model, pricing)
    total = reported if reported is not None else computed
    return {
        "usage_source": source,
        "tokens": tokens,
        "tokens_by_model": by_model,
        "cost_by_category_usd": cost,
        "cost_computed_usd": computed,
        "cost_reported_usd": reported,
        "cost_usd": total,
        "cost_split_exact": bool(computed is not None and total is not None and abs(computed - total) <= max(0.0005, 0.01 * total)),
        "requests": len(messages),
        "subagent_requests": sum(1 for m in messages.values() if m[2]),
        "peak_context_tokens": peak,
        "tool_calls": dict(tools),
        "tool_calls_total": sum(tools.values()),
        "code_runs": tools.get("REPL", 0),
        "tools_used_in_code": sorted(inner_tools),  # names only; the CLI does not record per-call counts
        "repl_mode_row": repl_mode,
        "api_duration_s": (cost_state or {}).get("totalAPIDuration", 0) / 1000 if cost_state else None,
        "tool_duration_s": (cost_state or {}).get("totalToolDuration", 0) / 1000 if cost_state else None,
        "first_timestamp": min(timestamps) if timestamps else None,
        "last_timestamp": max(timestamps) if timestamps else None,
        "effort": sorted(efforts),
        "claude_code_version": sorted(versions),
    }


def arm_check(arm, summary, banner_seen):
    """Confirm the session really ran in the intended mode. Returns (ok, reason)."""
    names = set(summary["tool_calls"])
    used_code = bool(names & CODE_MODE_TOOLS)
    if arm == "codemode":
        if not (banner_seen or summary["repl_mode_row"] or used_code):
            return False, "no sign that Code Mode was active"
        if names - CODE_MODE_TOOLS and not used_code:
            return False, f"direct tool calls only: {sorted(names)}"
        return True, ""
    if used_code or banner_seen or summary["repl_mode_row"]:
        return False, "Code Mode was active in a baseline run"
    return True, ""
