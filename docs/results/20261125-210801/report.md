# Code Mode benchmark report

- Run: `20261125-210801` started 2026-11-25T21:08:01+00:00
- Claude Code: 2.1.332 (Claude Code); permission mode `dontAsk`; effort `default`
- Repeats per scenario and arm: 1

Both arms use the same prompts, fixtures, model, settings and harness; the only difference is `CLAUDE_CODE_EXPERIMENTAL_CODE_MODE`. Figures are medians over valid runs. Δ is Code Mode relative to baseline (negative means Code Mode used less). A trailing `~` means the two arms' min-max ranges overlap, so the difference is within run-to-run noise.

## Totals

| Model | Arm | Runs | Valid | Passed | Input tok | Output tok | Cache read tok | Cache write tok | Input $ | Output $ | Cache read $ | Cache write $ | Total $ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-haiku-5-5 | baseline | 2 | 2 | 2 | 3,350 | 39,673 | 3,159,590 | 98,324 | 0.00 | 0.02 | 0.03 | 0.02 | 0.07 |
| claude-haiku-5-5 | codemode | 2 | 2 | 2 | 3,840 | 35,061 | 2,015,099 | 100,342 | 0.00 | 0.02 | 0.02 | 0.02 | 0.06 |

**Total cost of this benchmark run: $0.13** (list prices as reported by Claude Code).

## claude-haiku-5-5

| Scenario | Category | Pass base | Pass code | Cost $ base | Cost $ code | Δ | Tokens base | Tokens code | Δ | API requests base | API requests code | Δ | Wall s base | Wall s code | Δ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hono_router_params | repo: bug fix | 1/1 | 1/1 | 0.0494 | 0.0350 | -29% | 2,252,016 | 1,324,310 | -41% | 31 | 23 | -26% | 188 | 165 | -12% |
| flask_ipv6_host | repo: bug fix | 1/1 | 1/1 | 0.0221 | 0.0231 | +5% | 1,048,921 | 830,032 | -21% | 18 | 18 | +0% ~ | 64 | 80 | +24% |

