# Code Mode benchmark report

- Run: `20261126-093537` started 2026-11-26T09:35:37+00:00
- Claude Code: 2.1.332 (Claude Code); permission mode `dontAsk`; effort `default`
- Repeats per scenario and arm: 3

Both arms use the same prompts, fixtures, model, settings and harness; the only difference is `CLAUDE_CODE_EXPERIMENTAL_CODE_MODE`. Figures are medians over valid runs. Δ is Code Mode relative to baseline (negative means Code Mode used less). A trailing `~` means the two arms' min-max ranges overlap, so the difference is within run-to-run noise.

## Totals

| Model | Arm | Runs | Valid | Passed | Input tok | Output tok | Cache read tok | Cache write tok | Input $ | Output $ | Cache read $ | Cache write $ | Total $ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| claude-opus-5-5 | baseline | 33 | 33 | 33 | 49,874 | 276,331 | 28,253,376 | 1,004,131 | 0.02 | 5.51 | 5.65 | 8.03 | 19.22 |
| claude-opus-5-5 | codemode | 33 | 33 | 33 | 52,230 | 254,657 | 16,002,991 | 989,222 | 0.03 | 5.08 | 3.20 | 7.91 | 16.22 |

**Total cost of this benchmark run: $35.44** (list prices as reported by Claude Code).

## claude-opus-5-5

| Scenario | Category | Pass base | Pass code | Cost $ base | Cost $ code | Δ | Tokens base | Tokens code | Δ | API requests base | API requests code | Δ | Wall s base | Wall s code | Δ |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| hono_jsx_async | repo: bug fix | 3/3 | 3/3 | 0.8348 | 0.6663 | -20% | 1,439,836 | 804,341 | -44% | 23 | 18 | -22% ~ | 170 | 152 | -10% |
| hono_method_override | repo: bug fix | 3/3 | 3/3 | 0.4065 | 0.3844 | -5% ~ | 493,574 | 335,461 | -32% | 10 | 9 | -10% ~ | 94 | 90 | -4% ~ |
| hono_router_params | repo: bug fix | 3/3 | 3/3 | 0.8175 | 0.8687 | +6% ~ | 1,285,953 | 1,028,356 | -20% | 22 | 21 | -5% ~ | 162 | 168 | +4% ~ |
| hono_trailing_slash_skip | repo: feature | 3/3 | 3/3 | 0.3210 | 0.3199 | -0% ~ | 418,704 | 307,446 | -27% | 9 | 9 | +0% ~ | 75 | 78 | +4% ~ |
| fastify_error_status | repo: bug fix | 3/3 | 3/3 | 0.8183 | 0.7277 | -11% ~ | 1,379,574 | 994,598 | -28% | 24 | 22 | -8% ~ | 202 | 160 | -21% ~ |
| fastify_not_found_hook | repo: bug fix | 3/3 | 3/3 | 0.6923 | 0.4842 | -30% | 1,083,780 | 501,271 | -54% | 20 | 13 | -35% | 184 | 122 | -34% ~ |
| fastify_close_disposable | repo: feature | 3/3 | 3/3 | 0.8116 | 0.7139 | -12% ~ | 1,295,682 | 718,899 | -45% | 22 | 17 | -23% ~ | 184 | 172 | -7% |
| click_help_wrap | repo: bug fix | 3/3 | 3/3 | 0.4264 | 0.3278 | -23% ~ | 586,504 | 339,004 | -42% ~ | 12 | 11 | -8% ~ | 74 | 518 | +602% ~ |
| click_no_such_command | repo: feature | 3/3 | 3/3 | 0.4797 | 0.3887 | -19% ~ | 655,968 | 311,168 | -53% | 12 | 10 | -17% ~ | 80 | 86 | +8% ~ |
| flask_automatic_options | repo: bug fix | 3/3 | 3/3 | 0.3791 | 0.2695 | -29% | 467,969 | 197,712 | -58% | 9 | 6 | -33% | 64 | 47 | -27% |
| flask_ipv6_host | repo: bug fix | 3/3 | 3/3 | 0.4371 | 0.3030 | -31% | 759,913 | 313,857 | -59% | 16 | 11 | -31% ~ | 71 | 56 | -21% ~ |

