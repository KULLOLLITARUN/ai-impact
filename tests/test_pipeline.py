"""End-to-end fixture tests: diff -> ... -> ImpactReport, for the four
required v0 scenarios from AI_Impact_Analyzer_PLAN.md section 19.
"""

from __future__ import annotations

import subprocess

from core.models import RiskLevel
from core.pipeline import analyze


def test_signature_change_with_untested_caller_is_high_risk(git_repo):
    git_repo.write(
        "auth.py",
        "def validate_token(token):\n"
        "    return token == 'ok'\n",
    )
    git_repo.write(
        "login.py",
        "from auth import validate_token\n\n"
        "def login(token):\n"
        "    return validate_token(token)\n",
    )
    git_repo.commit("base")

    git_repo.write(
        "auth.py",
        "def validate_token(token, allow_expired=False):\n"
        "    if allow_expired:\n"
        "        return True\n"
        "    return token == 'ok'\n",
    )
    git_repo.commit("signature change")

    report = analyze(git_repo.path, diff_ref="HEAD~1")

    finding = next(f for f in report.findings if f.changed_symbol.qualified_name.endswith("validate_token"))
    assert finding.risk_evidence["signature_changed"] is True
    assert finding.risk == RiskLevel.HIGH


def test_body_only_change_with_test_coverage_is_low_risk(git_repo):
    git_repo.write(
        "greeter.py",
        "def greet(name):\n"
        "    return 'hi ' + name\n",
    )
    git_repo.write(
        "test_greeter.py",
        "from greeter import greet\n\n"
        "def test_greet():\n"
        "    assert greet('a') == 'hi a'\n",
    )
    git_repo.commit("base")

    git_repo.write(
        "greeter.py",
        "def greet(name):\n"
        "    return 'hello ' + name\n",
    )
    git_repo.commit("body only change")

    report = analyze(git_repo.path, diff_ref="HEAD~1")

    finding = next(f for f in report.findings if f.changed_symbol.qualified_name.endswith("greet"))
    assert finding.risk_evidence["signature_changed"] is False
    assert finding.covering_tests, "expected the test to be found as covering `greet`"
    assert finding.risk == RiskLevel.LOW


def test_harmless_local_rename_produces_no_findings(git_repo):
    git_repo.write(
        "calc.py",
        "def add(a, b):\n"
        "    total = a + b\n"
        "    return total\n",
    )
    git_repo.commit("base")

    git_repo.write(
        "calc.py",
        "def add(a, b):\n"
        "    result = a + b\n"
        "    return result\n",
    )
    git_repo.commit("rename local var")

    report = analyze(git_repo.path, diff_ref="HEAD~1")

    for f in report.findings:
        assert f.risk == RiskLevel.LOW
    assert report.overall_risk == RiskLevel.LOW


def test_changed_function_with_zero_coverage_reports_gap(git_repo):
    git_repo.write(
        "billing.py",
        "def charge(amount):\n"
        "    return amount\n",
    )
    git_repo.commit("base")

    git_repo.write(
        "billing.py",
        "def charge(amount):\n"
        "    return amount * 1.0\n",
    )
    git_repo.commit("change with no tests")

    report = analyze(git_repo.path, diff_ref="HEAD~1")

    finding = next(f for f in report.findings if f.changed_symbol.qualified_name.endswith("charge"))
    assert len(finding.test_gaps) == 1
    assert finding.covering_tests == []


def test_staged_mode_analyzes_uncommitted_index_changes(git_repo):
    git_repo.write(
        "auth.py",
        "def validate_token(token):\n"
        "    return token == 'ok'\n",
    )
    git_repo.write(
        "login.py",
        "from auth import validate_token\n\n"
        "def login(token):\n"
        "    return validate_token(token)\n",
    )
    git_repo.commit("base")

    # Modify and stage, but do NOT commit -- this is the case `--staged` exists for.
    git_repo.write(
        "auth.py",
        "def validate_token(token, allow_expired=False):\n"
        "    if allow_expired:\n"
        "        return True\n"
        "    return token == 'ok'\n",
    )
    subprocess.run(["git", "add", "-A"], cwd=git_repo.path, check=True, capture_output=True)

    report = analyze(git_repo.path, staged=True)

    finding = next(f for f in report.findings if f.changed_symbol.qualified_name.endswith("validate_token"))
    assert finding.risk_evidence["signature_changed"] is True
    assert finding.risk == RiskLevel.HIGH
    assert any(ac.symbol.qualified_name.endswith("login") for ac in finding.affected_callers)
