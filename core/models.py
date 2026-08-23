"""Shared data model for the AI Impact core engine.

Every stage of the pipeline (diff -> ast_index -> graph -> blast_radius ->
test_mapping -> risk) reads and writes these types. The CLI and MCP server
both format `ImpactReport`, they never construct their own version of it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CallerTier(str, Enum):
    HIGH = "HIGH"      # direct caller
    MEDIUM = "MEDIUM"  # 2 hops
    LOW = "LOW"        # 3 hops


@dataclass(frozen=True)
class Symbol:
    """A function, method, or class defined in the repo."""

    qualified_name: str   # e.g. "src.auth.AuthService.validate_token"
    file: str              # repo-relative path
    lineno: int
    end_lineno: int
    kind: str               # "function" | "method" | "class"

    def __hash__(self) -> int:
        return hash((self.qualified_name, self.file))


@dataclass(frozen=True)
class CallSite:
    """A specific place where one symbol calls another."""

    caller: Symbol
    callee: Symbol
    file: str
    lineno: int


@dataclass
class ChangedSymbol:
    symbol: Symbol
    signature_changed: bool
    changed_lines: int


@dataclass
class AffectedCaller:
    symbol: Symbol
    tier: CallerTier
    call_site: CallSite
    dependency_depth: int   # hops from the changed symbol


@dataclass
class TestGap:
    changed_symbol: Symbol
    description: str        # e.g. "No test found" or "Branch at line 42 not covered"


@dataclass
class Finding:
    changed_symbol: Symbol
    affected_callers: list[AffectedCaller] = field(default_factory=list)
    test_gaps: list[TestGap] = field(default_factory=list)
    covering_tests: list[str] = field(default_factory=list)  # qualified test names
    risk: RiskLevel = RiskLevel.LOW
    risk_evidence: dict = field(default_factory=dict)


@dataclass
class ImpactReport:
    diff_ref: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def overall_risk(self) -> RiskLevel:
        if any(f.risk == RiskLevel.HIGH for f in self.findings):
            return RiskLevel.HIGH
        if any(f.risk == RiskLevel.MEDIUM for f in self.findings):
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
