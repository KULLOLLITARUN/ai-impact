"""Phase 4: optional LLM explanation layer.

Strict boundary (see AI_Impact_Analyzer_PLAN.md section 12): the model is
handed the already-computed, evidence-grounded finding dict and asked only
to phrase it for a human. It is explicitly instructed never to state a fact,
number, or file/line reference that isn't present in the evidence it was
given. This module never feeds the model raw source code or the repository
-- only the structured output of the deterministic core.

Uses stdlib `urllib.request` only, so the explainer adds zero required
dependencies -- it activates purely based on whether an API key env var is
set, and is entirely optional (see core.pipeline / cli / mcp_impact, none of
which import this module).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

try:
    from dotenv import load_dotenv

    load_dotenv()  # loads a .env file from the current/parent directory if present; no-op if absent
except ImportError:
    pass  # python-dotenv is optional -- plain `export`/OS env vars still work without it

GEMINI_MODEL = "gemini-3.6-flash"
GROQ_MODEL = "openai/gpt-oss-120b"

GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

_SYSTEM_INSTRUCTION = (
    "You are explaining a code-change risk finding to a developer. "
    "You are given a JSON object that is the complete, authoritative evidence -- "
    "produced by a deterministic static-analysis tool, not by you. "
    "Rules:\n"
    "1. Only state facts, numbers, file paths, and line numbers that appear in the JSON.\n"
    "2. Never invent a caller, a test, a risk factor, or a dollar/percentage figure not present.\n"
    "3. If the evidence is thin (e.g. no affected callers), say so plainly rather than padding the answer.\n"
    "4. Write 3-6 sentences, plain language, aimed at a developer deciding whether to review this change more closely.\n"
    "5. End with one concrete suggestion for what to check first, grounded only in the given evidence."
)


class ExplainerError(Exception):
    """Raised for any failure in the optional explanation layer. Callers should
    treat this as 'explanation unavailable', never as a reason to fail the
    underlying (already-complete) deterministic analysis."""


class MissingAPIKeyError(ExplainerError):
    pass


def build_prompt(finding: dict) -> str:
    return f"{_SYSTEM_INSTRUCTION}\n\nEvidence:\n{json.dumps(finding, indent=2)}"


def _post_json(url: str, headers: dict, body: dict, timeout: int = 20) -> dict:
    # Never include the request URL/headers in an error message -- a key
    # passed as a query param or header must not end up echoed to a terminal,
    # a log, or (in the MCP path) back to an agent's context.
    safe_url = url.split("?", 1)[0]
    data = json.dumps(body).encode("utf-8")
    default_headers = {
        "Content-Type": "application/json",
        # Some providers front their API with Cloudflare, which can reject
        # urllib's default "Python-urllib/x.y" user-agent string outright.
        "User-Agent": "ai-impact/0.1 (+https://github.com/ai-impact)",
    }
    req = urllib.request.Request(url, data=data, headers={**default_headers, **headers})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ExplainerError(f"{safe_url} returned HTTP {exc.code}: {detail[:300]}") from exc
    except urllib.error.URLError as exc:
        raise ExplainerError(f"could not reach {safe_url}: {exc.reason}") from exc


def _explain_with_gemini(prompt: str) -> str:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise MissingAPIKeyError("GEMINI_API_KEY (or GOOGLE_API_KEY) is not set")

    body = {"contents": [{"parts": [{"text": prompt}]}]}
    result = _post_json(GEMINI_URL, headers={"x-goog-api-key": api_key}, body=body)
    try:
        return result["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError) as exc:
        raise ExplainerError(f"unexpected Gemini response shape: {result}") from exc


def _explain_with_groq(prompt: str) -> str:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise MissingAPIKeyError("GROQ_API_KEY is not set")

    body = {
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    result = _post_json(GROQ_URL, headers={"Authorization": f"Bearer {api_key}"}, body=body)
    try:
        return result["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError) as exc:
        raise ExplainerError(f"unexpected Groq response shape: {result}") from exc


_PROVIDERS = {
    "gemini": _explain_with_gemini,
    "groq": _explain_with_groq,
}


def explain(finding: dict, provider: str = "gemini") -> str:
    if provider not in _PROVIDERS:
        raise ExplainerError(f"unknown provider '{provider}', expected one of {list(_PROVIDERS)}")
    prompt = build_prompt(finding)
    return _PROVIDERS[provider](prompt)
