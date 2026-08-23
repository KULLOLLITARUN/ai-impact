"""Regression test for a real deadlock: calling analyze_impact (or any tool
that shells out to `git`) over the actual MCP stdio protocol used to hang
forever on Windows.

Root cause: subprocess.run(["git", ...]) in core/diff.py and
core/blast_radius.py didn't redirect stdin, so the child process inherited
the parent's real stdin handle. Under a stdio-transport MCP server, that
handle *is* the live JSON-RPC pipe -- letting `git` inherit it deadlocked the
connection. Calling the tool functions directly in Python (as test_mcp.py
does) never exercised this, because there's no live stdio pipe as stdin in
that case -- only spawning the server as a real subprocess and driving it
over stdio (as a real MCP client, e.g. Antigravity, would) reproduces it.

Fixed by passing stdin=subprocess.DEVNULL on both git subprocess calls.
"""

from __future__ import annotations

import asyncio
import sys

import pytest

mcp_client = pytest.importorskip("mcp", reason="mcp extra not installed (pip install -e '.[mcp]')")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402


async def _call_analyze_impact_over_stdio(repo_path: str, diff_ref: str) -> dict:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_impact.server"],
        cwd=".",
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "analyze_impact", {"repo_path": repo_path, "diff_ref": diff_ref}
            )
            return result


def test_analyze_impact_responds_over_real_mcp_stdio_protocol(git_repo):
    """Must complete quickly -- this test itself times out (via asyncio.wait_for)
    rather than hanging the suite if the deadlock regresses."""
    git_repo.write("m.py", "def f(x):\n    return x\n")
    git_repo.commit("base")
    git_repo.write("m.py", "def f(x, y=1):\n    return x + y\n")
    git_repo.commit("change")

    async def run_with_timeout():
        return await asyncio.wait_for(
            _call_analyze_impact_over_stdio(git_repo.path, "HEAD~1"), timeout=15
        )

    try:
        result = asyncio.run(run_with_timeout())
    except asyncio.TimeoutError:
        pytest.fail(
            "analyze_impact did not respond within 15s over real MCP stdio -- "
            "likely the git-subprocess-stdin-inheritance deadlock has regressed "
            "(see module docstring)."
        )

    assert result.isError is False
    assert '"signature_changed": true' in result.content[0].text
