"""Orchestrates the full pipeline: diff -> ... -> ImpactReport.

This is the one function the CLI and MCP server both call -- the single
source of truth referenced throughout the plan (section 5).
"""

from __future__ import annotations

from core import blast_radius, risk, test_mapping
from core.diff import get_changed_files
from core.graph import build_call_graph, build_repo_index
from core.models import Finding, ImpactReport


def analyze(repo_path: str, diff_ref: str | None = None, staged: bool = False) -> ImpactReport:
    file_diffs = get_changed_files(repo_path, diff_ref=diff_ref, staged=staged)
    repo_index = build_repo_index(repo_path)
    call_graph = build_call_graph(repo_index)

    changed_symbols = blast_radius.detect_changed_symbols(
        repo_path, repo_index, file_diffs, diff_ref, staged=staged
    )
    radius = blast_radius.compute_blast_radius(call_graph, changed_symbols)

    findings: list[Finding] = []
    for cs in changed_symbols:
        affected_callers = radius.get(cs.symbol.qualified_name, [])

        covering_tests = test_mapping.find_covering_tests(call_graph, repo_index, cs.symbol)
        gap = test_mapping.find_test_gap(cs.symbol, covering_tests)
        test_gaps = [gap] if gap else []

        risk_level, evidence = risk.score(cs, affected_callers, test_gaps)

        findings.append(
            Finding(
                changed_symbol=cs.symbol,
                affected_callers=affected_callers,
                test_gaps=test_gaps,
                covering_tests=covering_tests,
                risk=risk_level,
                risk_evidence=evidence,
            )
        )

    label = diff_ref or ("staged" if staged else "HEAD")
    return ImpactReport(diff_ref=label, findings=findings)
