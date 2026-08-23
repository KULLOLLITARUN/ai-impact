"""Creates a small, real git repo with a HIGH-risk change to try ai-impact
against immediately -- no need to hand-craft a test case yourself.

Usage:
    python examples/setup_demo_repo.py [target_dir]   # default: ./demo-repo

Then:
    ai-impact analyze --repo <target_dir> --diff HEAD~1
    ai-impact explain  --repo <target_dir> --diff HEAD~1

What it sets up: auth.py::validate_token gets a new parameter (a signature
change) between commit 1 and commit 2, and login.py calls it without a
matching test -- ai-impact should report HIGH risk, one affected caller
(login.login), and one test-coverage gap.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(args: list[str], cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def main() -> None:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("demo-repo")
    if target.exists():
        print(f"{target} already exists -- remove it first or pass a different path.")
        raise SystemExit(1)

    target.mkdir(parents=True)
    _run(["git", "init", "-q"], target)
    _run(["git", "config", "user.email", "demo@example.com"], target)
    _run(["git", "config", "user.name", "Demo"], target)

    (target / "auth.py").write_text('def validate_token(token):\n    return token == "ok"\n')
    (target / "login.py").write_text(
        "from auth import validate_token\n\ndef login(token):\n    return validate_token(token)\n"
    )
    _run(["git", "add", "-A"], target)
    _run(["git", "commit", "-q", "-m", "base: add auth and login"], target)

    (target / "auth.py").write_text(
        'def validate_token(token, allow_expired=False):\n'
        '    if allow_expired:\n'
        '        return True\n'
        '    return token == "ok"\n'
    )
    _run(["git", "commit", "-q", "-am", "change auth signature (no test added)"], target)

    print(f"Demo repo created at {target.resolve()}")
    print(f"Try: ai-impact analyze --repo {target} --diff HEAD~1")


if __name__ == "__main__":
    main()
