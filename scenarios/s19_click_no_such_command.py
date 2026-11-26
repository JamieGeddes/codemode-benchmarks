"""Real feature in Click: a NoSuchCommand exception with suggestions."""
from ._repo import task

META, PROMPT, setup, solve, verify = task(
    id="click_no_such_command",
    title="Click: suggest close matches for an unknown command",
    repo="click",
    fix="831c8f0948af519e45b90801d7430ff25451f972",
    category="repo: feature",
    hypothesis="Unclear: read a few neighbouring files, then write code and tests; little to batch.",
    run=["tests/test_commands.py", "tests/test_options.py"],
    select=["-k", "test_unknown_command or test_suggest_possible_commands or test_unknown_options or test_suggest_possible_options"],
    prompt=(
        "Feature request: a mistyped option gets a helpful suggestion but a mistyped subcommand only gets \"No "
        "such command 'x'.\". Add a `NoSuchCommand` exception (a `UsageError`, exported from the top-level "
        "`click` package like `NoSuchOption`) that a group raises for an unknown command, and give it the "
        "same suggestion behaviour as options, based on close matches among the group's command names. Make "
        "the two consistent: the messages are \"No such command 'pause'.\" and \"No such option '--bounds'.\", "
        "followed by a space and either \"Did you mean 'push'?\" for one close match or \"(Did you mean one of: "
        "'declare', 'refine'?)\" for several (names quoted and sorted). Both exceptions should accept the full "
        "collection of valid names as `possibilities` and work out the close matches themselves. Add a "
        "changelog entry and tests."
    ),
)
