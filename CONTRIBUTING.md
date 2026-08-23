# Contributing to AI Impact

Thanks for considering it. A few things to know before opening a PR.

## The core rule

The deterministic core (`core/`) must never let an LLM decide a finding. Rules produce evidence; the optional `ai/explainer.py` layer only ever phrases evidence that already exists. If your change touches `core/`, it must not introduce a path where a number, caller, or risk label depends on a model call. This is the whole reason the project is trustworthy — see `AI_Impact_Analyzer_PLAN.md` sections 3, 5, and 12 for the reasoning.

## Good first issues

- New fixture repos/diffs for `tests/` — every new fixture directly hardens the core engine and is low-risk to review.
- CLI output formatting improvements (`cli/main.py`'s `_render_text`).
- Extending `docs/MCP_SETUP.md` with verified setup steps for another MCP host (Cursor, Claude Code, Windsurf).
- Improving error messages, especially around unresolved/ambiguous call-graph cases.

## Higher-bar contributions

Changes to `core/blast_radius.py` or `core/risk.py` must:
1. Pass the full fixture suite (`pytest tests/`) — 14 tests currently, all fixture-driven, none mocked.
2. Ideally add a new fixture that specifically proves the case being fixed. A rule change without a fixture demonstrating why is hard to review and easy to regress later.
3. Preserve the "no unearned precision" rule — no new fabricated confidence scores, no dollar figures without a shown calculation, no risk label without evidence backing it.

Run the full suite before opening a PR:

```bash
python -m pytest tests/ -v
```

## Explicit non-goals

Please don't open PRs for:
- **Security vulnerability scanning** — that's a different, already-crowded category (Snyk, Semgrep). This tool does change-impact and test-gap analysis only.
- **Auto-applying fixes or auto-committing code** — the "suggest a test/fix" direction (plan section 18, v3) is explicitly assistive-only: a developer reviews and applies it, the tool never modifies the repo on its own.
- **Multi-repo / cross-service analysis** in v0/v1 — out of scope until the single-repo core is proven.
- Adding a second language (JS/TS, etc.) before the Python core has a wider real-world usage — see plan section 4 for why v0 is Python-only.

## Project layout

```text
core/       deterministic engine — diff parsing, AST, call graph, blast radius, test mapping, risk scoring
cli/        thin CLI adapter over core/
mcp_impact/ thin MCP server adapter over core/ (named to avoid shadowing the `mcp` SDK package)
ai/         optional LLM explanation layer, zero required dependencies, activates only if an API key is set
tests/      fixture-driven tests — real temp git repos built per test, not mocks
docs/       MCP_SETUP.md and friends
```

If you're touching `core/`, `cli/` and `mcp_impact/` should not need changes — that's the point of the shared-core architecture. If a fix to a bug requires touching both, that's a signal the logic leaked out of `core/` and should be moved back in.

## Style

No enforced formatter yet — match the existing style (type hints, dataclasses for data, small focused functions). Comments explain *why*, not *what* — see the top-of-file docstrings in `core/` for the tone to match.
