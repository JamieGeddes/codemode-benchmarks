"""Real bug fix in Hono: async JSX components that resolve to null, a boolean or a number."""
from ._repo import task

META, PROMPT, setup, solve, verify = task(
    id="hono_jsx_async",
    title="Hono: async components resolving to null, booleans or numbers",
    repo="hono",
    fix="6e8fbe186665d48a59c9aafc5e065925a168a37b",
    category="repo: bug fix",
    hypothesis="Unclear: most of the work is locating the code in a real codebase, then a small edit and a test run.",
    run=["src/jsx/index.test.tsx", "src/jsx/streaming.test.tsx", "src/helper/html/index.test.ts"],
    prompt=(
        "Bug report: with the built-in JSX renderer, a function component may return null, undefined, a "
        "boolean, a number or a string, and that works for synchronous components. The async equivalents are "
        "broken: `const Count = async () => 1` used as `<div><Count /></div>` should render `<div>1</div>`, "
        "and an async component resolving to null, undefined, true or false should render nothing "
        "(`<div></div>`), exactly as the synchronous versions do. The same goes for an async component inside "
        "`<Suspense>` when streaming, and for a promise interpolated into the html tagged template helper: "
        "html`<p>${Promise.resolve(false)}</p>` should resolve to `<p></p>` and a promise of 0 to `<p>0</p>`. "
        "TypeScript should also accept such components. Find the cause, fix it and add tests."
    ),
)
