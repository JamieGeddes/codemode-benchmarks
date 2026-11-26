# Code Mode benchmark report

- Run: `20261125-220716` started 2026-11-25T22:07:16+00:00
- Claude Code: 2.1.332 (Claude Code); permission mode `dontAsk`; effort `default`
- Repeats per scenario and arm: 3

Both arms use the same prompts, fixtures, model, settings and harness; the only difference is `CLAUDE_CODE_EXPERIMENTAL_CODE_MODE`. Figures are medians over valid runs. Δ is Code Mode relative to baseline (negative means Code Mode used less). A trailing `~` means the two arms' min-max ranges overlap, so the difference is within run-to-run noise.

## Totals

| Model | Arm | Runs | Valid | Passed | Input tok | Output tok | Cache read tok | Cache write tok | Input $ | Output $ | Cache read $ | Cache write $ | Total $ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-sonnet-5-5 | baseline | 33 | 33 | 33 | 47,006 | 170,728 | 16,775,051 | 736,009 | 0.01 | 1.70 | 1.68 | 2.94 | 6.33 |
| claude-sonnet-5-5 | codemode | 33 | 33 | 33 | 46,910 | 142,423 | 8,647,652 | 673,524 | 0.01 | 1.40 | 0.86 | 2.69 | 4.97 |

**Total cost of this benchmark run: $11.30** (list prices as reported by Claude Code).

## claude-sonnet-5-5

| Scenario | Category | Pass base | Pass code | Cost $ base | Cost $ code | Δ | Tokens base | Tokens code | Δ | API requests base | API requests code | Δ | Wall s base | Wall s code | Δ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hono_jsx_async | repo: bug fix | 3/3 | 3/3 | 0.2552 | 0.2021 | -21% | 700,930 | 404,605 | -42% | 13 | 12 | -8% | 85 | 77 | -8% ~ |
| hono_method_override | repo: bug fix | 3/3 | 3/3 | 0.2041 | 0.1502 | -26% ~ | 496,023 | 233,512 | -53% | 10 | 8 | -20% ~ | 72 | 63 | -13% ~ |
| hono_router_params | repo: bug fix | 3/3 | 3/3 | 0.2656 | 0.1860 | -30% ~ | 1,012,749 | 426,033 | -58% | 21 | 14 | -33% ~ | 211 | 93 | -56% ~ |
| hono_trailing_slash_skip | repo: feature | 3/3 | 3/3 | 0.1558 | 0.1294 | -17% ~ | 403,409 | 224,596 | -44% | 9 | 8 | -11% ~ | 55 | 57 | +3% ~ |
| fastify_error_status | repo: bug fix | 3/3 | 3/3 | 0.2221 | 0.1771 | -20% ~ | 617,924 | 280,650 | -55% ~ | 12 | 9 | -25% ~ | 135 | 89 | -34% ~ |
| fastify_not_found_hook | repo: bug fix | 3/3 | 3/3 | 0.1618 | 0.1410 | -13% ~ | 505,282 | 260,479 | -48% ~ | 11 | 9 | -18% ~ | 85 | 85 | +0% ~ |
| fastify_close_disposable | repo: feature | 3/3 | 3/3 | 0.2262 | 0.1687 | -25% | 536,289 | 339,161 | -37% | 11 | 11 | +0% ~ | 109 | 83 | -23% |
| click_help_wrap | repo: bug fix | 3/3 | 3/3 | 0.1208 | 0.0923 | -24% | 269,025 | 134,939 | -50% | 6 | 5 | -17% ~ | 32 | 28 | -13% ~ |
| click_no_such_command | repo: feature | 3/3 | 3/3 | 0.2244 | 0.1749 | -22% ~ | 559,384 | 382,348 | -32% ~ | 11 | 12 | +9% ~ | 61 | 58 | -5% ~ |
| flask_automatic_options | repo: bug fix | 3/3 | 3/3 | 0.1525 | 0.1113 | -27% | 363,862 | 160,164 | -56% | 8 | 6 | -25% ~ | 40 | 31 | -23% ~ |
| flask_ipv6_host | repo: bug fix | 3/3 | 3/3 | 0.1330 | 0.1078 | -19% | 391,832 | 201,712 | -49% | 9 | 8 | -11% ~ | 36 | 31 | -14% ~ |

