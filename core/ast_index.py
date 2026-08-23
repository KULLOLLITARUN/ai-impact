"""AST parsing: build a per-file symbol table (functions, methods, classes).

This stage only looks at one file's source at a time and has no notion of
imports or calls -- that's `graph.py`. Keeping this stage narrow makes it
independently testable and keeps the "static approximate call graph" built
in clearly separable stages (see AI_Impact_Analyzer_PLAN.md section 7).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from core.models import Symbol


@dataclass(frozen=True)
class Signature:
    param_names: tuple[str, ...]
    defaults_count: int
    has_varargs: bool
    has_kwargs: bool


@dataclass
class FileIndex:
    path: str
    symbols: dict[str, Symbol]        # qualified_name -> Symbol
    signatures: dict[str, Signature]  # qualified_name -> Signature (functions/methods only)
    tree: ast.Module


def module_name(path: str) -> str:
    return path[:-3].replace("/", ".").replace("\\", ".") if path.endswith(".py") else path


_module_name = module_name


def _signature_of(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Signature:
    args = node.args
    names = [a.arg for a in args.posonlyargs] + [a.arg for a in args.args] + [a.arg for a in args.kwonlyargs]
    return Signature(
        param_names=tuple(names),
        defaults_count=len(args.defaults) + len(args.kw_defaults),
        has_varargs=args.vararg is not None,
        has_kwargs=args.kwarg is not None,
    )


def index_file(path: str, source: str) -> FileIndex:
    tree = ast.parse(source, filename=path)
    module_prefix = _module_name(path)

    symbols: dict[str, Symbol] = {}
    signatures: dict[str, Signature] = {}

    def visit_function(node: ast.FunctionDef | ast.AsyncFunctionDef, qual_prefix: str, kind: str) -> None:
        qual_name = f"{qual_prefix}.{node.name}"
        symbols[qual_name] = Symbol(
            qualified_name=qual_name,
            file=path,
            lineno=node.lineno,
            end_lineno=node.end_lineno or node.lineno,
            kind=kind,
        )
        signatures[qual_name] = _signature_of(node)

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            visit_function(node, module_prefix, "function")
        elif isinstance(node, ast.ClassDef):
            class_qual = f"{module_prefix}.{node.name}"
            symbols[class_qual] = Symbol(
                qualified_name=class_qual,
                file=path,
                lineno=node.lineno,
                end_lineno=node.end_lineno or node.lineno,
                kind="class",
            )
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    visit_function(sub, class_qual, "method")

    return FileIndex(path=path, symbols=symbols, signatures=signatures, tree=tree)


def symbol_at_line(file_index: FileIndex, lineno: int) -> Symbol | None:
    """Return the innermost (deepest) symbol whose body contains `lineno`, if any."""
    best: Symbol | None = None
    for sym in file_index.symbols.values():
        if sym.lineno <= lineno <= sym.end_lineno:
            if best is None or (sym.end_lineno - sym.lineno) < (best.end_lineno - best.lineno):
                best = sym
    return best
