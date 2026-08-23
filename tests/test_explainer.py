"""Unit tests for the optional explanation layer -- no network calls, no
API key required. These test the guardrails (prompt grounding, missing-key
behavior), not actual model output, since that's inherently non-deterministic
and requires a real key."""

from __future__ import annotations

import pytest

from ai.explainer import ExplainerError, MissingAPIKeyError, build_prompt, explain


def test_build_prompt_embeds_the_full_evidence_verbatim():
    finding = {"symbol": "auth.validate_token", "risk": "HIGH", "evidence": {"caller_count": 3}}
    prompt = build_prompt(finding)

    assert "auth.validate_token" in prompt
    assert '"caller_count": 3' in prompt
    assert "Only state facts" in prompt  # the grounding instruction must be present


def test_explain_raises_missing_key_error_when_gemini_key_absent(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    with pytest.raises(MissingAPIKeyError):
        explain({"symbol": "x"}, provider="gemini")


def test_explain_raises_missing_key_error_when_groq_key_absent(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    with pytest.raises(MissingAPIKeyError):
        explain({"symbol": "x"}, provider="groq")


def test_explain_rejects_unknown_provider():
    with pytest.raises(ExplainerError):
        explain({"symbol": "x"}, provider="not-a-real-provider")
