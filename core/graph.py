"""Import graph + static approximate call graph, built across an entire repo.

Resolution strategy (deliberately conservative, see plan section 7 & 20):
  - `name(...)`            -> resolved against module-level symbols in the same
                               file first, then against `from x import name`.
  - `self.method(...)`     -> resolved against the enclosing class's methods.
  - `obj.method(...)`      -> best-effort: matched by method name against every
                               class in the repo that defines a method with that
                               name (no type inference). This can over-match on
                               common method names -- that's an accepted, stated
                               limitation, not a silent bug.
Calls that can't be resolved to a repo-local symbol (stdlib, third-party,
dynamic dispatch via getattr/eval) are dropped, not guessed at.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass, field

from core.ast_index import FileIndex, index_file, module_name
from core.models import CallSite, Symbol


@dataclass
class RepoIndex:
    files: dict[str, FileIndex]  # repo-relative path -> FileIndex

    def symbol(self, qualified_name: str) -> Symbol | None:
        for fi in self.files.values():
            if qualified_name in fi.symbols:
                return fi.symbols[qualified_name]
        return None

    def symbols_by_short_name(self, short_name: str) -> list[Symbol]:
        out = []
        for fi in self.files.values():
            for qn, sym in fi.symbols.items():
                if qn.rsplit(".", 1)[-1] == short_name and sym.kind == "method":
                    out.append(sym)
        return out


def build_repo_index(repo_path: str) -> RepoIndex:
    files: dict[str, FileIndex] = {}
    for root, _dirs, filenames in os.walk(repo_path):
        # Skip hidden directories (.git, .venv, etc.) -- but check this against
        # the path *relative to repo_path*, not the raw walked root. A relative
        # repo_path like "." makes os.walk's first root literally the string
        # ".", which itself starts with "." and would otherwise wrongly skip
        # the repo's own top-level files on every relative-path invocation.
        rel_root = os.path.relpath(root, repo_path)
        if rel_root != "." and any(part.startswith(".") for part in rel_root.split(os.sep)):
            continue
        for name in filenames:
            if not name.endswith(".py"):
                continue
            abs_path = os.path.join(root, name)
            rel_path = os.path.relpath(abs_path, repo_path).replace(os.sep, "/")
            with open(abs_path, "r", encoding="utf-8") as f:
                source = f.read()
            try:
                files[rel_path] = index_file(rel_path, source)
            except SyntaxError:
                continue  # unparseable file: excluded, not guessed at
    return RepoIndex(files=files)


@dataclass
class CallGraph:
    # callee qualified_name -> list of CallSite (who calls it, from where)
    callers_of: dict[str, list[CallSite]] = field(default_factory=dict)

    def add(self, call_site: CallSite) -> None:
        self.callers_of.setdefault(call_site.callee.qualified_name, []).append(call_site)


def _enclosing_symbol(file_index: FileIndex, lineno: int) -> Symbol | None:
    best: Symbol | None = None
    for sym in file_index.symbols.values():
        if sym.kind == "class":
            continue
        if sym.lineno <= lineno <= sym.end_lineno:
            if best is None or (sym.end_lineno - sym.lineno) < (best.end_lineno - best.lineno):
                best = sym
    return best


def _class_qual_of(qualified_name: str) -> str | None:
    parts = qualified_name.rsplit(".", 2)
    return parts[0] + "." + parts[1] if len(parts) == 3 else None


def _build_import_map(repo_index: RepoIndex, file_index: FileIndex) -> dict[str, str]:
    """local name -> qualified_name of a repo-local symbol, for `from module import name`.

    Absolute imports only (level=0) in v0 -- relative imports (`from . import x`)
    are not resolved and calls through them are dropped, not guessed at.
    """
    module_by_name = {module_name(p): p for p in repo_index.files}
    import_map: dict[str, str] = {}

    for node in ast.walk(file_index.tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            target_path = module_by_name.get(node.module)
            if target_path is None:
                continue
            target_file = repo_index.files[target_path]
            for alias in node.names:
                qual = f"{node.module}.{alias.name}"
                if qual in target_file.symbols:
                    import_map[alias.asname or alias.name] = qual

    return import_map


def build_call_graph(repo_index: RepoIndex) -> CallGraph:
    graph = CallGraph()

    for path, file_index in repo_index.files.items():
        module_symbol_names = {qn.rsplit(".", 1)[-1]: qn for qn in file_index.symbols}
        import_map = _build_import_map(repo_index, file_index)

        for node in ast.walk(file_index.tree):
            if not isinstance(node, ast.Call):
                continue

            caller_symbol = _enclosing_symbol(file_index, node.lineno)
            if caller_symbol is None:
                continue  # module-level call outside any function: ignored in v0

            callee: Symbol | None = None
            func = node.func

            if isinstance(func, ast.Name):
                qn = module_symbol_names.get(func.id)
                if qn:
                    callee = file_index.symbols[qn]
                elif func.id in import_map:
                    callee = repo_index.symbol(import_map[func.id])

            elif isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "self":
                class_qual = _class_qual_of(caller_symbol.qualified_name)
                if class_qual:
                    method_qual = f"{class_qual}.{func.attr}"
                    callee = file_index.symbols.get(method_qual) or repo_index.symbol(method_qual)

            elif isinstance(func, ast.Attribute):
                candidates = repo_index.symbols_by_short_name(func.attr)
                if len(candidates) == 1:
                    callee = candidates[0]
                # ambiguous (0 or >1 candidates): dropped, not guessed at

            if callee is not None:
                graph.add(
                    CallSite(
                        caller=caller_symbol,
                        callee=callee,
                        file=path,
                        lineno=node.lineno,
                    )
                )

    return graph
