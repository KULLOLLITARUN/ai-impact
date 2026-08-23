# AI Impact

Analyzes the statically discoverable blast radius of a Python code change, identifies likely test gaps, and (optionally) uses an LLM to explain the findings in plain language.

The deterministic core needs no API key and no setup beyond Python + git. It never invents a caller, a risk level, or a dollar figure — every number in a report is traceable back to the diff and the repo's own call graph. See [`AI_Impact_Analyzer_PLAN.md`](../r%26d/AI_Impact_Analyzer_PLAN.md) for the full design.

## Install

```bash
git clone <this-repo>
cd ai-impact
pip install -e .
```

No third-party dependencies for the core engine or CLI — just Python 3.10+ and `git` on your PATH.

## Usage

```bash
# Compare working tree against a commit
ai-impact analyze --diff HEAD~1

# Compare a branch against main
ai-impact analyze --diff main...HEAD

# Analyze staged changes before you commit
ai-impact analyze --staged

# Machine-readable output for CI
ai-impact analyze --diff HEAD~1 --json
```

Or run without installing:

```bash
python -m cli.main analyze --diff HEAD~1
```

### Exit codes (for CI gating)

| Code | Meaning |
|---|---|
| 0 | No findings, or only LOW risk |
| 1 | MEDIUM risk found |
| 2 | HIGH risk found |
| 3 | Analysis error (not a code-quality signal) |

## What it does

```text
Git diff -> AST -> static approximate call graph -> backward blast-radius
walk -> test-coverage mapping -> deterministic risk score -> report
```

For each function/method touched by the diff, it reports:
- Whether the function's **signature changed**
- Which callers are affected, tiered by how many hops away they are (direct caller = HIGH, 2 hops = MEDIUM, 3 hops = LOW)
- Whether any test in the repo actually exercises the changed code (static call-graph reachability, not runtime coverage instrumentation, in v0)
- A `HIGH` / `MEDIUM` / `LOW` risk label, always shown with the evidence behind it — never a bare unexplained number

## Limitations (read before trusting a report)

- **Static analysis, not proof.** Dynamic Python (`getattr`, `eval`, metaclasses, dependency injection) can hide real call relationships from the analyzer.
- **Test mapping is a static approximation** in v0 — it checks whether a test *calls* the changed code via the call graph, not whether a `coverage.py` run actually executed the new branch.
- **Single-repo only.** If another service depends on this code, this tool can't see that.
- **`LOW` risk is not a safety guarantee** — it means the checks this tool runs found nothing, not that the change is safe. Treat it as one input to review, not a replacement for it.
- **Not a security scanner.** This tool does change-impact and test-gap analysis only.

## MCP (for agentic IDEs)

An MCP server (`mcp_impact/server.py`) exposes the same core engine as four tools an agent can call mid-task — see [`docs/MCP_SETUP.md`](docs/MCP_SETUP.md). Install with `pip install -e ".[mcp]"`.

## AI explanation (optional)

```bash
pip install -e ".[ai]"          # adds python-dotenv, so .env is picked up automatically
cp .env.example .env            # then paste your key(s) into .env
```

`.env` (already created for you at the project root — just fill in one or both):

```env
GEMINI_API_KEY=...   # free key: https://aistudio.google.com/apikey
GROQ_API_KEY=...     # free key: https://console.groq.com/keys
```

`.env` is gitignored — keys never get committed. `export GEMINI_API_KEY=...` in your shell works too, if you'd rather not use a file.

```bash
ai-impact explain --diff HEAD~1                          # explains the highest-risk finding
ai-impact explain --diff HEAD~1 --symbol auth.validate_token --provider groq
```

No key set, or the request fails? `explain` still prints the deterministic evidence and exits `0` — it never fails the underlying analysis, and never fabricates prose. The model is only ever given the already-computed evidence dict and instructed never to state a fact not present in it (see `ai/explainer.py`); it cannot change a risk label or invent a caller. Same behavior on the MCP side via `explain_finding`.

## Status

Phase 1 (core engine), Phase 2 (CLI), Phase 3 (MCP server), and Phase 4 (Gemini/Groq explanation) are all implemented, tested, and verified against live providers — 14/14 automated tests passing (fixture-driven, no network calls), plus a manual end-to-end check against real Gemini and Groq API calls producing correctly-grounded explanations. Live verification inside a real Antigravity session is the next concrete step — see [`docs/MCP_SETUP.md`](docs/MCP_SETUP.md) and the plan doc for the full roadmap (editor UI is Phase 5, not started).

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md) — good first issues, the core rule (deterministic engine, LLM never decides a finding), and explicit non-goals.

## License

MIT — see [`LICENSE`](LICENSE).
