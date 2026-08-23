"""Static test -> exercised-symbol mapping (v0: no coverage.py data required).

A test is considered to "cover" a changed symbol if, by walking the call
graph forward from the test function, that symbol is reachable within a
bounded number of hops. This is a static approximation, not real coverage
instrumentation -- see plan section 9 & 20. Ingesting a real coverage.py
report for branch-level precision is a v1 concern, not v0.
"""

from __future__ import annotations

from core.graph import CallGraph, RepoIndex
from core.models import Symbol, TestGap

MAX_SEARCH_DEPTH = 10


def is_test_file(path: str) -> bool:
    base = path.rsplit("/", 1)[-1]
    return base.startswith("test_") or base.endswith("_test.py")


_is_test_file = is_test_file


def _is_test_symbol(sym: Symbol) -> bool:
    short_name = sym.qualified_name.rsplit(".", 1)[-1]
    return short_name.startswith("test_") or short_name.startswith("Test")


def find_covering_tests(
    call_graph: CallGraph,
    repo_index: RepoIndex,
    target: Symbol,
    max_depth: int = MAX_SEARCH_DEPTH,
) -> list[str]:
    """Backward BFS from `target` through the call graph, collecting any test
    functions found along the way (unbounded relative to the HIGH/MEDIUM/LOW
    blast-radius tiers -- coverage matters even from a distant test)."""
    covering: list[str] = []
    visited: set[str] = {target.qualified_name}
    frontier: list[tuple[Symbol, int]] = [(target, 0)]

    while frontier:
        current, depth = frontier.pop(0)
        if depth >= max_depth:
            continue
        for call_site in call_graph.callers_of.get(current.qualified_name, []):
            caller = call_site.caller
            if caller.qualified_name in visited:
                continue
            visited.add(caller.qualified_name)
            if _is_test_file(caller.file) and _is_test_symbol(caller):
                covering.append(caller.qualified_name)
            frontier.append((caller, depth + 1))

    return covering


def find_test_gap(target: Symbol, covering_tests: list[str]) -> TestGap | None:
    if covering_tests:
        return None
    return TestGap(changed_symbol=target, description="No test found that exercises this symbol")
