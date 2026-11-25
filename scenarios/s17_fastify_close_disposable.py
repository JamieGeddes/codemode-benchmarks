"""Real feature in Fastify: addHook('onClose', disposable)."""
from ._repo import task

META, PROMPT, setup, solve, verify = task(
    id="fastify_close_disposable",
    title="Fastify: disposable objects as onClose hooks",
    repo="fastify",
    fix="5d4c23352d90c2474bfaf1a0d530c86b699cb795",
    category="repo: feature",
    hypothesis="Unclear: read a few neighbouring files, then write code and tests; little to batch.",
    run=["test/close-disposable.test.js"],
    prompt=(
        "Feature request: let `addHook('onClose', ...)` accept a disposable object as well as a function, so "
        "that resources following the explicit resource management protocol can be registered directly: "
        "`fastify.addHook('onClose', pool)`. An object with a `Symbol.asyncDispose` method has that method "
        "awaited when the instance closes; otherwise an object with a `Symbol.dispose` method has it called. "
        "If both exist the async one is used. A rejection or a thrown error must make `close()` reject with "
        "that error, the fulfilment value is ignored, and disposables must run in the same order as function "
        "hooks registered at the same place would. Anything that is neither a function nor a disposable must "
        "throw `FST_ERR_HOOK_INVALID_HANDLER` at registration, as before. Update the TypeScript types and the "
        "hooks documentation, and add tests."
    ),
)
