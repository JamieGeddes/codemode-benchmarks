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

The harness itself is standard library Python only. The repo-tier scenarios additionally clone four
open-source projects and install their dependencies on your machine (see below).

## Requirements

- Claude Code 2.1.323 or later (native build), logged in, with Code Mode available to your account
- tmux, Node.js 22+, Python 3.10+, git
- For the repo tier: network access on first use, npm, pnpm, and pip 26 or later (older pip works but
  cannot pin Python dependencies by date)
- macOS or Linux

## Usage

```sh
python3 -m bench list                      # scenarios
python3 -m bench selftest                  # check micro fixtures and verifiers, no API usage
python3 -m bench selftest --tier repo      # clone, install and check the repo tier (network, a few minutes)
python3 -m unittest discover -s tests -t . # harness tests, no API usage

# Cheap trial: 2 scenarios, 1 repeat, 1 model
python3 -m bench run --scenarios single_bugfix,multi_source --models claude-haiku-5-5 --repeats 1

# Full suite (default: Sonnet 5.5 and Opus 5.5, 5 repeats, 21 scenarios = 420 sessions)
python3 -m bench run --max-cost-usd 400

python3 -m bench run --tier repo --repeats 3   # only the real-repository scenarios (or --tier micro)

python3 -m bench run --resume results/<run-id>   # continue after an interruption or usage limit; retries invalid sessions
python3 -m bench report results/<run-id>         # rebuild the report
```

Useful flags: `--tier micro|repo|all`, `--jobs N` (parallel sessions; keep at 1 if you care about wall time), `--effort`,
`--timeout`, `--keep-workspaces`, `--seed`, `--no-accept-code-mode`.

## Scenarios

There are two tiers. The **micro** tier is generated, offline and small: each scenario isolates one
tool-call pattern (fan-out, repetition, large output, a strict sequence). It says how Code Mode
behaves on that pattern, not how it behaves on everyday work. The **repo** tier is the representative
one: real changes taken from the history of real projects, where most of the effort is finding the
right code.

Hypotheses were written before any run, so the suite includes cases where Code Mode is expected to
help, cases where it should make no difference, and controls where its overhead may show.

### Micro tier

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

### Repo tier

| Id | Project | Task |
|---|---|---|
| `hono_jsx_async` | Hono | Bug: async JSX components resolving to null, booleans or numbers |
| `hono_method_override` | Hono | Bug: method override to GET or HEAD keeps the request body |
| `hono_router_params` | Hono | Bug: a repeated path parameter changes value when unrelated routes exist |
| `hono_trailing_slash_skip` | Hono | Feature: `skip` option for the trailing-slash middleware |
| `fastify_error_status` | Fastify | Bug: error status codes above 599 are sent as they are |
| `fastify_not_found_hook` | Fastify | Bug: `callNotFound()` skips the not-found preHandler |
| `fastify_close_disposable` | Fastify | Feature: disposable objects as `onClose` hooks |
| `click_help_wrap` | Click | Bug: help text wraps inside hyphenated words |
| `click_no_such_command` | Click | Feature: suggestions for a mistyped command |
| `flask_automatic_options` | Flask | Bug: `provide_automatic_options` cannot be enabled per view |
| `flask_ipv6_host` | Flask | Bug: IPv6 literals in host names |

Expectation for all of them: unclear. They are explore, edit, test loops with little to batch, which
is the point: this is what most sessions look like.

How a repo-tier task is built (`scenarios/_repo.py`):

- Each task names an upstream commit. The workspace is a pinned checkout with that commit
  reverse-applied, so the fix, the tests it added and its changelog entry are gone. There is no git
  history to look the answer up in.
- The prompt is written as an issue report: symptoms and expected behaviour, never file names.
- Verification restores the upstream test files and runs them, so the pass criterion is the one the
  project's maintainers wrote. The reference solution is the upstream change.
- Dependencies are installed once per repository and cached under `~/.cache/codemode-bench/repos`
  (about 1.1 GB; override with `CODEMODE_BENCH_CACHE`). Each run gets a copy-on-write copy.
  Versions are pinned: Hono by its lockfile, Fastify and the Python projects by resolving as of the
  pinned commit's date.

| Project | Licence | Language | Source size | Pin |
|---|---|---|---|---|
| [honojs/hono](https://github.com/honojs/hono) | MIT | TypeScript | 243 files, 29.7k lines | `9c2f2948` |
| [fastify/fastify](https://github.com/fastify/fastify) | MIT | JavaScript | 39 files, 10.3k lines (67k lines of tests) | `f5757f12` |
| [pallets/click](https://github.com/pallets/click) | BSD-3-Clause | Python | 17 files, 12.8k lines | per task |
| [pallets/flask](https://github.com/pallets/flask) | BSD-3-Clause | Python | 24 files, 9.6k lines | per task |

Nothing from these projects is stored in this repository. Their development dependencies (about 1,300
npm packages and a dozen wheels) are installed locally only; nearly all are MIT, ISC, BSD or
Apache-2.0. The exceptions seen at the time of writing are `lightningcss` (MPL-2.0),
`@img/sharp-libvips` (LGPL-3.0-or-later), `node-forge` (BSD-3-Clause OR GPL-2.0) and
`@bytecodealliance/componentize-js` (no licence field in its manifest).

Caveats: these projects are popular, so a model may have seen the upstream fix (the
fixes used here were merged between February and November 2026).
That affects both arms equally, but it makes the tasks easier than unseen code would be. Some tasks
are verified with a subset of the upstream tests where the rest assert internal names that an
equally valid fix would not share.

Each scenario is one file in `scenarios/` with `PROMPT`, `setup()`, `verify()` and a reference
`solve()` used by the self-test.

## Fairness

- Identical prompt, fixture, model, permission mode, settings and harness for both arms. Prompts
  describe the goal only and never suggest a method.
- Sessions ignore your personal settings and hooks (`--setting-sources project,local`) and your
  configured MCP servers (`--strict-mcp-config`).
- Sessions ignore your personal instructions. Claude Code loads `CLAUDE.md` files from every directory
  above the working directory, which for a workspace under your home directory includes
  `~/.claude/CLAUDE.md`. The runner excludes every instruction file above the workspace
  (`claudeMdExcludes`), and marks a session invalid if one is loaded anyway.
- Not isolated: tools that Claude Code or your account adds by itself, such as the Chrome extension
  and connectors, are still offered in both arms.
- Run order is randomised per repeat, and the two arms of a scenario run back to back in random order,
  so prompt-cache state and time-of-day drift affect both alike.
- Every run is verified automatically; a cheaper run that fails the task is reported as a failure.
- Each record is checked to confirm the session really ran in the intended mode. Harness faults are
  marked invalid, excluded from medians, listed in the report and run again by `--resume`.
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
- Repo-tier workspaces run the projects' own test tooling with the same permissions as the session.
  npm install scripts are disabled for Fastify and pnpm does not run dependency build scripts.
- Code Mode is experimental and may change; re-check `bench/driver.py` screen markers after upgrades.
