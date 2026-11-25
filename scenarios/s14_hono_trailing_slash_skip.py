"""Real feature in Hono: a `skip` option for appendTrailingSlash."""
from ._repo import task

META, PROMPT, setup, solve, verify = task(
    id="hono_trailing_slash_skip",
    title="Hono: skip option for the trailing-slash middleware",
    repo="hono",
    fix="f23e97b7f300bcb8571ae864010b8f7cdb5d0d5d",
    category="repo: feature",
    hypothesis="Unclear: read a few neighbouring files, then write code and tests; little to batch.",
    run=["src/middleware/trailing-slash/index.test.ts"],
    prompt=(
        "Feature request: `appendTrailingSlash` redirects paths that look like files, for example "
        "`/style.css` to `/style.css/`, which is never wanted. Add a `skip` option to `appendTrailingSlash`: "
        "a function that receives the request path and returns true when the redirect should not happen, for "
        "example `appendTrailingSlash({ alwaysRedirect: true, skip: (path) => /\\.\\w+$/.test(path) })`. It "
        "must work both with and without `alwaysRedirect`. Document the option in the same style as the "
        "existing ones and add tests."
    ),
)
