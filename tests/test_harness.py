"""Harness tests. No API usage: `python3 -m unittest discover -s tests -t .`"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scenarios
from bench import __main__ as cli
from bench import driver, mcp_server, report, transcript
from scenarios import _repo

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


class IsolationTests(unittest.TestCase):
    def test_instruction_files_are_recorded_and_outside_ones_fail_the_check(self):
        with tempfile.TemporaryDirectory() as ws:
            inside, outside = str(Path(ws) / "CLAUDE.md"), str(Path.home() / ".claude" / "CLAUDE.md")
            row = lambda *paths: {"type": "attachment", "attachment": {"type": "instructions", "files": [{"path": p} for p in paths]}}
            clean = transcript.parse_session([write_jsonl([row(inside), {"type": "attachment", "attachment": {"type": "date"}}])], PRICING)
            self.assertEqual(clean["instruction_files"], [inside])
            self.assertEqual(transcript.isolation_check(clean, ws), (True, ""))
            leaked = transcript.parse_session([write_jsonl([row(inside, outside)])], PRICING)
            ok, reason = transcript.isolation_check(leaked, ws)
            self.assertFalse(ok)
            self.assertIn(outside, reason)
            self.assertNotIn(inside, reason)
            self.assertEqual(transcript.isolation_check({}, ws), (True, ""))  # records made before this check existed

    def test_sessions_exclude_every_instruction_file_above_the_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Path.home() / ".cache" / "codemode-bench" / "run" / "task"
            globs = driver.outside_instruction_globs(ws)
            home = Path.home().as_posix()
            for wanted in (f"{home}/.claude/CLAUDE.md", f"{home}/CLAUDE.md", f"{home}/.claude/rules/**",
                           f"{home}/.cache/CLAUDE.md", f"{ws.parent.as_posix()}/CLAUDE.local.md"):
                self.assertIn(wanted, globs)
            self.assertFalse([g for g in globs if g.startswith(ws.as_posix() + "/")])  # a fixture's own files still load
            driver.prepare(tmp, ws, "prompt", "baseline", "m", {})
            settings = json.loads((Path(tmp) / "settings.json").read_text())
            self.assertEqual(settings["claudeMdExcludes"], globs)
            self.assertIn("Stop", settings["hooks"])


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


    def test_resume_retries_invalid_sessions_only(self):
        plan = cli.build_plan(["a"], ["m"], 2, ["baseline", "codemode"], seed=1)
        keys = [t["run_key"] for t in plan]
        records = [{"run_key": keys[0], "valid": True}, {"run_key": keys[1], "valid": False}]
        todo, retries = cli.pending(plan, records)
        self.assertEqual([t["run_key"] for t in todo], keys[1:])  # plan order is kept
        self.assertEqual(retries, 1)
        self.assertEqual(cli.pending(plan, [{"run_key": k, "valid": True} for k in keys]), ([], 0))


class FakeMenu:
    """A two-option menu standing in for tmux: tracks the cursor and what Enter confirmed."""
    OPTIONS = ["No, exit", "Yes, I trust this folder"]

    def __init__(self, dropped_keys=0, blank_reads=0):
        self.cursor, self.dropped, self.blank, self.confirmed = 0, dropped_keys, blank_reads, None

    def screen(self, name):
        if self.blank > 0:  # the menu has not finished drawing
            self.blank -= 1
            return " Accessing workspace:\n"
        return "\n".join(f" {'❯' if i == self.cursor else ' '} {opt}" for i, opt in enumerate(self.OPTIONS)) + "\n"

    def tmux(self, *args):
        key = args[-1]
        if self.dropped > 0:  # the terminal is not reading input yet
            self.dropped -= 1
        elif key == "Enter":
            self.confirmed = self.OPTIONS[self.cursor]
        else:
            self.cursor = max(0, min(len(self.OPTIONS) - 1, self.cursor + (1 if key == "Down" else -1)))


class DriverTests(unittest.TestCase):
    def choose(self, menu, option=driver.TRUST_OPTION):
        with mock.patch.object(driver, "screen", menu.screen), mock.patch.object(driver, "tmux", menu.tmux):
            return driver.choose("session", option, settle_s=0)

    def test_choose_moves_the_cursor_then_confirms(self):
        menu = FakeMenu()
        self.assertTrue(self.choose(menu))
        self.assertEqual(menu.confirmed, driver.TRUST_OPTION)

    def test_choose_survives_a_dropped_key_and_a_half_drawn_menu(self):
        for menu in (FakeMenu(dropped_keys=1), FakeMenu(blank_reads=2), FakeMenu(dropped_keys=2, blank_reads=1)):
            self.assertTrue(self.choose(menu))
            self.assertEqual(menu.confirmed, driver.TRUST_OPTION)

    def test_choose_never_confirms_the_wrong_option(self):
        for menu in (FakeMenu(dropped_keys=99), FakeMenu(blank_reads=99)):
            self.assertFalse(self.choose(menu))
            self.assertIsNone(menu.confirmed)
        menu = FakeMenu()
        self.assertFalse(self.choose(menu, option="Not on screen"))
        self.assertIsNone(menu.confirmed)


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
        self.assertTrue(cli.selftest())  # micro tier only; the repo tier needs the network


class RepoTierTests(unittest.TestCase):
    """Exercise the repo-tier machinery offline against a throwaway local repository."""

    def git(self, *args):
        subprocess.run(["git", "-C", str(self.upstream), "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                        "-c", "commit.gpgsign=false", *args], check=True, capture_output=True)

    def commit(self, files, message):
        for rel, text in files.items():
            path = self.upstream / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return subprocess.run(["git", "-C", str(self.upstream), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()

    def test_fixture_removes_the_fix_and_verify_restores_the_tests(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.upstream = tmp / "upstream"
            self.upstream.mkdir()
            self.git("init", "-q", "-b", "main")
            test = "const test = require('node:test');\nconst assert = require('node:assert');\nconst { add } = require('../lib/add');\n"
            self.commit({"lib/add.js": "exports.add = (a, b) => a - b;\n", "CHANGES.md": "# Changes\n", ".mcp.json": "{}\n",
                         "test/add.test.js": test + "test('loads', () => { assert.ok(add); });\n"}, "Initial")
            fix = self.commit({"lib/add.js": "exports.add = (a, b) => a + b;\n", "CHANGES.md": "# Changes\n- fix add\n",
                               "test/add.test.js": test + "test('adds', () => { assert.strictEqual(add(2, 3), 5); });\n"}, "Fix add")
            pin = self.commit({"lib/other.js": "exports.other = 1;\n"}, "Later work")
            spec = {"url": str(self.upstream), "licence": "MIT", "kind": "node", "pin": pin, "install": ["true"],
                    "test": ["node", "--test"], "test_re": r"^test/", "env_note": "Nothing to install."}
            with mock.patch.dict(_repo.REPOS, {"local": spec}), mock.patch.object(_repo, "CACHE", tmp / "cache"):
                meta, prompt, setup, solve, verify = _repo.task(
                    id="local_fix", title="t", repo="local", fix=fix, category="repo: bug fix", hypothesis="h",
                    run=["test/add.test.js"], prompt="Fix add.")
                ws = tmp / "ws"
                ws.mkdir()
                setup(ws, tmp)
                self.assertEqual((ws / "lib/add.js").read_text(), "exports.add = (a, b) => a - b;\n")
                self.assertNotIn("fix add", (ws / "CHANGES.md").read_text())  # the changelog entry would give it away
                self.assertNotIn("adds", (ws / "test/add.test.js").read_text())  # so would the upstream test
                self.assertTrue((ws / "lib/other.js").exists())  # later upstream work is kept
                self.assertFalse((ws / ".mcp.json").exists())
                self.assertFalse((ws / ".git").exists())
                (ws / "test/add.test.js").write_text("")  # an emptied test file must not make verification pass
                self.assertFalse(verify(ws, tmp)["passed"])
                setup(ws, tmp)  # a second setup starts again from a clean tree
                solve(ws, tmp)
                self.assertTrue(verify(ws, tmp)["passed"])
            self.assertEqual(meta["tier"], "repo")
            self.assertTrue(prompt.endswith("Nothing to install."))

    def test_repo_scenarios_are_well_formed_and_opt_in(self):
        mods = {sid: m for sid, m in scenarios.load_all().items() if cli.tier_of(m) == "repo"}
        self.assertGreaterEqual(len(mods), 10)
        for sid, mod in mods.items():
            self.assertRegex(mod.META["repo"], r"^https://github\.com/\S+ @ [0-9a-f]{10} \((MIT|BSD-3-Clause)\), fix [0-9a-f]{10}$", sid)
            self.assertIn("node_modules/", mod.META["git_exclude"])
            self.assertNotRegex(mod.PROMPT, r"\b(src|lib|tests?)/\S+\.(ts|tsx|js|py)\b", f"{sid}: the prompt should not name files")
        for spec in _repo.REPOS.values():
            self.assertRegex(spec.get("pin", "0" * 40), r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main()
