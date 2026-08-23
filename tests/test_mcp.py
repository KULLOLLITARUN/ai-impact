"""Integration test: MCP tools must return exactly the same data as the CLI's
--json output for the same diff. This enforces the single-source-of-truth
architecture (plan section 5) rather than just documenting it -- if a future
change makes the MCP layer compute something differently from the CLI, this
test fails.
"""

from __future__ import annotations

from core.pipeline import analyze
from core.serialize import report_to_dict
from mcp_impact.server import analyze_impact, explain_finding, get_affected_files, get_test_gaps


def test_analyze_impact_matches_cli_json_output(git_repo):
    git_repo.write("auth.py", "def validate_token(token):\n    return token == 'ok'\n")
    git_repo.write(
        "login.py",
        "from auth import validate_token\n\ndef login(token):\n    return validate_token(token)\n",
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

    cli_equivalent = report_to_dict(analyze(git_repo.path, diff_ref="HEAD~1"))
    mcp_result = analyze_impact(git_repo.path, diff_ref="HEAD~1")

    assert mcp_result == cli_equivalent


def test_get_affected_files_is_consistent_with_analyze_impact(git_repo):
    git_repo.write("auth.py", "def validate_token(token):\n    return token == 'ok'\n")
    git_repo.write(
        "login.py",
        "from auth import validate_token\n\ndef login(token):\n    return validate_token(token)\n",
    )
    git_repo.commit("base")
    git_repo.write(
        "auth.py",
        "def validate_token(token, allow_expired=False):\n    return token == 'ok'\n",
    )
    git_repo.commit("change")

    full = analyze_impact(git_repo.path, diff_ref="HEAD~1")
    affected = get_affected_files(git_repo.path, diff_ref="HEAD~1")

    expected = [
        {
            "changed_symbol": f["symbol"],
            "affected_symbol": ac["symbol"],
            "tier": ac["tier"],
            "file": ac["file"],
            "line": ac["line"],
        }
        for f in full["findings"]
        for ac in f["affected_callers"]
    ]
    assert affected == expected


def test_get_test_gaps_is_consistent_with_analyze_impact(git_repo):
    git_repo.write("billing.py", "def charge(amount):\n    return amount\n")
    git_repo.commit("base")
    git_repo.write("billing.py", "def charge(amount):\n    return amount * 1.0\n")
    git_repo.commit("change with no tests")

    full = analyze_impact(git_repo.path, diff_ref="HEAD~1")
    gaps = get_test_gaps(git_repo.path, diff_ref="HEAD~1")

    expected = [
        {"symbol": f["symbol"], "file": f["file"], "gap": g}
        for f in full["findings"]
        for g in f["test_gaps"]
    ]
    assert gaps == expected


def test_explain_finding_returns_deterministic_evidence_when_no_api_key_configured(git_repo, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    git_repo.write("billing.py", "def charge(amount):\n    return amount\n")
    git_repo.commit("base")
    git_repo.write("billing.py", "def charge(amount):\n    return amount * 1.0\n")
    git_repo.commit("change")

    result = explain_finding(git_repo.path, symbol="billing.charge", diff_ref="HEAD~1")

    assert result["symbol"] == "billing.charge"
    assert result["explanation"] is None
    assert "unavailable" in result["explanation_status"]
    # The finding's own evidence must still be present -- explanation being
    # unavailable must never hide the deterministic result.
    assert result["evidence"]["signature_changed"] is False


def test_explain_finding_unknown_symbol_returns_error(git_repo):
    git_repo.write("billing.py", "def charge(amount):\n    return amount\n")
    git_repo.commit("base")
    git_repo.write("billing.py", "def charge(amount):\n    return amount * 1.0\n")
    git_repo.commit("change")

    result = explain_finding(git_repo.path, symbol="does.not.exist", diff_ref="HEAD~1")
    assert "error" in result
