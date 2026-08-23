"""Fixture-repo helpers: build a tiny real git repo per test case, per plan
section 19 ("fixture-driven, not just unit tests of individual functions").
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)

    class Repo:
        path = str(repo)

        def write(self, rel_path: str, content: str) -> None:
            file_path = repo / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")

        def commit(self, message: str) -> None:
            _run(["git", "add", "-A"], repo)
            _run(["git", "commit", "-q", "-m", message], repo)

    return Repo()
