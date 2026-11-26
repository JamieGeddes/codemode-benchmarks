"""Real bug fix in Click: line wrapping of help text."""
from ._repo import task

META, PROMPT, setup, solve, verify = task(
    id="click_help_wrap",
    title="Click: help text wraps inside hyphenated words",
    repo="click",
    fix="a46a95c733d0ed72f63cd2915f2bc4a09a7179f9",
    category="repo: bug fix",
    hypothesis="Unclear: most of the work is locating the code in a real codebase, then a small edit and a test run.",
    run=["tests/test_formatting.py"],
    select=["-k", "test_wrap_text_keeps_words_whole"],
    prompt=(
        "Bug report: generated help pages sometimes break a line in the middle of a word. Option names are "
        "the worst case: `click.formatting.wrap_text('Add --avoid-motorways to stay on country roads.', 20)` "
        "splits `--avoid-motorways` after one of its hyphens. Wrapped text should only ever break between "
        "words. A word that is wider than the available width must not be cut either: it goes on a line of "
        "its own, and this also holds when the word is wrapped in ANSI style codes, which must survive "
        "intact. Fix the wrapping used for help output and add tests."
    ),
)
