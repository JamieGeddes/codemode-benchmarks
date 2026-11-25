"""Shared helpers for scenario fixtures. Standard library only."""
import json
import subprocess
from pathlib import Path


def write(root, rel, text):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run(cmd, cwd, timeout=300):
    """Run a command, returning (exit_code, combined_output)."""
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s: {cmd}"
    return proc.returncode, proc.stdout + proc.stderr


def node_test(ws, files):
    """Run the given test files with Node's built-in runner."""
    return run(["node", "--test", *[str(f) for f in files]], ws)


def pkg(ws, name, scripts=None):
    body = {"name": name, "version": "1.0.0", "private": True, "scripts": scripts or {"test": "node --test"}}
    write(ws, "package.json", json.dumps(body, indent=2) + "\n")


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def result(passed, detail="", score=None):
    return {
        "passed": bool(passed),
        "score": float(bool(passed)) if score is None else round(float(score), 4),
        "detail": str(detail)[-1500:],
    }
