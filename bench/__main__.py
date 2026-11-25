"""Code Mode benchmark runner.

    python3 -m bench list
    python3 -m bench selftest
    python3 -m bench run [--scenarios a,b] [--models m1,m2] [--repeats 5]
    python3 -m bench run --resume results/<run-id>
    python3 -m bench report results/<run-id>
"""
import argparse
import datetime as dt
import json
import random
import shutil
import subprocess
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import scenarios  # noqa: E402
from bench import driver, report, transcript  # noqa: E402

DEFAULT_MODELS = "claude-sonnet-5-5,claude-opus-5-5"
ARMS = ("baseline", "codemode")
GIT = ["git", "-c", "user.name=bench", "-c", "user.email=bench@example.invalid", "-c", "commit.gpgsign=false"]


def _version(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def selftest(names=None):
    """Check every fixture: verification must fail before the reference solution and pass after it."""
    ok = True
    for sid, mod in scenarios.load_all().items():
        if names and sid not in names:
            continue
        with tempfile.TemporaryDirectory() as tmp:
            ws, truth = Path(tmp) / "ws", Path(tmp) / "truth"
            ws.mkdir()
            truth.mkdir()
            mod.setup(ws, truth)
            before = mod.verify(ws, truth)
            mod.setup(ws, truth)  # verify may restore pristine files; start again from a clean fixture
            mod.solve(ws, truth)
            after = mod.verify(ws, truth)
            files = sum(1 for p in ws.rglob("*") if p.is_file())
        good = (not before["passed"]) and after["passed"]
        ok = ok and good
        print(f"{'ok  ' if good else 'FAIL'} {sid:<18} files={files:<4} unsolved passed={before['passed']} solved passed={after['passed']}")
        if not good:
            print("     before:", before["detail"][-300:], "\n     after:", after["detail"][-300:])
    return ok


def build_plan(scenario_ids, models, repeats, arms, seed):
    """Randomised, blocked order: within each repeat the scenario/model pairs are shuffled and the
    arms of a pair run back to back in random order, so drift over time affects both arms alike."""
    plan = []
    for rep in range(1, repeats + 1):
        rng = random.Random(seed * 1000 + rep)
        pairs = [(s, m) for s in scenario_ids for m in models]
        rng.shuffle(pairs)
        for scenario, model in pairs:
            order = list(arms)
            rng.shuffle(order)
            for arm in order:
                plan.append({"run_key": f"{scenario}__{model}__{arm}__r{rep}", "scenario": scenario, "model": model,
                             "arm": arm, "repeat": rep})
    return plan


def _copy_transcripts(stop, session_id, run_dir):
    main = Path(stop["transcript_path"]) if stop and stop.get("transcript_path") else None
    if main is None or not main.exists():
        found = list((Path.home() / ".claude" / "projects").glob(f"*/{session_id}.jsonl"))
        main = found[0] if found else None
    if main is None:
        return []
    paths = [run_dir / "transcript.jsonl"]
    shutil.copy(main, paths[0])
    side = main.with_suffix("")  # subagent transcripts live in a directory named after the session
    if side.is_dir():
        for n, sub in enumerate(sorted(side.rglob("*.jsonl"))):
            dest = run_dir / "subagents" / f"{n:02d}-{sub.name}"
            dest.parent.mkdir(exist_ok=True)
            shutil.copy(sub, dest)
            paths.append(dest)
    return paths


def execute(task, cfg, mods, log):
    mod = mods[task["scenario"]]
    run_dir = cfg["out"] / "runs" / task["run_key"]
    ws = cfg["workdir"] / cfg["run_id"] / task["run_key"]
    truth = run_dir / "truth"
    for path in (run_dir, ws):
        shutil.rmtree(path, ignore_errors=True)
    truth.mkdir(parents=True)
    ws.mkdir(parents=True)
    mod.setup(ws, truth)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=ws, check=True)
    subprocess.run([*GIT, "add", "-A"], cwd=ws, check=True)
    subprocess.run([*GIT, "commit", "-q", "-m", "Fixture"], cwd=ws, check=True)

    servers = {}
    if mod.META.get("mcp"):
        servers["bench"] = {"command": sys.executable, "args": [str(ROOT / "bench" / "mcp_server.py"), str(truth / "mcp_data.json")]}
    session_id = driver.prepare(run_dir, ws, mod.PROMPT, task["arm"], task["model"], servers,
                                permission_mode=cfg["permission_mode"], effort=cfg["effort"])
    started = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    outcome = driver.run_session(run_dir, task["arm"], cfg["timeout"] or mod.META["timeout_s"],
                                 accept_code_mode=cfg["accept_code_mode"], log=log)

    paths = _copy_transcripts(outcome.get("stop"), session_id, run_dir)
    summary = transcript.parse_session(paths, cfg["pricing"])
    subprocess.run([*GIT, "add", "-A"], cwd=ws)
    diff = subprocess.run([*GIT, "diff", "--cached"], cwd=ws, capture_output=True, text=True, errors="replace").stdout
    (run_dir / "changes.patch").write_text(diff[:2_000_000])
    try:
        verdict = mod.verify(ws, truth)
    except Exception as err:  # a verifier crash is a failed run, never a crashed benchmark
        verdict = {"passed": False, "score": 0.0, "detail": f"verifier error: {err!r}"}

    arm_ok, arm_reason = transcript.arm_check(task["arm"], summary, outcome["banner_seen"])
    reason = ""
    if outcome["status"] not in ("completed", "timeout"):
        reason = f"session {outcome['status']}: {outcome.get('detail', '')[-300:]}"
    elif summary["requests"] == 0:
        reason = "no API requests found in the transcript"
    elif not arm_ok:
        reason = arm_reason
    stop = outcome.get("stop") or {}
    record = {
        **task, "run_id": cfg["run_id"], "category": mod.META["category"], "session_id": session_id, "started_at": started,
        "status": outcome["status"], "valid": not reason, "invalid_reason": reason,
        "passed": bool(verdict["passed"]) and outcome["status"] == "completed", "score": verdict["score"],
        "verify_detail": verdict["detail"], "wall_s": outcome["wall_s"], "permission_mode": stop.get("permission_mode"),
        "prompt": mod.PROMPT, "final_message": stop.get("last_assistant_message"), **summary,
    }
    (run_dir / "verify.json").write_text(json.dumps(verdict, indent=2))
    (run_dir / "record.json").write_text(json.dumps(record, indent=2))
    if not cfg["keep_workspaces"]:
        shutil.rmtree(ws, ignore_errors=True)
    return record


def cmd_run(args):
    mods = scenarios.load_all()
    if args.resume:
        out = Path(args.resume).resolve()
        manifest = json.loads((out / "manifest.json").read_text())
        plan = manifest["plan"]
    else:
        ids = args.scenarios.split(",") if args.scenarios else list(mods)
        unknown = [s for s in ids if s not in mods]
        if unknown:
            sys.exit(f"unknown scenario(s): {unknown}; see `python3 -m bench list`")
        run_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        out = Path(args.out).resolve() if args.out else ROOT / "results" / run_id
        out.mkdir(parents=True, exist_ok=True)
        manifest = {
            "run_id": run_id, "started_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "scenarios": ids, "models": args.models.split(","), "arms": args.arms.split(","), "repeats": args.repeats,
            "seed": args.seed, "permission_mode": args.permission_mode, "effort": args.effort, "timeout_override_s": args.timeout,
            "claude_version": _version(["claude", "--version"]), "tmux_version": _version(["tmux", "-V"]),
            "node_version": _version(["node", "--version"]), "python_version": sys.version.split()[0], "platform": sys.platform,
            "suite_commit": _version(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
            "pricing": json.loads(transcript.PRICING_FILE.read_text()),
        }
        manifest["plan"] = build_plan(ids, manifest["models"], args.repeats, manifest["arms"], args.seed)
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
        plan = manifest["plan"]
    cfg = {
        "out": out, "run_id": manifest["run_id"], "workdir": Path(args.workdir).expanduser().resolve(),
        "permission_mode": manifest["permission_mode"], "effort": manifest["effort"], "timeout": manifest.get("timeout_override_s"),
        "accept_code_mode": not args.no_accept_code_mode, "keep_workspaces": args.keep_workspaces,
        "pricing": manifest["pricing"]["models"],
    }
    done = {r["run_key"] for r in report.load(out)}
    todo = [t for t in plan if t["run_key"] not in done]
    spent = sum(r.get("cost_usd") or 0 for r in report.load(out))
    print(f"results: {out}\n{len(todo)} session(s) to run, {len(done)} already recorded")
    lock, halt = threading.Lock(), threading.Event()

    def work(task):
        nonlocal spent
        if halt.is_set():
            return
        try:
            rec = execute(task, cfg, mods, lambda msg: print(f"  [{task['run_key']}] {msg}"))
        except driver.UsageLimit as err:
            halt.set()
            print(f"usage limit detected, stopping; continue later with --resume {out}\n{err}")
            return
        with lock:
            with open(out / "results.jsonl", "a") as fh:
                fh.write(json.dumps(rec) + "\n")
            spent += rec.get("cost_usd") or 0
            flag = "pass" if rec["passed"] else "FAIL"
            if not rec["valid"]:
                flag = f"INVALID ({rec['invalid_reason'][:80]})"
            print(f"{rec['run_key']:<62} {flag:<5} ${rec.get('cost_usd') or 0:.4f} tok={rec['tokens']['total']:>9,} "
                  f"req={rec['requests']:>3} {rec['wall_s']:.0f}s  total ${spent:.2f}", flush=True)
            if args.max_cost_usd and spent >= args.max_cost_usd and not halt.is_set():
                halt.set()
                print(f"budget of ${args.max_cost_usd:.2f} reached, stopping; continue with --resume {out}")

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        list(pool.map(work, todo))
    path = report.render(out, report.load(out), manifest, {sid: m.META for sid, m in mods.items()})
    print(f"report: {path}")


def cmd_report(args):
    out = Path(args.results_dir).resolve()
    manifest = json.loads((out / "manifest.json").read_text()) if (out / "manifest.json").exists() else None
    path = report.render(out, report.load(out), manifest, {sid: m.META for sid, m in scenarios.load_all().items()})
    print(path.read_text())


def main():
    parser = argparse.ArgumentParser(prog="python3 -m bench", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list scenarios")
    st = sub.add_parser("selftest", help="check fixtures and verifiers locally (no API usage)")
    st.add_argument("--scenarios")
    run = sub.add_parser("run", help="run the benchmark")
    run.add_argument("--scenarios", help="comma-separated scenario ids (default: all)")
    run.add_argument("--models", default=DEFAULT_MODELS)
    run.add_argument("--arms", default=",".join(ARMS))
    run.add_argument("--repeats", type=int, default=5)
    run.add_argument("--seed", type=int, default=1, help="seed for the run order")
    run.add_argument("--out", help="results directory (default: results/<timestamp>)")
    run.add_argument("--resume", metavar="DIR", help="continue an interrupted run")
    run.add_argument("--workdir", default="~/.cache/codemode-bench", help="where throwaway workspaces are created")
    run.add_argument("--permission-mode", default="dontAsk")
    run.add_argument("--effort", help="reasoning effort for both arms (default: Claude Code's default)")
    run.add_argument("--timeout", type=int, help="override every scenario's timeout, in seconds")
    run.add_argument("--jobs", type=int, default=1, help="sessions to run in parallel")
    run.add_argument("--max-cost-usd", type=float, help="stop starting new sessions once this much has been spent")
    run.add_argument("--keep-workspaces", action="store_true")
    run.add_argument("--no-accept-code-mode", action="store_true", help="fail instead of accepting the Code Mode opt-in screen")
    rep = sub.add_parser("report", help="rebuild report.md and summary.csv")
    rep.add_argument("results_dir")
    args = parser.parse_args()
    if args.cmd == "list":
        for sid, mod in scenarios.load_all().items():
            print(f"{sid:<18} {mod.META['category']:<22} {mod.META['title']}")
    elif args.cmd == "selftest":
        sys.exit(0 if selftest(args.scenarios.split(",") if args.scenarios else None) else 1)
    elif args.cmd == "run":
        cmd_run(args)
    else:
        cmd_report(args)


if __name__ == "__main__":
    main()
