"""Changed-symbol detection + backward call-graph walk (blast radius).

Pipeline for this stage:
  diff line ranges -> enclosing AST symbols (in the new file)
  old vs new signature comparison -> signature_changed flag
  backward walk of the call graph from each changed symbol, bounded depth
    -> AffectedCaller list, tiered by hop distance (see plan section 8)
"""

from __future__ import annotations

import subprocess

from core.ast_index import Signature, index_file, symbol_at_line
from core.diff import FileDiff
from core.graph import CallGraph, RepoIndex
from core.models import AffectedCaller, CallerTier, ChangedSymbol, Symbol
from core.test_mapping import is_test_file

_TIER_BY_DEPTH = {1: CallerTier.HIGH, 2: CallerTier.MEDIUM, 3: CallerTier.LOW}
MAX_DEPTH = 3


def _old_source(repo_path: str, diff_ref: str | None, staged: bool, path: str) -> str | None:
    """Best-effort fetch of a file's pre-change content. None if unavailable (new file)."""
    ref = "HEAD" if staged else (diff_ref or "HEAD")
    # stdin=DEVNULL: see the matching comment in diff.py -- prevents inheriting
    # a live MCP JSON-RPC pipe as this child's stdin (Windows deadlock).
    result = subprocess.run(
        ["git", "-C", repo_path, "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    return result.stdout if result.returncode == 0 else None


def _signature_changed(old_sig: Signature | None, new_sig: Signature | None) -> bool:
    if old_sig is None or new_sig is None:
        return old_sig != new_sig
    return (
        old_sig.param_names != new_sig.param_names
        or old_sig.has_varargs != new_sig.has_varargs
        or old_sig.has_kwargs != new_sig.has_kwargs
    )


def detect_changed_symbols(
    repo_path: str,
    repo_index: RepoIndex,
    file_diffs: list[FileDiff],
    diff_ref: str | None,
    staged: bool = False,
) -> list[ChangedSymbol]:
    changed: dict[str, ChangedSymbol] = {}

    for fd in file_diffs:
        new_file_index = repo_index.files.get(fd.path)
        if new_file_index is None:
            continue  # deleted or unparseable file: excluded, not guessed at

        old_source = _old_source(repo_path, diff_ref, staged, fd.path)
        old_file_index = None
        if old_source is not None:
            try:
                old_file_index = index_file(fd.path, old_source)
            except SyntaxError:
                old_file_index = None

        for rng in fd.changed_ranges:
            for lineno in range(rng.start, rng.end + 1):
                sym = symbol_at_line(new_file_index, lineno)
                if sym is None or sym.kind == "class":
                    continue

                old_sig = old_file_index.signatures.get(sym.qualified_name) if old_file_index else None
                new_sig = new_file_index.signatures.get(sym.qualified_name)
                sig_changed = _signature_changed(old_sig, new_sig)

                existing = changed.get(sym.qualified_name)
                if existing is None:
                    changed[sym.qualified_name] = ChangedSymbol(
                        symbol=sym, signature_changed=sig_changed, changed_lines=1
                    )
                else:
                    existing.changed_lines += 1
                    existing.signature_changed = existing.signature_changed or sig_changed

    return list(changed.values())


def compute_blast_radius(
    call_graph: CallGraph,
    changed_symbols: list[ChangedSymbol],
    max_depth: int = MAX_DEPTH,
) -> dict[str, list[AffectedCaller]]:
    """Returns changed-symbol qualified_name -> list of AffectedCaller, backward BFS."""
    result: dict[str, list[AffectedCaller]] = {}

    for cs in changed_symbols:
        visited: set[str] = {cs.symbol.qualified_name}
        frontier: list[tuple[Symbol, int]] = [(cs.symbol, 0)]
        affected: list[AffectedCaller] = []

        while frontier:
            current_sym, depth = frontier.pop(0)
            if depth >= max_depth:
                continue
            for call_site in call_graph.callers_of.get(current_sym.qualified_name, []):
                caller = call_site.caller
                if caller.qualified_name in visited:
                    continue
                visited.add(caller.qualified_name)
                if is_test_file(caller.file):
                    # Test callers are a test-coverage signal (see test_mapping.py),
                    # not a production blast-radius signal -- excluded here so a
                    # well-tested function doesn't look riskier than an untested one.
                    continue
                hop = depth + 1
                tier = _TIER_BY_DEPTH.get(hop, CallerTier.LOW)
                affected.append(
                    AffectedCaller(
                        symbol=caller,
                        tier=tier,
                        call_site=call_site,
                        dependency_depth=hop,
                    )
                )
                frontier.append((caller, hop))

        result[cs.symbol.qualified_name] = affected

    return result
