"""Real bug fix in Hono: a repeated path parameter name resolves differently depending on the router chosen."""
from ._repo import task

META, PROMPT, setup, solve, verify = task(
    id="hono_router_params",
    title="Hono: duplicate path parameter value depends on unrelated routes",
    repo="hono",
    fix="08807ce12aa3aa27c8c5adf63e677bbab6bceda9",
    category="repo: bug fix",
    hypothesis="Unclear: most of the work is locating the code in a real codebase, then a small edit and a test run.",
    run=["src/hono.test.ts", "src/router/trie-router/node.test.ts", "src/router/trie-router/router.test.ts"],
    prompt=(
        "Bug report: a route that uses the same parameter name twice gives inconsistent results. With only "
        "`app.get('/:id/:id/x', (c) => c.text(c.req.param('id')))` registered, a request to `/123/456/x` "
        "returns `123`. After adding a completely unrelated route such as `app.get('/a', ...)`, the same "
        "request returns `456`. Registering an unrelated route must not change the result: when a parameter "
        "name is repeated, the first value should win everywhere (so `/:id/:id/:id` matched against `/1/2/3` "
        "gives `1`). Find out why the behaviour differs, fix it and add tests."
    ),
)
