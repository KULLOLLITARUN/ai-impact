"""ai-impact CLI: thin adapter over core.pipeline.analyze -- no analysis logic here."""

from __future__ import annotations

import argparse
import json
import sys

from core.models import ImpactReport, RiskLevel
from core.pipeline import analyze
from core.serialize import finding_to_dict, report_to_dict

_EXIT_BY_RISK = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}


def _render_text(report: ImpactReport) -> str:
    if not report.findings:
        return "AI IMPACT ANALYSIS\n" + "-" * 36 + "\n\nNo changed symbols detected. Nothing to report.\n"

    lines = ["AI IMPACT ANALYSIS", "-" * 36, ""]
    for finding in report.findings:
        sym = finding.changed_symbol
        lines.append(f"Changed:")
        lines.append(f"  {sym.file}")
        lines.append(f"    └── {sym.qualified_name}")
        if finding.risk_evidence.get("signature_changed"):
            lines.append("        ⚠ signature changed")
        lines.append("")

        if finding.affected_callers:
            lines.append("Affected callers:")
            for ac in sorted(finding.affected_callers, key=lambda a: a.dependency_depth):
                lines.append(f"  {ac.tier.value:<6}  {ac.call_site.file}:{ac.call_site.lineno}")
            lines.append("")

        if finding.covering_tests:
            lines.append("Tests:")
            for t in finding.covering_tests:
                lines.append(f"  ✓ {t}")
        for gap in finding.test_gaps:
            lines.append(f"  ⚠ {gap.description}")
        lines.append("")

        lines.append(f"Risk: {finding.risk.value}")
        lines.append(f"  Evidence: {finding.risk_evidence}")
        lines.append("")

    lines.append(f"Overall risk: {report.overall_risk.value}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to a legacy codepage that can't encode the
    # unicode markers (✓/⚠/└──) used in the text report; force UTF-8 output
    # cross-platform rather than downgrading the report to plain ASCII.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="ai-impact")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze_cmd = sub.add_parser("analyze", help="Analyze the impact of a code change")
    analyze_cmd.add_argument("--diff", dest="diff_ref", default=None, help="git ref to diff against, e.g. HEAD~1")
    analyze_cmd.add_argument("--staged", action="store_true", help="analyze staged changes instead of a ref")
    analyze_cmd.add_argument("--repo", default=".", help="path to the git repo (default: current directory)")
    analyze_cmd.add_argument("--json", action="store_true", help="emit machine-readable JSON instead of text")

    explain_cmd = sub.add_parser(
        "explain", help="Plain-language explanation of one finding (optional, needs an API key)"
    )
    explain_cmd.add_argument("--diff", dest="diff_ref", default=None, help="git ref to diff against, e.g. HEAD~1")
    explain_cmd.add_argument("--staged", action="store_true", help="analyze staged changes instead of a ref")
    explain_cmd.add_argument("--repo", default=".", help="path to the git repo (default: current directory)")
    explain_cmd.add_argument(
        "--symbol", default=None, help="qualified symbol name to explain (default: highest-risk finding)"
    )
    explain_cmd.add_argument("--provider", choices=["gemini", "groq"], default="gemini")

    args = parser.parse_args(argv)

    if args.command == "analyze":
        try:
            report = analyze(args.repo, diff_ref=args.diff_ref, staged=args.staged)
        except Exception as exc:  # noqa: BLE001 -- top-level CLI boundary
            print(f"Analysis error: {exc}", file=sys.stderr)
            return 3

        if args.json:
            print(json.dumps(report_to_dict(report), indent=2))
        else:
            print(_render_text(report))

        return _EXIT_BY_RISK[report.overall_risk]

    if args.command == "explain":
        try:
            report = analyze(args.repo, diff_ref=args.diff_ref, staged=args.staged)
        except Exception as exc:  # noqa: BLE001
            print(f"Analysis error: {exc}", file=sys.stderr)
            return 3

        if not report.findings:
            print("No findings to explain.")
            return 0

        if args.symbol:
            match = next(
                (f for f in report.findings if f.changed_symbol.qualified_name == args.symbol), None
            )
            if match is None:
                print(f"No finding for symbol '{args.symbol}' in this diff.", file=sys.stderr)
                return 3
        else:
            # Default: explain the single highest-risk finding.
            risk_order = {RiskLevel.HIGH: 2, RiskLevel.MEDIUM: 1, RiskLevel.LOW: 0}
            match = max(report.findings, key=lambda f: risk_order[f.risk])

        finding_dict = finding_to_dict(match)
        print(f"Symbol: {match.changed_symbol.qualified_name}")
        print(f"Risk:   {match.risk.value}")
        print()

        from ai.explainer import ExplainerError, explain as explain_finding

        try:
            prose = explain_finding(finding_dict, provider=args.provider)
        except ExplainerError as exc:
            print(f"[explanation unavailable via {args.provider}: {exc}]", file=sys.stderr)
            print()
            print("Deterministic evidence (still authoritative):")
            print(json.dumps(finding_dict["evidence"], indent=2))
            return 0

        print(prose)
        return 0

    return 3


if __name__ == "__main__":
    raise SystemExit(main())
