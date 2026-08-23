"""ImpactReport -> plain dict, shared by the CLI's --json mode and the MCP
server so the two interfaces can never disagree about a finding's shape
(see AI_Impact_Analyzer_PLAN.md section 5, "single source of truth")."""

from __future__ import annotations

from core.models import Finding, ImpactReport


def finding_to_dict(f: Finding) -> dict:
    return {
        "symbol": f.changed_symbol.qualified_name,
        "file": f.changed_symbol.file,
        "risk": f.risk.value,
        "evidence": f.risk_evidence,
        "affected_callers": [
            {
                "symbol": ac.symbol.qualified_name,
                "tier": ac.tier.value,
                "file": ac.call_site.file,
                "line": ac.call_site.lineno,
            }
            for ac in f.affected_callers
        ],
        "test_gaps": [g.description for g in f.test_gaps],
        "covering_tests": f.covering_tests,
    }


def report_to_dict(report: ImpactReport) -> dict:
    return {
        "diff_ref": report.diff_ref,
        "overall_risk": report.overall_risk.value,
        "findings": [finding_to_dict(f) for f in report.findings],
    }
