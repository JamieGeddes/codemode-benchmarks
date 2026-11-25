"""The "repo" tier: tasks taken from the history of real open-source projects.

Each task names an upstream commit (`fix`) and the commit whose tree the session works in (`pin`,
which already contains the fix). The fixture is the pinned tree with the fix reverse-applied, so the
code, the tests the fix added and its changelog entry are all gone. Verification restores the
pinned test files and runs them; the reference solution re-applies the upstream change.

Unlike the micro tier this needs the network once per repository: a bare clone and a dependency
install, both cached under ~/.cache/codemode-bench/repos (override with CODEMODE_BENCH_CACHE).
"""
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

from ._util import result

CACHE = Path(os.environ.get("CODEMODE_BENCH_CACHE", "~/.cache/codemode-bench")).expanduser() / "repos"
_LOCK = threading.Lock()

# Licences were checked when each repository was added; all are permissive. Nothing from these
# projects is stored in this repository: they are cloned on the user's machine at the pinned commit.
REPOS = {
    "hono": {
        "url": "https://github.com/honojs/hono", "licence": "MIT", "kind": "node",
        "pin": "9c2f2948498434506f9ebc77a213bf67a2da5603",
        "install": ["pnpm", "install", "--frozen-lockfile"],
        "test": ["pnpm", "exec", "vitest", "run", "--project", "main", "--coverage.enabled=false"],
        "test_re": r"\.test\.tsx?$",
        "needs": ["pnpm"],
        "env_note": "Dependencies are already installed with pnpm.",
    },
    "fastify": {
        "url": "https://github.com/fastify/fastify", "licence": "MIT", "kind": "node",
        "pin": "f5757f12298e95210a3e35d81559961b284ad6f1",
        # No lockfile upstream, so dependency versions are resolved as of the pinned commit's date.
        "install": ["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund", "--before", "2026-11-25T00:00:00Z"],
        "test": ["node", "--test"],
        "test_re": r"^test/",
        "needs": ["npm"],
        "env_note": "Dependencies are already installed with npm.",
    },
    "click": {
        "url": "https://github.com/pallets/click", "licence": "BSD-3-Clause", "kind": "python",
        "test_deps": ["pytest"],
        "test_re": r"^tests/",
        "env_note": "A virtual environment with the project and its test dependencies installed is in .venv.",
    },
    "flask": {
        "url": "https://github.com/pallets/flask", "licence": "BSD-3-Clause", "kind": "python",
        "test_deps": ["pytest", "asgiref", "greenlet", "python-dotenv"],
        "test_re": r"^tests/",
        "env_note": "A virtual environment with the project and its test dependencies installed is in .venv.",
    },
}
PY_TEST = [".venv/bin/python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
GIT_EXCLUDE = ".venv/\nnode_modules/\n"


class SetupError(RuntimeError):
    """The repository could not be cloned or its dependencies installed."""


def _sh(cmd, cwd=None, data=None, timeout=1800, check=True, env=None):
    proc = subprocess.run(cmd, cwd=cwd, input=data, capture_output=True, timeout=timeout,
                          env={**os.environ, **(env or {})})
    if check and proc.returncode != 0:
        tail = (proc.stdout + proc.stderr).decode(errors="replace")[-1500:]
        raise SetupError(f"{' '.join(map(str, cmd))} failed in {cwd}:\n{tail}")
    return proc


def _mirror(name, commits):
    """Bare clone of the upstream repository holding every commit a task needs."""
    path = CACHE / f"{name}.git"
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        tmp = CACHE / f"{name}.git.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        _sh(["git", "clone", "-q", "--bare", REPOS[name]["url"], str(tmp)])
        tmp.rename(path)
    if any(_sh(["git", "-C", str(path), "cat-file", "-e", f"{c}^{{commit}}"], check=False).returncode for c in commits):
        _sh(["git", "-C", str(path), "fetch", "-q", "origin", "+refs/heads/*:refs/heads/*"])
    return path


def _git(name, *args):
    return _sh(["git", "-C", str(CACHE / f"{name}.git"), *args]).stdout


def _prepared(name, pin):
    """Cached checkout of `pin` with dependencies installed (node) or downloaded as wheels (python)."""
    repo = REPOS[name]
    for tool in repo.get("needs", []):
        if not shutil.which(tool):
            raise SetupError(f"{tool} is required for the {name} scenarios but is not on PATH")
    base = CACHE / name / pin[:12]
    tree, ready = base / "tree", base / "ready"
    if ready.exists():
        return base
    shutil.rmtree(base, ignore_errors=True)
    tree.mkdir(parents=True)
    archive = _git(name, "archive", pin)
    _sh(["tar", "-x", "-C", str(tree)], data=archive)
    if repo["kind"] == "node":
        _sh(repo["install"], cwd=tree)
    else:
        if sys.version_info < (3, 10):
            raise SetupError(f"the {name} scenarios need Python 3.10 or later")
        # Build the project once so its runtime and build requirements land in the wheel directory,
        # then every workspace can create its own virtual environment without the network.
        # Dependencies are resolved as they stood a day after the pinned commit (pip 26 or later),
        # so an old commit is not paired with releases it was never tested against.
        day = _git(name, "show", "-s", "--format=%cd", "--date=format:%Y-%m-%d", pin).decode().strip()
        cutoff = (dt.date.fromisoformat(day) + dt.timedelta(days=2)).isoformat() + "T00:00:00Z"
        wheel = [sys.executable, "-m", "pip", "wheel", "-q", "--disable-pip-version-check", "-w", str(base / "wheels"),
                 str(tree), "flit_core>=3.11,<4", *repo["test_deps"]]
        dated = _sh([*wheel, "--uploaded-prior-to", cutoff], check=False)
        if dated.returncode != 0:
            if b"no such option" not in dated.stderr:
                raise SetupError(f"pip wheel failed for {name}:\n{dated.stderr.decode(errors='replace')[-1500:]}")
            shutil.rmtree(base / "wheels", ignore_errors=True)
            _sh(wheel)  # older pip: latest releases
    ready.write_text(pin + "\n")
    return base


def _copy_tree(src, dst):
    """Copy the contents of src into the empty directory dst, using copy-on-write where available."""
    for flags in (["-Rc"] if sys.platform == "darwin" else ["-a", "--reflink=auto"], ["-R"]):
        if subprocess.run(["cp", *flags, f"{src}/.", str(dst)], capture_output=True).returncode == 0:
            return
    shutil.copytree(src, dst, symlinks=True, dirs_exist_ok=True)


def _apply(ws, patch, reverse):
    # GIT_CEILING_DIRECTORIES stops git treating the workspace as part of an enclosing repository.
    cmd = ["git", "apply", "--whitespace=nowarn", *(["-R"] if reverse else []), "-"]
    _sh(cmd, cwd=ws, data=patch, env={"GIT_CEILING_DIRECTORIES": str(Path(ws).resolve().parent)})


def _venv(ws, wheels, test_deps):
    _sh([sys.executable, "-m", "venv", ".venv"], cwd=ws)
    _sh([".venv/bin/python", "-m", "pip", "install", "-q", "--disable-pip-version-check", "--no-index",
         "--find-links", str(wheels), "-e", ".", *test_deps], cwd=ws)


def task(*, id, title, repo, fix, prompt, category, hypothesis, run, pin=None, select=None, timeout_s=1500):
    """Build META, PROMPT, setup, solve and verify for one commit-derived task.

    fix     upstream commit that made the change (its first-parent diff is what gets removed)
    pin     commit the workspace is based on; defaults to the repository pin, or to `fix` itself
    run     test files to run for verification, as of `pin`
    select  optional extra arguments for the test runner (for example ["-k", "expr"] for pytest)
    """
    spec = REPOS[repo]
    pin = pin or spec.get("pin") or fix
    test_re = re.compile(spec["test_re"])
    meta = {"id": id, "title": title, "category": category, "hypothesis": hypothesis, "timeout_s": timeout_s,
            "tier": "repo", "repo": f"{spec['url']} @ {pin[:10]} ({spec['licence']}), fix {fix[:10]}",
            "git_exclude": GIT_EXCLUDE}

    def patch():
        return _git(repo, "diff", "--binary", f"{fix}^", fix)

    def setup(ws, truth):
        ws = Path(ws)
        with _LOCK:
            _mirror(repo, [pin, fix])
            base = _prepared(repo, pin)
        for child in ws.iterdir():  # the self-test sets a workspace up twice
            shutil.rmtree(child) if child.is_dir() and not child.is_symlink() else child.unlink()
        _copy_tree(base / "tree", ws)
        for rel in (".claude", ".mcp.json"):  # never run an upstream project's agent settings or servers
            target = ws / rel
            shutil.rmtree(target, ignore_errors=True) if target.is_dir() else target.unlink(missing_ok=True)
        _apply(ws, patch(), reverse=True)
        if spec["kind"] == "python":
            _venv(ws, base / "wheels", spec["test_deps"])

    def solve(ws, truth):
        _apply(ws, patch(), reverse=False)

    def verify(ws, truth):
        ws = Path(ws)
        changed = _git(repo, "diff", "--name-only", f"{fix}^", fix).decode().split()
        for rel in {p for p in changed if test_re.search(p)} | set(run):
            shown = _sh(["git", "-C", str(CACHE / f"{repo}.git"), "show", f"{pin}:{rel}"], check=False)
            if shown.returncode == 0:  # pristine upstream tests, so edited tests cannot mask a failure
                (ws / rel).parent.mkdir(parents=True, exist_ok=True)
                (ws / rel).write_bytes(shown.stdout)
        if spec["kind"] == "python" and not (ws / ".venv/bin/python").exists():
            _venv(ws, CACHE / repo / pin[:12] / "wheels", spec["test_deps"])
        cmd = [*(PY_TEST if spec["kind"] == "python" else spec["test"]), *run, *(select or [])]
        try:
            proc = subprocess.run(cmd, cwd=ws, capture_output=True, text=True, errors="replace", timeout=900)
        except subprocess.TimeoutExpired:
            return result(False, f"verification timed out: {' '.join(cmd)}")
        return result(proc.returncode == 0, proc.stdout + proc.stderr)

    return meta, f"{prompt}\n\n{spec['env_note']}", setup, solve, verify
