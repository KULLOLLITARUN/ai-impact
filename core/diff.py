"""Git diff parsing: turn a git ref/staged diff into changed line ranges per file."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ChangedRange:
    start: int
    end: int  # inclusive


@dataclass(frozen=True)
class FileDiff:
    path: str
    changed_ranges: list[ChangedRange]


_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _run_git_diff(repo_path: str, diff_ref: str | None, staged: bool) -> str:
    args = ["git", "-C", repo_path, "diff", "--unified=0"]
    if staged:
        args.append("--staged")
    elif diff_ref:
        args.append(diff_ref)
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout


def parse_unified_diff(diff_text: str) -> list[FileDiff]:
    """Parse `git diff --unified=0` output into per-file changed line ranges.

    Only additions/modifications on the "new" side of the diff are tracked --
    that is what maps back onto the current AST of each changed file.
    """
    file_diffs: list[FileDiff] = []
    current_path: str | None = None
    current_ranges: list[ChangedRange] = []

    def flush() -> None:
        if current_path is not None and current_ranges:
            file_diffs.append(FileDiff(path=current_path, changed_ranges=list(current_ranges)))

    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            flush()
            current_ranges = []
            raw = line[4:].strip()
            current_path = None if raw == "/dev/null" else raw.removeprefix("b/")
            continue

        match = _HUNK_HEADER.match(line)
        if match and current_path is not None:
            start = int(match.group(1))
            count = int(match.group(2)) if match.group(2) is not None else 1
            if count == 0:
                # Pure deletion on the new side -- nothing to map onto the new AST.
                continue
            current_ranges.append(ChangedRange(start=start, end=start + count - 1))

    flush()
    return [fd for fd in file_diffs if fd.path.endswith(".py")]


def get_changed_files(repo_path: str, diff_ref: str | None = None, staged: bool = False) -> list[FileDiff]:
    diff_text = _run_git_diff(repo_path, diff_ref, staged)
    return parse_unified_diff(diff_text)
