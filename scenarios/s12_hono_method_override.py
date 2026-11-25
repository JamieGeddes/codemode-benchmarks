"""Real bug fix in Hono: the method-override middleware when the new method cannot carry a body."""
from ._repo import task

META, PROMPT, setup, solve, verify = task(
    id="hono_method_override",
    title="Hono: method override to GET or HEAD keeps the body",
    repo="hono",
    fix="64a1d5a9e53bf244ab13caff7b7d64dcbfb803de",
    category="repo: bug fix",
    hypothesis="Unclear: most of the work is locating the code in a real codebase, then a small edit and a test run.",
    run=["src/middleware/method-override/index.test.ts"],
    prompt=(
        "Bug report: the method override middleware fails when a POST is overridden to GET or HEAD (in any "
        "letter case), because the rewritten request still carries the original body, which is not allowed "
        "for those methods. It happens with every way of choosing the method: the form field (multipart and "
        "urlencoded bodies), the header option and the query option. When overriding to GET or HEAD the body "
        "should be dropped and the downstream handler should see neither a Content-Type nor a Content-Length "
        "header. A related problem: when a urlencoded form is overridden to another method such as DELETE, "
        "the handler still sees the Content-Length of the original body even though the method field has been "
        "removed from it; the stale header should not be passed on. Fix both and add tests."
    ),
)
