"""Real bug fix in Flask: host strings that contain an IPv6 address."""
from ._repo import task

META, PROMPT, setup, solve, verify = task(
    id="flask_ipv6_host",
    title="Flask: IPv6 literals in host names",
    repo="flask",
    fix="05e9c6bd630ecf4ec0ec884b1fc7901663737bc7",
    category="repo: bug fix",
    hypothesis="Unclear: most of the work is locating the code in a real codebase, then a small edit and a test run.",
    run=["tests/test_basic.py", "tests/test_testing.py"],
    select=["-k", "test_session_transaction_ipv6 or test_run_server_port"],
    prompt=(
        "Bug report: IPv6 addresses are mishandled wherever a host and port are split apart. Two symptoms: "
        "with `SERVER_NAME = '[::1]:8080'`, `app.run()` does not start the development server on host `::1` "
        "and port 8080; and with the test client, a session set through "
        "`client.session_transaction(base_url='http://[::1]:8000/')` is not seen by a following "
        "`client.get('/', base_url='http://[::1]:8000/')`. Both work for names such as `localhost:8080`. Find "
        "the places that take a host apart, fix them and add tests."
    ),
)
