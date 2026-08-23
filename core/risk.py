"""Deterministic risk scoring: evidence in, a HIGH/MEDIUM/LOW label out.

No weighted numeric score is exposed -- see plan section 11. `risk_evidence`
carries every factor that fed the label so a developer (or the optional LLM
explainer) can see exactly why, never a bare unexplained label.
"""

from __future__ import annotations

from core.models import AffectedCaller, CallerTier, ChangedSymbol, RiskLevel, TestGap


def score(
    changed: ChangedSymbol,
    affected_callers: list[AffectedCaller],
    test_gaps: list[TestGap],
) -> tuple[RiskLevel, dict]:
    caller_count = len(affected_callers)
    high_tier_callers = sum(1 for ac in affected_callers if ac.tier == CallerTier.HIGH)
    max_depth = max((ac.dependency_depth for ac in affected_callers), default=0)
    has_gap = len(test_gaps) > 0
    is_public = not changed.symbol.qualified_name.rsplit(".", 1)[-1].startswith("_")

    evidence = {
        "signature_changed": changed.signature_changed,
        "changed_lines": changed.changed_lines,
        "caller_count": caller_count,
        "high_tier_caller_count": high_tier_callers,
        "dependency_depth": max_depth,
        "coverage_gap_count": len(test_gaps),
        "is_public_symbol": is_public,
    }

    # HIGH: a breaking-shaped change with real, known blast radius.
    if changed.signature_changed and high_tier_callers > 0:
        return RiskLevel.HIGH, evidence
    if changed.signature_changed and has_gap:
        return RiskLevel.HIGH, evidence
    if has_gap and caller_count > 0:
        return RiskLevel.HIGH, evidence

    # MEDIUM: a real signal (breaking-shaped change or a direct dependent),
    # but not confirmed to combine with an actual untested blast radius yet.
    if changed.signature_changed or high_tier_callers > 0:
        return RiskLevel.MEDIUM, evidence

    # LOW: either has known callers but nothing else flagged, or is a fully
    # isolated change (no callers, no signature change) -- e.g. a local
    # variable rename with no observable external effect. Note: a symbol
    # with zero known callers is deliberately NOT escalated for lacking a
    # test in v0 -- with no confirmed blast radius, that's noise, not signal.
    return RiskLevel.LOW, evidence
