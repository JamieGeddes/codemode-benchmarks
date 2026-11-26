# Code Mode benchmark analysis

Repo tier, 11 scenarios × 2 arms × 3 repeats per model. Claude Code 2.1.332, permission mode `dontAsk`, default effort. The only difference between arms is `CLAUDE_CODE_EXPERIMENTAL_CODE_MODE`. Δ is Code Mode relative to baseline.

| Run | Model | Started (UTC) | Suite commit | Runs | Data |
|---|---|---|---|---|---|
| `20261125-220716` | `claude-sonnet-5-5` | 2026-11-25 22:07 | `1ed9afd` | 66, all valid | [`results/20261125-220716/`](results/20261125-220716/) |
| `20261126-093537` | `claude-opus-5-5` | 2026-11-26 09:35 | `df93981` | 66, all valid | [`results/20261126-093537/`](results/20261126-093537/) |

- Each data directory holds `report.md`, `summary.csv`, `manifest.json` and `results.jsonl`.
- Earlier pilot runs, 1 repeat on two scenarios: [`results/20261125-210801/`](results/20261125-210801/) (Haiku 5.5) and [`results/20261125-213223/`](results/20261125-213223/) (Sonnet 5.5).
- Per-session transcripts and the cloned test repositories are not committed. The per-request figures in the Explanation section come from the local transcripts under `results/<run-id>/runs/`.
- One Opus session (`flask_ipv6_host` baseline, repeat 3) first failed on a harness fault and was re-run; the figures use the re-run.

## Summary

Code Mode completed every task the baseline did on both models (132 of 132 runs passed) and cost less: 21% less on Sonnet 5.5 and 16% less on Opus 5.5. It always ran with a smaller context.

The saving has two parts. A fixed part, worth about 9% on both models, comes from a smaller prompt that is re-read on every request. A variable part comes from finishing in fewer round trips, and that part is not guaranteed: on Opus, three of the eleven scenarios saved 5% or less, and one cost 6% more.

The runs cannot say anything about quality differences, because every run in both arms passed.

## Findings

### Totals

Sums over all 33 runs per arm, except peak context.

| Metric | Sonnet base | Sonnet code | Δ | Opus base | Opus code | Δ |
|---|---|---|---|---|---|---|
| Passed | 33/33 | 33/33 | none | 33/33 | 33/33 | none |
| Cost | $6.33 | $4.97 | -21% | $19.22 | $16.22 | -16% |
| Cache-read tokens | 16.78M | 8.65M | -48% | 28.25M | 16.00M | -43% |
| Output tokens | 170,728 | 142,423 | -17% | 276,331 | 254,657 | -8% |
| Cache-write tokens | 736,009 | 673,524 | -8% | 1,004,131 | 989,222 | -1% |
| API requests | 365 | 318 | -13% | 535 | 448 | -16% |
| Tool calls (top level) | 378 | 285 | -25% | 613 | 416 | -32% |
| Peak context, per-scenario median | 46k to 60k | 27k to 41k | -32% to -40% | 49k to 74k | 31k to 65k | -10% to -41% |
| Wall time | 2,748 s | 2,222 s | -19% | 4,042 s | 5,065 s | +25% (see below) |

### Cost per scenario

Medians over 3 repeats. A trailing `~` means the two arms' min-max ranges overlap, so the difference is within run-to-run noise.

| Scenario | Category | Sonnet $ base | Sonnet $ code | Δ | Opus $ base | Opus $ code | Δ | Opus requests base | Opus requests code |
|---|---|---|---|---|---|---|---|---|---|
| hono_jsx_async | bug fix | 0.2552 | 0.2021 | -21% | 0.8348 | 0.6663 | -20% | 23 | 18 |
| hono_method_override | bug fix | 0.2041 | 0.1502 | -26% ~ | 0.4065 | 0.3844 | -5% ~ | 10 | 9 |
| hono_router_params | bug fix | 0.2656 | 0.1860 | -30% ~ | 0.8175 | 0.8687 | +6% ~ | 22 | 21 |
| hono_trailing_slash_skip | feature | 0.1558 | 0.1294 | -17% ~ | 0.3210 | 0.3199 | -0% ~ | 9 | 9 |
| fastify_error_status | bug fix | 0.2221 | 0.1771 | -20% ~ | 0.8183 | 0.7277 | -11% ~ | 24 | 22 |
| fastify_not_found_hook | bug fix | 0.1618 | 0.1410 | -13% ~ | 0.6923 | 0.4842 | -30% | 20 | 13 |
| fastify_close_disposable | feature | 0.2262 | 0.1687 | -25% | 0.8116 | 0.7139 | -12% ~ | 22 | 17 |
| click_help_wrap | bug fix | 0.1208 | 0.0923 | -24% | 0.4264 | 0.3278 | -23% ~ | 12 | 11 |
| click_no_such_command | feature | 0.2244 | 0.1749 | -22% ~ | 0.4797 | 0.3887 | -19% ~ | 12 | 10 |
| flask_automatic_options | bug fix | 0.1525 | 0.1113 | -27% | 0.3791 | 0.2695 | -29% | 9 | 6 |
| flask_ipv6_host | bug fix | 0.1330 | 0.1078 | -19% | 0.4371 | 0.3030 | -31% | 16 | 11 |

- **Sonnet:** Code Mode was cheaper on median in all 11 scenarios, by 13% to 30%. The ranges separate cleanly in 5.
- **Opus:** cheaper in 9 scenarios, flat in 1 and dearer in 1, from -31% to +6%. The ranges separate cleanly in 4.
- **Peak context:** lower in all 11 scenarios on both models with no overlap. The gap is a near-constant 17k to 21k tokens on Sonnet. On Opus it is 14k to 23k in ten scenarios and 7k in `hono_router_params`.
- **Correctness:** no difference between arms on either model.
- **Opus does more per task.** It used 16 requests per baseline run against Sonnet's 11, and about three times the money.

Requests, tokens and wall time per scenario are in each run's `report.md`.

### Wall time

Wall time is mostly noise and does not show a reliable effect in either direction.

- **Sonnet:** -19% in total, but only `fastify_close_disposable` separates cleanly. Much of the gap comes from slow test runs in the baseline `hono_router_params` runs.
- **Opus:** +25% in total, caused by two Code Mode runs of `click_help_wrap` (953 s and 518 s against a typical 50 to 80 s). In both, the model chose to run Click's stress tests, a suite of about 15 minutes, and waited for it. No baseline run did this. Without that scenario, Code Mode is 8% faster on Opus (3,840 s to 3,543 s).
- With 3 repeats it is not possible to say whether Code Mode made the stress-test choice more likely.

## Explanation

### 1. A smaller fixed context gives a floor of about 9%

The first request of a session carries about 40.0k tokens in baseline and 21.8k in Code Mode. This was the same in all 132 sessions, to within 0.2k tokens. The gap of roughly 18k tokens is re-read from cache on every later request.

| | Sonnet | Opus |
|---|---|---|
| Fixed context saving, tokens (18.2k × Code Mode requests) | 5.8M | 8.2M |
| Share of the cache-read saving | about 70% | about 67% |
| Value at the cache-read list price | $0.58 | $1.63 |
| Share of baseline cost | 9% | 8.5% |

The likely cause is a single `REPL` tool replacing the full set of tool schemas in the prompt. This is an inference from the token counts; the prompts themselves were not compared.

### 2. Fewer round trips provide the rest, when they happen

Code Mode wraps several tool calls in one `REPL` run, which cut API requests by 13% on Sonnet and 16% on Opus.

On Opus the cost saving tracks the request saving closely:

| Opus scenarios | Requests Δ | Cost Δ |
|---|---|---|
| `flask_ipv6_host`, `flask_automatic_options`, `fastify_not_found_hook` | -31% to -35% | -29% to -31% |
| `hono_method_override`, `hono_router_params`, `hono_trailing_slash_skip` | 0% to -10% | -5% to +6% |

In the second group the session was no shorter, and Code Mode wrote more new context to the cache (up 6% to 25%), which cancelled the fixed saving. `hono_router_params` is the clearest case: cache writes rose 25% and the context gap shrank to 7k tokens.

Sonnet behaved more evenly: `click_no_such_command` and `fastify_close_disposable` showed no drop in requests and still saved 22% and 25%.

### 3. The cost saving is smaller than the token saving

Total tokens fell by 40% to 50%, cost by 16% to 21%, because the tokens saved are the cheapest kind.

| Cost category | Sonnet base $ | Sonnet saving $ | Share of saving | Opus base $ | Opus saving $ | Share of saving |
|---|---|---|---|---|---|---|
| Cache write (1h) | 2.94 | 0.25 | 18% | 8.03 | 0.12 | 4% |
| Output | 1.70 | 0.30 | 22% | 5.51 | 0.43 | 14% |
| Cache read | 1.68 | 0.81 | 60% | 5.65 | 2.45 | 82% |
| **Total** | **6.33** | **1.36** | | **19.22** | **3.00** | |

Cache writes are 42% to 47% of baseline spend and barely move. That caps the achievable saving on short sessions, and explains the lower percentage on Opus: its cache writes and output fell less than Sonnet's.

### 4. Long-running commands are a friction point in Code Mode

In four Code Mode sessions (three Opus, one Sonnet) a shell command outlived the `REPL` timeout and was moved to the background, after which the model polled for its output. No baseline session hit this. Besides the two stress-test runs above, one Opus session lost 120 s to a `git commit` that waited on standard input. The cost effect was small; the wall-time effect was large.

## Recommendation

Use Code Mode as the default for routine interactive bug-fix and small-feature work in existing repositories, on either model. Outcomes were the same and context use was always lower. Expect about 20% lower cost on Sonnet and about 15% on Opus. The percentage is lower on Opus but the absolute saving is higher: about $0.09 per task against $0.04.

| Workflow | Fit | Reason |
|---|---|---|
| Exploration-heavy work: many search, read and test round trips | Best | The fixed context saving and batching compound; savings of about 30% on both models |
| Short or strictly sequential tasks | Modest | Only the fixed saving applies; 13% to 25% on Sonnet, about zero on Opus when the session is no shorter |
| Tasks dominated by long-running commands (slow test suites, builds) | Use with care | Commands that outlive the `REPL` timeout are moved to the background and polled, which costs wall time |
| Headless or CI use | Not available | `claude -p` does not offer Code Mode |

Do not choose Code Mode for speed: neither run shows a reliable wall-time gain.

## Limitations

- **The user's global `CLAUDE.md` was loaded in every session.** All 132 transcripts contain `~/.claude/CLAUDE.md` as an instructions attachment, despite `--setting-sources project,local`. Its workflow rules (feature branch, full test suite, commit, push, open a PR) were followed in both arms, so the comparison between arms is still like for like, but the absolute figures include that extra work and the README's isolation claim does not hold. The harness should be fixed before further runs.
- **Quality is untested.** Both arms passed 100% of runs on both models, so the suite cannot detect a quality gap in either direction. Scenarios where the baseline sometimes fails are needed.
- **Micro tier not run.** Fan-out, MCP-heavy and large-output patterns are where batching should matter most, and the controls are where overhead should show.
- **Haiku is unverified.** The single-repeat Haiku 5.5 pilot had `flask_ipv6_host` at +5% cost and +24% wall time under Code Mode.
- **Low statistical power.** With 3 repeats, most per-scenario deltas overlap: 5 of 11 separate on Sonnet and 4 of 11 on Opus.
- **Short sessions.** Runs used 4 to 26 requests and stayed under 75k tokens of context. Behaviour in long sessions, including compaction, was not measured.
- **Runs on different days and suite commits.** The two models were run a day apart on different suite commits, with the same scenarios and Claude Code version. Comparisons between arms within a model are sound; comparisons between models are indicative.

## Suggested next runs

1. Fix the `CLAUDE.md` isolation, then repeat one model on the repo tier to see how much the workflow rules added.
2. Micro tier on Sonnet 5.5 and Opus 5.5 with 3 or more repeats.
3. Harder repo scenarios with a baseline pass rate below 100%, to test for quality differences.
4. Repo tier at 5 repeats, to tighten the per-scenario ranges and to check whether the Opus stress-test behaviour recurs.
5. Repo tier on Haiku 5.5 with 3 repeats.
