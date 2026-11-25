"""Real bug fix in Fastify: reply.callNotFound() and hooks declared on setNotFoundHandler()."""
from ._repo import task

META, PROMPT, setup, solve, verify = task(
    id="fastify_not_found_hook",
    title="Fastify: callNotFound skips the not-found preHandler",
    repo="fastify",
    fix="4176096a31f5b4c31512c36f578b08a596a72435",
    category="repo: bug fix",
    hypothesis="Unclear: most of the work is locating the code in a real codebase, then a small edit and a test run.",
    run=["test/404s.test.js"],
    prompt=(
        "Bug report: hooks passed to `setNotFoundHandler()` are skipped depending on registration order. If a "
        "route whose handler calls `reply.callNotFound()` is registered before `setNotFoundHandler({ "
        "preHandler }, handler)`, the not-found handler runs but its preHandler never does. Registering the "
        "not-found handler first makes it work. Since preHandler hooks are often used for authorisation this "
        "must not depend on order. Find the cause, fix it without changing the behaviour of the other "
        "not-found features, and add a test."
    ),
)
