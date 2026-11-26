# Code Mode benchmark report

- Run: `20261125-213223` started 2026-11-25T21:32:23+00:00
- Claude Code: 2.1.332 (Claude Code); permission mode `dontAsk`; effort `default`
- Repeats per scenario and arm: 1

Both arms use the same prompts, fixtures, model, settings and harness; the only difference is `CLAUDE_CODE_EXPERIMENTAL_CODE_MODE`. Figures are medians over valid runs. Δ is Code Mode relative to baseline (negative means Code Mode used less). A trailing `~` means the two arms' min-max ranges overlap, so the difference is within run-to-run noise.

## Totals

| Model | Arm | Runs | Valid | Passed | Input tok | Output tok | Cache read tok | Cache write tok | Input $ | Output $ | Cache read $ | Cache write $ | Total $ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-sonnet-5-5 | baseline | 2 | 2 | 2 | 2,812 | 11,220 | 1,506,755 | 77,499 | 0.00 | 0.11 | 0.15 | 0.31 | 0.57 |
| claude-sonnet-5-5 | codemode | 2 | 2 | 2 | 2,798 | 9,474 | 708,866 | 53,185 | 0.00 | 0.09 | 0.07 | 0.21 | 0.38 |

**Total cost of this benchmark run: $0.95** (list prices as reported by Claude Code).

## claude-sonnet-5-5

| Scenario | Category | Pass base | Pass code | Cost $ base | Cost $ code | Δ | Tokens base | Tokens code | Δ | API requests base | API requests code | Δ | Wall s base | Wall s code | Δ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hono_router_params | repo: bug fix | 1/1 | 1/1 | 0.3176 | 0.2213 | -30% | 1,241,696 | 569,233 | -54% | 25 | 18 | -28% | 259 | 207 | -20% |
| flask_ipv6_host | repo: bug fix | 1/1 | 1/1 | 0.2552 | 0.1570 | -38% | 356,590 | 205,090 | -42% | 8 | 8 | +0% ~ | 36 | 34 | -6% |

