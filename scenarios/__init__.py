"""Benchmark scenarios. Each module defines META, PROMPT, setup(), solve() and verify()."""
import importlib
import pkgutil


def load_all():
    """Return {scenario id: module}, in file-name order."""
    out = {}
    for info in sorted(pkgutil.iter_modules(__path__), key=lambda m: m.name):
        if info.name.startswith("_"):
            continue
        module = importlib.import_module(f"{__name__}.{info.name}")
        out[module.META["id"]] = module
    return out
