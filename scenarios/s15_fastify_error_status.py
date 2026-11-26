"""Real bug fix in Fastify: errors carrying a status code above 599."""
from ._repo import task

META, PROMPT, setup, solve, verify = task(
    id="fastify_error_status",
    title="Fastify: out-of-range error status codes",
    repo="fastify",
    fix="9e9f61a6bf092bbd3cf8d10b792432aa8be085af",
    category="repo: bug fix",
    hypothesis="Unclear: most of the work is locating the code in a real codebase, then a small edit and a test run.",
    run=["test/reply-error.test.js", "test/diagnostics-channel/error-status.test.js"],
    prompt=(
        "Bug report: when a route handler throws or rejects with an error whose `statusCode` (or `status`) is "
        "not a valid HTTP error status, for example 600, Fastify uses that number for the response. Only "
        "values from 400 to 599 should be taken from an error; anything else must result in a 500, with the "
        "serialised error body reporting `statusCode: 500` as well. The status visible to subscribers of the "
        "`tracing:fastify.request.handler:error` diagnostics channel must agree with the status of the "
        "response that is sent. Find every place that derives a status from an error, fix them and add tests."
    ),
)
