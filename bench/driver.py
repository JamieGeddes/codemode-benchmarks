"""Drive one interactive Claude Code session inside tmux and wait for it to finish.

Code Mode only runs in an interactive terminal session, so both arms are driven the same way:
a detached tmux session on a private socket, the prompt passed on the command line, and a Stop
hook that writes a marker file when Claude finishes its turn.
"""
import json
import re
import shlex
import subprocess
import time
import uuid
from pathlib import Path

SOCKET = "codemode-bench"  # private tmux server; never touches the user's own tmux sessions
TRUST_OPTION = "Yes, I trust this folder"
CODE_MODE_OPTION = "Yes, turn on Code Mode"
CODE_MODE_BANNER = "Code Mode (experimental) is on"
EXIT_MARKER = "__BENCH_EXIT__="
LIMIT_RE = re.compile(r"usage limit|limit reached|hit your limit|rate limit", re.I)
ALLOWED_TOOLS = ["Bash", "Read", "Edit", "Write", "Glob", "Grep", "NotebookEdit", "TodoWrite", "Agent", "Task",
                 "ToolSearch", "TaskStop", "REPL", "Poll", "mcp__bench"]


class UsageLimit(RuntimeError):
    """The account appears to be rate or usage limited; the whole benchmark should pause."""


def tmux(*args):
    return subprocess.run(["tmux", "-L", SOCKET, *args], capture_output=True, text=True)


def screen(name):
    return tmux("capture-pane", "-t", name, "-p").stdout


def alive(name):
    return tmux("has-session", "-t", name).returncode == 0


def choose(name, option, attempts=8, settle_s=0.3):
    """Move the ❯ cursor of an on-screen menu to `option` and confirm. Returns True once confirmed.

    The screen is re-read after every key press and Enter is only sent once the cursor is seen on
    `option`. A key sent while the menu is still being drawn can be dropped, and confirming blind
    would then pick whatever the menu defaults to. If the cursor never gets there, nothing is
    confirmed and the caller tries again on a later poll.
    """
    for _ in range(attempts):
        lines = [ln.strip() for ln in screen(name).splitlines()]
        target = next((i for i, ln in enumerate(lines) if option in ln), None)
        cursors = [i for i, ln in enumerate(lines) if ln.startswith("❯") and abs(i - target) <= 4] if target is not None else []
        if cursors:
            steps = target - min(cursors, key=lambda i: abs(i - target))
            if steps == 0:
                tmux("send-keys", "-t", name, "Enter")
                return True
            tmux("send-keys", "-t", name, "Down" if steps > 0 else "Up")
        time.sleep(settle_s)  # let the menu finish drawing or the cursor move
    return False


def prepare(run_dir, workspace, prompt, arm, model, mcp_servers, permission_mode="dontAsk", effort=None):
    """Write the per-run prompt, settings, MCP config and launch script. Returns the session id."""
    run_dir = Path(run_dir)
    session_id = str(uuid.uuid4())
    stop_file = run_dir / "stop.json"
    (run_dir / "prompt.txt").write_text(prompt)
    settings = {
        "hooks": {"Stop": [{"hooks": [{"type": "command", "command": f"cat > {shlex.quote(str(stop_file))}"}]}]},
        "permissions": {"allow": ALLOWED_TOOLS},
    }
    (run_dir / "settings.json").write_text(json.dumps(settings, indent=2))
    (run_dir / "mcp.json").write_text(json.dumps({"mcpServers": mcp_servers}, indent=2))
    args = ["claude", "--model", model, "--session-id", session_id, "--permission-mode", permission_mode,
            "--setting-sources", "project,local",  # ignore the user's own settings, CLAUDE.md, plugins and hooks
            "--settings", str(run_dir / "settings.json"),
            "--strict-mcp-config", "--mcp-config", str(run_dir / "mcp.json")]
    if effort:
        args += ["--effort", effort]
    script = "\n".join([
        "#!/bin/sh",
        f"cd {shlex.quote(str(workspace))} || exit 97",
        f"export CLAUDE_CODE_EXPERIMENTAL_CODE_MODE={'1' if arm == 'codemode' else '0'}",
        f"exec {' '.join(shlex.quote(a) for a in args)} -- \"$(cat {shlex.quote(str(run_dir / 'prompt.txt'))})\"",
        "",
    ])
    (run_dir / "launch.sh").write_text(script)
    return session_id


def run_session(run_dir, arm, timeout_s, accept_code_mode=True, log=lambda msg: None):
    """Launch the prepared session and block until it stops. Returns a dict describing what happened."""
    run_dir = Path(run_dir)
    stop_file = run_dir / "stop.json"
    stop_file.unlink(missing_ok=True)
    name = "b" + uuid.uuid4().hex[:10]
    command = f"sh {shlex.quote(str(run_dir / 'launch.sh'))}; echo; echo {EXIT_MARKER}$?; sleep 3600"
    started = tmux("new-session", "-d", "-s", name, "-x", "200", "-y", "50", command)
    if started.returncode != 0:
        return {"status": "launch_failed", "detail": started.stderr.strip(), "banner_seen": False, "wall_s": 0.0}

    t0 = time.time()
    status, detail, stop, banner, last_key, last_text, last_change, wall = "timeout", "", None, False, 0.0, "", t0, None
    try:
        while time.time() - t0 < timeout_s:
            time.sleep(1)
            text = screen(name)
            now = time.time()
            if text != last_text:
                last_text, last_change = text, now
            banner = banner or CODE_MODE_BANNER in text
            if EXIT_MARKER in text:
                status, detail = "exited_early", text.strip()[-800:]
                break
            if now - last_key > 3:
                if TRUST_OPTION in text:
                    if not choose(name, TRUST_OPTION):
                        log("could not select the trust option yet, retrying")
                    last_key = now
                    continue
                if CODE_MODE_OPTION in text:
                    if arm != "codemode" or not accept_code_mode:
                        status, detail = "code_mode_prompt", "Code Mode opt-in screen appeared"
                        break
                    log("accepting the Code Mode opt-in screen")
                    if not choose(name, CODE_MODE_OPTION):
                        log("could not select the Code Mode option yet, retrying")
                    last_key = now
                    continue
            if stop_file.exists():
                try:
                    stop = json.loads(stop_file.read_text())
                except ValueError:
                    continue  # hook is still writing
                if stop.get("background_tasks"):
                    stop_file.unlink(missing_ok=True)  # Claude will be woken when they finish; wait for the next stop
                    continue
                status = "completed"
                break
            if now - last_change > 90 and LIMIT_RE.search(text):
                raise UsageLimit(text.strip()[-600:])
        wall = time.time() - t0
        (run_dir / "screen.txt").write_text(screen(name))
        # Leave gracefully so Claude Code writes its session cost record to the transcript.
        if status == "timeout":
            tmux("send-keys", "-t", name, "Escape")
            time.sleep(2)
        if alive(name) and EXIT_MARKER not in screen(name):
            tmux("send-keys", "-t", name, "Escape")
            time.sleep(0.5)
            tmux("send-keys", "-t", name, "-l", "/exit")
            time.sleep(1)
            tmux("send-keys", "-t", name, "Enter")
            for _ in range(30):
                if EXIT_MARKER in screen(name):
                    break
                time.sleep(0.5)
    finally:
        tmux("kill-session", "-t", name)
    return {"status": status, "detail": detail, "banner_seen": banner, "wall_s": round(wall if wall is not None else time.time() - t0, 2),
            "stop": stop}
