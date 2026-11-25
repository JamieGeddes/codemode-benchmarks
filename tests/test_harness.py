"""Harness tests. No API usage: `python3 -m unittest discover -s tests -t .`"""
import json
import tempfile
import unittest
from pathlib import Path

from bench import __main__ as cli
from bench import mcp_server, report, transcript

PRICING = transcript.load_pricing()


def assistant(mid, model, usage, blocks, sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain, "timestamp": "2026-01-01T00:00:01Z", "version": "2.1.332",
            "message": {"id": mid, "model": model, "usage": usage, "content": blocks}}


def usage(inp, out, read, w1h, w5m=0):
    return {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": read, "cache_creation_input_tokens": w1h + w5m,
            "cache_creation": {"ephemeral_1h_input_tokens": w1h, "ephemeral_5m_input_tokens": w5m}}


def write_jsonl(rows):
    fh = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False)
    fh.write("\n".join(json.dumps(r) for r in rows) + "\nnot json\n")
    fh.close()
    return fh.name


class TranscriptTests(unittest.TestCase):
    def test_streamed_blocks_are_counted_once(self):
        u = usage(10, 100, 1000, 500, 50)
        path = write_jsonl([
            assistant("m1", "claude-sonnet-5-5", u, [{"type": "thinking"}]),
            assistant("m1", "claude-sonnet-5-5", u, [{"type": "tool_use", "id": "t1", "name": "Bash"}]),
            assistant("m1", "claude-sonnet-5-5", u, [{"type": "tool_use", "id": "t2", "name": "Read"}]),
            assistant("m2", "claude-sonnet-5-5", usage(5, 20, 2000, 0), [{"type": "text", "text": "done"}]),
        ])
        s = transcript.parse_session([path], PRICING)
        self.assertEqual(s["requests"], 2)
        self.assertEqual(s["tool_calls"], {"Bash": 1, "Read": 1})
        self.assertEqual(s["tokens"], {"input": 15, "output": 120, "cache_read": 3000, "cache_write_1h": 500, "cache_write_5m": 50, "total": 3685})
        self.assertEqual(s["peak_context_tokens"], 2005)
        expected = (15 * 2 + 120 * 10 + 3000 * 0.1 + 500 * 4 + 50 * 2.5) / 1e6
        self.assertAlmostEqual(s["cost_usd"], expected)
        self.assertEqual(s["usage_source"], "transcript-messages")

    def test_cli_cost_record_is_authoritative_and_split_matches(self):
        # Figures from a real Haiku 5.5 session recorded while building the suite.
        cost_state = {"type": "cost-state", "totalCostUSD": 0.0053866, "totalAPIDuration": 6819, "totalToolDuration": 0, "modelUsage": {
            "claude-haiku-5-5": {"inputTokens": 1220, "outputTokens": 1110, "cacheReadInputTokens": 0, "cacheCreationInputTokens": 23548,
                                 "cacheCreationEphemeral5mInputTokens": 0, "cacheCreationEphemeral1hInputTokens": 23548, "costUSD": 0.0053866}}}
        path = write_jsonl([assistant("m1", "claude-haiku-5-5", usage(2, 1087, 0, 23548), [{"type": "text", "text": "x"}]),
                            {"type": "repl-mode", "replMode": True}, cost_state])
        s = transcript.parse_session([path], PRICING)
        self.assertEqual(s["usage_source"], "cli-cost-state")
        self.assertEqual(s["tokens"]["input"], 1220)
        self.assertAlmostEqual(s["cost_usd"], 0.0053866)
        self.assertAlmostEqual(s["cost_computed_usd"], 0.0053866, places=7)
        self.assertTrue(s["cost_split_exact"])
        self.assertTrue(s["repl_mode_row"])

    def test_unpriced_model_keeps_tokens(self):
        path = write_jsonl([assistant("m1", "mystery-model", usage(1, 2, 3, 4), [])])
        s = transcript.parse_session([path], PRICING)
        self.assertIsNone(s["cost_usd"])
        self.assertEqual(s["tokens"]["total"], 10)

    def test_arm_check(self):
        base = {"tool_calls": {"Bash": 2}, "repl_mode_row": False}
        code = {"tool_calls": {"REPL": 1}, "repl_mode_row": True}
        self.assertTrue(transcript.arm_check("baseline", base, False)[0])
        self.assertTrue(transcript.arm_check("codemode", code, True)[0])
        self.assertFalse(transcript.arm_check("baseline", code, False)[0])
        self.assertFalse(transcript.arm_check("codemode", base, False)[0])
        self.assertTrue(transcript.arm_check("codemode", {"tool_calls": {}, "repl_mode_row": True}, False)[0])


class PlanTests(unittest.TestCase):
    def test_plan_is_balanced_paired_and_reproducible(self):
        plan = cli.build_plan(["a", "b", "c"], ["m1", "m2"], 3, ["baseline", "codemode"], seed=7)
        self.assertEqual(len(plan), 36)
        self.assertEqual(len({t["run_key"] for t in plan}), 36)
        self.assertEqual(plan, cli.build_plan(["a", "b", "c"], ["m1", "m2"], 3, ["baseline", "codemode"], seed=7))
        for first, second in zip(plan[::2], plan[1::2]):
            self.assertEqual((first["scenario"], first["model"], first["repeat"]), (second["scenario"], second["model"], second["repeat"]))
            self.assertNotEqual(first["arm"], second["arm"])
        self.assertEqual({t["arm"] for t in plan[::2]}, {"baseline", "codemode"})  # both arms get to go first


class ReportTests(unittest.TestCase):
    def record(self, arm, rep, cost, valid=True, passed=True):
        tok = {"input": 10, "output": 20, "cache_read": 30, "cache_write_5m": 0, "cache_write_1h": 40, "total": 100}
        return {"run_key": f"s__m__{arm}__r{rep}", "scenario": "s", "model": "m", "arm": arm, "repeat": rep, "valid": valid,
                "passed": passed, "score": 1.0, "status": "completed", "invalid_reason": "" if valid else "broken",
                "cost_usd": cost, "cost_split_exact": True, "tokens": tok, "requests": 4, "tool_calls_total": 3, "peak_context_tokens": 9,
                "wall_s": 12.0, "cost_by_category_usd": {"input": cost / 4, "output": cost / 4, "cache_read": cost / 4, "cache_write_5m": 0, "cache_write_1h": cost / 4}}

    def test_medians_deltas_and_totals(self):
        recs = [self.record("baseline", r, c) for r, c in enumerate([1.0, 1.2, 1.1])]
        recs += [self.record("codemode", r, c) for r, c in enumerate([0.5, 0.6, 0.55])]
        recs.append(self.record("codemode", 9, 5.0, valid=False))
        agg = report.aggregate(recs)
        base, code = agg[("m", "s", "baseline")], agg[("m", "s", "codemode")]
        self.assertEqual((code["runs"], code["valid"]), (4, 3))
        pct, disjoint = report.delta(base["stats"]["cost_usd"], code["stats"]["cost_usd"])
        self.assertAlmostEqual(pct, -50.0)
        self.assertTrue(disjoint)
        self.assertFalse(report.delta(base["stats"]["requests"], code["stats"]["requests"])[1])
        with tempfile.TemporaryDirectory() as tmp:
            text = report.render(tmp, recs).read_text()
            self.assertIn("**Total cost of this benchmark run: $9.95**", text)
            self.assertIn("-50%", text)
            self.assertIn("Invalid runs", text)
            self.assertTrue((Path(tmp) / "summary.csv").exists())

    def test_rerun_replaces_earlier_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = [self.record("baseline", 1, 1.0), self.record("baseline", 1, 2.0)]
            (Path(tmp) / "results.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            loaded = report.load(tmp)
            self.assertEqual([r["cost_usd"] for r in loaded], [2.0])


class McpServerTests(unittest.TestCase):
    DATA = {"issues": {f"I{n}": {"id": f"I{n}", "customer_id": "C1", "title": "t", "status": "open" if n % 2 else "closed", "priority": "P1"} for n in range(12)},
            "metrics": {"svc": {"service": "svc", "error_rate_pct": 2.5}}}

    def test_search_paginates_and_filters(self):
        seen, cursor = [], None
        while True:
            page = mcp_server.call(self.DATA, "search_issues", {"customer_id": "C1", "cursor": cursor})
            self.assertNotIn("priority", page["issues"][0])
            seen += [i["id"] for i in page["issues"]]
            cursor = page["next_cursor"]
            if cursor is None:
                break
        self.assertEqual(len(seen), 12)
        self.assertEqual(len(mcp_server.call(self.DATA, "search_issues", {"customer_id": "C1", "status": "open"})["issues"]), 5)
        self.assertEqual(mcp_server.call(self.DATA, "search_issues", {"customer_id": "nobody"}), {"issues": [], "next_cursor": None})

    def test_protocol(self):
        self.assertEqual(mcp_server.handle(self.DATA, {"method": "tools/call", "params": {"name": "get_issue", "arguments": {"id": "I3"}}})["isError"], False)
        self.assertTrue(mcp_server.handle(self.DATA, {"method": "tools/call", "params": {"name": "get_issue", "arguments": {"id": "zz"}}})["isError"])
        self.assertEqual(len(mcp_server.handle(self.DATA, {"method": "tools/list"})["tools"]), 3)
        with self.assertRaises(LookupError):
            mcp_server.handle(self.DATA, {"method": "resources/list"})


class FixtureTests(unittest.TestCase):
    def test_every_fixture_fails_unsolved_and_passes_solved(self):
        self.assertTrue(cli.selftest())


if __name__ == "__main__":
    unittest.main()
