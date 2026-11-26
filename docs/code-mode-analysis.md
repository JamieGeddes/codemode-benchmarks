# Code Mode benchmark analysis

- Run: `20261125-220716`, started 2026-11-25T22:07:16+00:00
- Suite commit: `1ed9afd`
- Claude Code 2.1.332, model `claude-sonnet-5-5`, permission mode `dontAsk`, default effort
- Scope: repo tier only, 11 scenarios × 2 arms × 3 repeats = 66 runs, all valid
- Source data: [`results/20261125-220716/`](results/20261125-220716/) (`report.md`, `summary.csv`, `manifest.json`, `results.jsonl`)
- Earlier pilot runs, 1 repeat on two scenarios: [`results/20261125-210801/`](results/20261125-210801/) (Haiku 5.5) and [`results/20261125-213223/`](results/20261125-213223/) (Sonnet 5.5)
- Per-session transcripts and the cloned test repositories are not committed. The per-request figures in the Explanation section come from the local transcripts under `results/<run-id>/runs/`.

The only difference between arms is `CLAUDE_CODE_EXPERIMENTAL_CODE_MODE`. Δ is Code Mode relative to baseline.

## Summary

Code Mode completed every task the baseline did, for about a fifth less money and with roughly 19k tokens less context in use. Most of the saving comes from a smaller fixed context that is re-read on every request; batching tool calls contributes a smaller share. The run cannot say anything about quality differences, because every run in both arms passed.

## Findings

### Totals

Sums over all 33 runs per arm, except peak context.

| Metric | Baseline | Code Mode | Δ |
|---|---|---|---|
| Passed | 33/33 | 33/33 | none |
| Cost | $6.33 | $4.97 | -21% |
| Cache-read tokens | 16,775,051 | 8,647,652 | -48% |
| Output tokens | 170,728 | 142,423 | -17% |
| Cache-write tokens | 736,009 | 673,524 | -8% |
| API requests | 365 | 318 | -13% |
| Tool calls (top level) | 378 | 285 | -25% |
| Peak context, per-scenario median | 46k to 60k | 27k to 41k | -32% to -40% |
| Wall time | 2,748 s | 2,222 s | -19% |

### Per scenario

Medians over 3 repeats. A trailing `~` means the two arms' min-max ranges overlap, so the difference is within run-to-run noise.

| Scenario | Category | Cost $ base | Cost $ code | Δ | Requests base | Requests code | Peak context base | Peak context code | Wall s base | Wall s code | Δ |
|---|---|---|---|---|---|---|---|---|---|---|---|
| hono_jsx_async | bug fix | 0.2552 | 0.2021 | -21% | 13 | 12 | 59,980 | 40,700 | 85 | 77 | -8% ~ |
| hono_method_override | bug fix | 0.2041 | 0.1502 | -26% ~ | 10 | 8 | 53,560 | 32,420 | 72 | 63 | -13% ~ |
| hono_router_params | bug fix | 0.2656 | 0.1860 | -30% ~ | 21 | 14 | 55,020 | 36,200 | 211 | 93 | -56% ~ |
| hono_trailing_slash_skip | feature | 0.1558 | 0.1294 | -17% ~ | 9 | 8 | 48,620 | 30,860 | 55 | 57 | +3% ~ |
| fastify_error_status | bug fix | 0.2221 | 0.1771 | -20% ~ | 12 | 9 | 55,050 | 36,070 | 135 | 89 | -34% ~ |
| fastify_not_found_hook | bug fix | 0.1618 | 0.1410 | -13% ~ | 11 | 9 | 49,460 | 32,690 | 85 | 85 | +0% ~ |
| fastify_close_disposable | feature | 0.2262 | 0.1687 | -25% | 11 | 11 | 55,110 | 34,530 | 109 | 83 | -23% |
| click_help_wrap | bug fix | 0.1208 | 0.0923 | -24% | 6 | 5 | 47,340 | 28,670 | 32 | 28 | -13% ~ |
| click_no_such_command | feature | 0.2244 | 0.1749 | -22% ~ | 11 | 12 | 53,840 | 32,630 | 61 | 58 | -5% ~ |
| flask_automatic_options | bug fix | 0.1525 | 0.1113 | -27% | 8 | 6 | 48,450 | 29,250 | 40 | 31 | -23% ~ |
| flask_ipv6_host | bug fix | 0.1330 | 0.1078 | -19% | 9 | 8 | 45,930 | 27,400 | 36 | 31 | -14% ~ |

- **Cost:** Code Mode was cheaper on median in all 11 scenarios, by 13% to 30%. The ranges separate cleanly in 5 scenarios; the other 6 overlap at 3 repeats.
- **Peak context:** lower in all 11 scenarios with no overlap, by a near-constant 17k to 21k tokens.
- **Correctness:** no difference between arms.
- **Wall time:** mostly noise. Only `fastify_close_disposable` separates cleanly. Much of the total gap comes from slow test runs in the baseline `hono_router_params` runs (median tool time 143 s against 36 s).

## Explanation

### 1. A smaller fixed context is the main driver

In the transcripts sampled (`click_help_wrap` and `hono_router_params`, repeat 1 of each arm), the first request carries about 39.9k tokens in baseline and 21.7k in Code Mode. That gap of roughly 18k tokens is re-read from cache on every subsequent request.

- 18.2k × 318 Code Mode requests ≈ 5.8M tokens, about 70% of the 8.1M cache-read saving.
- The remainder is largely explained by Code Mode making 47 fewer requests.
- The near-constant peak-context gap across all scenarios is consistent with a fixed saving that does not depend on the task.

The likely cause is a single `REPL` tool replacing the full set of tool schemas in the prompt. This is an inference from the token counts; the prompts themselves were not compared.

### 2. Batching helps, modestly

Code Mode made 285 `REPL` calls against 378 direct tool calls in baseline, which translated into 13% fewer API round trips. Each `REPL` run typically wrapped one to three inner tool calls (`Bash`, `Read`, `Edit`, `Write`).

- Largest effect on the exploration-heavy task: `hono_router_params` went from 21 to 14 requests.
- No effect on `click_no_such_command` (11 to 12) or `fastify_close_disposable` (11 to 11), which still saved 22% and 25% through the fixed context reduction.

### 3. The cost saving is smaller than the token saving

Total tokens fell by about half, cost by a fifth, because the tokens saved are the cheapest kind.

| Cost category | Baseline $ | Code Mode $ | Saving $ | Share of saving |
|---|---|---|---|---|
| Cache write (1h) | 2.94 | 2.69 | 0.25 | 18% |
| Output | 1.70 | 1.40 | 0.30 | 22% |
| Cache read | 1.68 | 0.86 | 0.81 | 60% |
| Input | 0.01 | 0.01 | 0.00 | 0% |
| **Total** | **6.33** | **4.97** | **1.36** | |

Cache writes are 47% of baseline spend and barely move, which caps the achievable saving on short sessions like these.

## Recommendation

Use Code Mode as the default for routine interactive bug-fix and small-feature work in existing repositories on Sonnet. Outcomes were the same, cost was about a fifth lower, and each session had roughly 19k tokens more context headroom.

| Workflow | Fit | Reason |
|---|---|---|
| Exploration-heavy work: many search, read and test round trips | Best | The fixed context saving and batching compound |
| Short or strictly sequential tasks | Good | Only the fixed context saving applies, still 13% to 25% here |
| Headless or CI use | Not available | `claude -p` does not offer Code Mode |

## Limitations

- **Quality is untested.** Both arms passed 100% of runs, so the suite cannot detect a quality gap in either direction. Scenarios where the baseline sometimes fails are needed.
- **Micro tier not run.** Fan-out, MCP-heavy and large-output patterns are where batching should matter most, and the controls are where overhead should show.
- **One model.** The single-repeat Haiku 5.5 pilot (`20261125-210801`) had `flask_ipv6_host` at +5% cost and +24% wall time under Code Mode, so the result may not transfer. The single-repeat Sonnet 5.5 pilot (`20261125-213223`) agrees with this run: -30% and -38% cost on its two scenarios.
- **Low statistical power.** With 3 repeats, most per-scenario deltas overlap. Five or more repeats would firm them up.
- **Short sessions.** Runs used 5 to 21 requests and stayed under 61k tokens of context. Behaviour in long sessions, including compaction, was not measured.

## Suggested next runs

1. Micro tier on Sonnet 5.5 with 3 or more repeats.
2. Repo tier on Haiku 5.5 and Opus 5.5 to check whether the result transfers across models.
3. Harder repo scenarios with a baseline pass rate below 100%, to test for quality differences.
4. Repo tier at 5 repeats to tighten the per-scenario ranges.
