# Wiring AI Impact into an agentic IDE via MCP

The MCP server exposes four tools, all thin wrappers over the same deterministic core the CLI uses (see `mcp_impact/server.py`):

- `analyze_impact(repo_path, diff_ref=None, staged=False)` — full report
- `get_affected_files(repo_path, diff_ref=None, staged=False)` — just affected callers
- `get_test_gaps(repo_path, diff_ref=None, staged=False)` — just coverage gaps
- `explain_finding(repo_path, symbol, diff_ref=None, staged=False, provider="gemini")` — prose explanation (Phase 4, not yet implemented; currently returns the deterministic evidence with an explicit "unavailable" status rather than nothing)

## Install

```bash
pip install -e ".[mcp]"
```

## Run it standalone (sanity check before wiring into an IDE)

```bash
python -m mcp_impact.server
```

This starts the server on stdio and blocks, waiting for an MCP client — it won't print anything on its own. Ctrl+C to stop. Use this only to confirm the process starts without import errors; actual tool calls need a real MCP client (below).

## Antigravity

Add an MCP server entry pointing at this project's Python interpreter and the server module, e.g. (exact config file/location depends on your Antigravity version — check its MCP settings panel for the current path):

```json
{
  "mcpServers": {
    "ai-impact": {
      "command": "python",
      "args": ["-m", "mcp_impact.server"],
      "cwd": "/absolute/path/to/ai-impact"
    }
  }
}
```

Then, in a session, an agent editing a Python file in a git repo can call `analyze_impact` with that repo's path and `diff_ref="HEAD"` (or `staged=true` if it staged its own changes) before declaring a task complete.

**Status: not yet verified against a live Antigravity instance** — the tools above have only been exercised directly in Python (see `tests/test_mcp.py`) and via the standard MCP stdio transport locally. Wiring this into Antigravity itself and confirming a real agent turn calls it correctly is the next concrete step, not something this doc can claim done yet.

## Cursor / Claude Code

Same `mcpServers` JSON shape works in Cursor's `.cursor/mcp.json` and Claude Code's `claude mcp add` — verify these after Antigravity, per the plan's build order (test one host thoroughly before assuming the others behave identically; MCP is a standard protocol, but tool-calling UX differs per host).
