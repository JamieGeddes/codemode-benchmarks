# Code Mode benchmarks

Measures how Claude Code behaves on typical developer tasks with and without
[Code Mode](https://code.claude.com/docs/en/code-mode): tokens, cost, API round trips, wall time and
whether the task was actually completed.

## How it runs

Code Mode only works in an interactive terminal session (`claude -p` does not offer it), so a script
drives real interactive sessions for **both** arms through tmux:

1. Generate a fresh, deterministic fixture workspace and commit it to a throwaway git repository.
2. Start `claude` in a detached tmux session (private socket `codemode-bench`) with the scenario prompt.
   The only difference between arms is `CLAUDE_CODE_EXPERIMENTAL_CODE_MODE=0` or `=1`.
3. A `Stop` hook writes a marker file when Claude finishes; the runner then sends `/exit` so Claude Code
   writes its session cost record.
4. Copy the session transcript, parse usage from it, and run the scenario's verifier on the workspace.

Standard library Python only; no third-party packages.

## Requirements

- Claude Code 2.1.323 or later (native build), logged in, with Code Mode available to your account
- tmux, Node.js 22+, Python 3.10+, git
- macOS or Linux

## Usage

```sh
python3 -m bench list                      # scenarios
python3 -m bench selftest                  # check fixtures and verifiers, no API usage
python3 -m unittest discover -s tests -t . # harness tests, no API usage

# Cheap trial: 2 scenarios, 1 repeat, 1 model
python3 -m bench run --scenarios single_bugfix,multi_source --models claude-haiku-5-5 --repeats 1

# Full suite (default: Sonnet 5.5 and Opus 5.5, 5 repeats = 200 sessions)
python3 -m bench run --max-cost-usd 150

python3 -m bench run --resume results/<run-id>   # continue after an interruption or usage limit
python3 -m bench report results/<run-id>         # rebuild the report
```

Useful flags: `--jobs N` (parallel sessions; keep at 1 if you care about wall time), `--effort`,
`--timeout`, `--keep-workspaces`, `--seed`, `--no-accept-code-mode`.

## Scenarios

Hypotheses were written before any run, so the suite includes cases where Code Mode is expected to
help, cases where it should make no difference, and controls where its overhead may show.

| Id | Task | Expectation for Code Mode |
|---|---|---|
| `test_triage` | Run a 1,200-test suite, fix 4 root-cause bugs | May help (filter test output) |
| `bulk_migration` | Migrate a deprecated signature across 48 files | May help (repeated edit) |
| `codegen_feature` | Implement one module from a spec | Neutral |
| `codegen_scaffold` | Create 22 files from a schema and one example | Unclear |
| `log_analysis` | Answer 6 questions over 84,000 log lines | Unclear |
| `multi_source` | Join SQLite, CSV and two MCP APIs (about 50 MCP calls) | Should help |
| `dependency_audit` | Find undeclared and unused dependencies in 60 packages | May help (filter search results) |
| `single_bugfix` | Fix one described bug (control) | Neutral or slightly worse |
| `config_lookup` | Answer a question from a few files (control) | Neutral |
| `layered_debug` | Fix a build with 4 chained failures | Neutral (steps cannot be batched) |

Each scenario is one file in `scenarios/` with `PROMPT`, `setup()`, `verify()` and a reference
`solve()` used by the self-test.

## Fairness

- Identical prompt, fixture, model, permission mode, settings and harness for both arms. Prompts
  describe the goal only and never suggest a method.
- Sessions ignore your personal configuration (`--setting-sources project,local`,
  `--strict-mcp-config`), so your CLAUDE.md, plugins, hooks and MCP servers cannot skew either arm.
- Run order is randomised per repeat, and the two arms of a scenario run back to back in random order,
  so prompt-cache state and time-of-day drift affect both alike.
- Every run is verified automatically; a cheaper run that fails the task is reported as a failure.
- Each record is checked to confirm the session really ran in the intended mode. Harness faults are
  marked invalid, excluded from medians and listed in the report.
- The report shows medians, and marks a difference with `~` when the two arms' min-max ranges overlap.

## What is captured

`results/<run-id>/`:

- `manifest.json`: configuration, tool versions, price table, run order
- `results.jsonl`: one record per session with input, output, cache-read and cache-write tokens (5-minute
  and 1-hour), cost of each category, total cost, API requests, tool calls by name, code runs, peak
  context size, wall, API and tool time, verification verdict, prompt and final message
- `summary.csv`: median, min and max per model, scenario and arm
- `report.md`: comparison tables, totals per arm and the total cost of the run
- `runs/<run>/`: prompt, launch script, settings, full transcript, final screen, `changes.patch`, verdict

Token and cost totals come from the cost record Claude Code writes to the transcript. The per-category
cost split uses `bench/pricing.json` (list prices) and is cross-checked against that total.

## Things to know

- Costs are list prices. On a subscription plan nothing is billed per token, but sessions count
  towards your usage limits; the runner stops when it detects a limit and can be resumed.
- Sessions run unattended with `--permission-mode dontAsk` and an allow list (Bash, file tools, the
  benchmark MCP server) inside throwaway workspaces under `~/.cache/codemode-bench`. Anything else is
  denied rather than prompted.
- The runner accepts the folder-trust prompt for the workspaces it creates and, by default, the Code
  Mode opt-in screen if it appears.
- Claude Code keeps its own copy of each session under `~/.claude/projects/`; the runner does not
  delete those.
- Code Mode is experimental and may change; re-check `bench/driver.py` screen markers after upgrades.
