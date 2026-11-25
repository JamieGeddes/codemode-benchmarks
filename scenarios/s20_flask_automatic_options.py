"""Real bug fix in Flask: per-view override of automatic OPTIONS handling."""
from ._repo import task

META, PROMPT, setup, solve, verify = task(
    id="flask_automatic_options",
    title="Flask: provide_automatic_options cannot be enabled per view",
    repo="flask",
    fix="12e95c93b488725f80753f34b2e0d24838ca4646",
    category="repo: bug fix",
    hypothesis="Unclear: most of the work is locating the code in a real codebase, then a small edit and a test run.",
    run=["tests/test_basic.py", "tests/test_views.py"],
    select=["-k", "provide_automatic_options"],
    prompt=(
        "Bug report: with `app.config['PROVIDE_AUTOMATIC_OPTIONS'] = False`, a single view cannot opt back "
        "in. Setting `provide_automatic_options = True` on a view function or on a `View` class has no "
        "effect: an OPTIONS request to that route is not answered with the allowed methods (GET, HEAD, "
        "OPTIONS). Opting out per view when the config is enabled does work. The per-view setting should win "
        "in both directions, and a route that handles OPTIONS itself must be left alone. Fix it, add a "
        "changelog entry and tests."
    ),
)
