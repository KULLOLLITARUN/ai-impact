"""Impact Workbench v0: server-rendered HTML + a small amount of vanilla JS
for pure client-side toggling (select a finding, expand evidence, open the
Explain panel). No JS framework, no build step, no client-side analysis --
every value here comes straight from an already-computed ImpactReport. The
browser visualizes evidence; it never invents it.

Layout: findings list + changed files (left) / finding detail (right). No
permanent graph canvas -- impact relationships render as a compact chip
strip inline in the detail panel, sized to the data, not a fixed-size stage.
"""

from __future__ import annotations

import html

from core.models import Finding, ImpactReport, RiskLevel

RISK_COLOR = {
    RiskLevel.HIGH: "#DC4C3F",
    RiskLevel.MEDIUM: "#C08A2E",
    RiskLevel.LOW: "#2F9160",
}
RISK_BG = {
    RiskLevel.HIGH: "#FCEBE9",
    RiskLevel.MEDIUM: "#FBF2E4",
    RiskLevel.LOW: "#EAF6EF",
}


def _e(s: str) -> str:
    return html.escape(str(s), quote=True)


def _short_name(qualified_name: str) -> str:
    return qualified_name.rsplit(".", 1)[-1]


def _risk_color(risk: RiskLevel) -> str:
    return RISK_COLOR.get(risk, "#8A8F98")


def _impact_strip(finding: Finding) -> str:
    color = _risk_color(finding.risk)
    root = (
        f'<div class="impact-root">'
        f'<span class="chip chip-root" style="border-color:{color};color:{color}">'
        f'{_e(_short_name(finding.changed_symbol.qualified_name))}()</span>'
        f'</div>'
    )

    branches = []
    for ac in finding.affected_callers:
        tier_color = _risk_color(RiskLevel(ac.tier.value))
        branches.append(
            f'<div class="branch">'
            f'<span class="arrow">&#8594;</span>'
            f'<span class="chip" style="border-color:{tier_color};color:{tier_color}">'
            f'{_e(_short_name(ac.symbol.qualified_name))}()</span>'
            f'<span class="chip-sub">{_e(ac.call_site.file)}:{ac.call_site.lineno}</span>'
            f'</div>'
        )

    if finding.test_gaps:
        branches.append(
            f'<div class="branch"><span class="arrow">&#8594;</span>'
            f'<span class="chip chip-gap">&#10007; no test</span></div>'
        )
    elif finding.covering_tests:
        branches.append(
            f'<div class="branch"><span class="arrow">&#8594;</span>'
            f'<span class="chip chip-ok">&#10003; tested</span></div>'
        )

    if not branches:
        branches_html = '<div class="branch muted">No callers or test information found</div>'
    else:
        branches_html = "".join(branches)

    return f'<div class="impact-strip">{root}<div class="impact-branches">{branches_html}</div></div>'


def _finding_detail_html(finding: Finding, finding_id: str, active: bool) -> str:
    ev = finding.risk_evidence
    color = _risk_color(finding.risk)
    sym = finding.changed_symbol

    tags = []
    if ev.get("signature_changed"):
        tags.append("Signature changed")
    if ev.get("is_public_symbol"):
        tags.append("Public symbol")
    tags_html = "".join(f'<span class="tag">{_e(t)}</span>' for t in tags)

    why_bits = []
    if ev.get("signature_changed"):
        why_bits.append("Signature changed")
    if ev.get("caller_count", 0) > 0:
        why_bits.append(f"{ev['caller_count']} caller(s) affected")
    if ev.get("coverage_gap_count", 0) > 0:
        why_bits.append("No test coverage")
    if not why_bits:
        why_bits.append("No risk signals found")
    why_html = "".join(f"<li>{_e(b)}</li>" for b in why_bits)

    if finding.test_gaps:
        coverage_html = "".join(f'<div class="gap-line">&#9888; {_e(g.description)}</div>' for g in finding.test_gaps)
    elif finding.covering_tests:
        coverage_html = "".join(f'<div class="ok-line">&#10003; {_e(t)}</div>' for t in finding.covering_tests)
    else:
        coverage_html = '<div class="muted">No test information</div>'

    evidence_rows = "".join(
        f'<div class="ev-row"><span class="ev-key">{_e(k)}</span><span class="ev-val">{_e(v)}</span></div>'
        for k, v in ev.items()
    )

    active_cls = " active" if active else ""
    return f"""
    <div class="finding-detail{active_cls}" id="{finding_id}">
      <div class="fd-header">
        <div class="fd-title">{_e(_short_name(sym.qualified_name))}()</div>
        <span class="risk-chip" style="background:{RISK_BG[finding.risk]};color:{color}">{finding.risk.value}</span>
      </div>
      <div class="fd-location muted">{_e(sym.file)}:{sym.lineno}</div>
      <div class="fd-tags">{tags_html}</div>

      <div class="fd-section">
        <div class="section-heading">Impact</div>
        {_impact_strip(finding)}
      </div>

      <div class="fd-section">
        <div class="section-heading">Why</div>
        <ul class="why-list">{why_html}</ul>
      </div>

      <div class="fd-section">
        <div class="section-heading">Coverage</div>
        {coverage_html}
        <details class="evidence-details">
          <summary>Evidence</summary>
          <div class="evidence-box">{evidence_rows}</div>
        </details>
      </div>

      <div class="fd-actions">
        <button class="explain-btn" data-symbol="{_e(sym.qualified_name)}">Explain</button>
        <select class="provider-select">
          <option value="gemini">Gemini</option>
          <option value="groq">Groq</option>
        </select>
      </div>
      <div class="explain-panel" hidden></div>
    </div>
    """


def _findings_list_html(report: ImpactReport) -> str:
    items = []
    for i, f in enumerate(report.findings):
        active_cls = " active" if i == 0 else ""
        items.append(
            f'<button class="finding-item{active_cls}" data-finding="finding-{i}">'
            f'<span class="dot dot-{f.risk.value.lower()}"></span>'
            f'<span class="fi-symbol">{_e(_short_name(f.changed_symbol.qualified_name))}()</span>'
            f'<span class="fi-loc muted">{_e(f.changed_symbol.file)}:{f.changed_symbol.lineno}</span>'
            f'</button>'
        )
    return "".join(items) or '<div class="muted" style="padding:8px 0">No findings</div>'


def _changed_files_html(report: ImpactReport) -> str:
    files = sorted({f.changed_symbol.file for f in report.findings})
    if not files:
        return '<div class="muted">No files changed</div>'
    return "".join(f'<div class="file-row"><span class="file-M">M</span> {_e(f)}</div>' for f in files)


_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

:root {
  --bg: #FFFFFF; --bg-subtle: #FAFAFA; --text: #18181B; --muted: #71717A; --border: #EBEBEC;
  --accent: #5B5FEF; --accent-soft: #EEEEFD;
  --high: #DC4C3F; --medium: #C08A2E; --low: #2F9160;
}
* { box-sizing: border-box; }
body {
  margin: 0; font-family: 'Inter', -apple-system, "Segoe UI", sans-serif;
  background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.topbar { display: flex; align-items: center; justify-content: space-between; padding: 16px 28px; border-bottom: 1px solid var(--border); }
.brand-row { font-weight: 700; font-size: 15px; letter-spacing: -0.01em; display: flex; align-items: center; gap: 8px; }
.brand-row .logo { color: var(--accent); font-size: 16px; }
.topbar-right { color: var(--muted); font-size: 13px; }
.stat-bar { display: flex; align-items: center; gap: 24px; padding: 14px 28px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.risk-count { display: flex; align-items: center; gap: 6px; font-weight: 600; font-size: 13.5px; }
.risk-count .dot { width: 8px; height: 8px; }
.stat-sep { color: var(--muted); }
.stat-plain { color: var(--muted); font-size: 13px; }
.controls-row { display: flex; align-items: center; gap: 10px; margin-left: auto; }
.controls-row form { display: flex; align-items: center; gap: 8px; }
.controls-row label { color: var(--muted); font-size: 12.5px; display: flex; align-items: center; gap: 4px; }
.controls-row input[type=text] {
  font-size: 13px; padding: 6px 10px; border: 1px solid var(--border); border-radius: 7px;
  width: 110px; font-family: inherit; background: var(--bg-subtle);
}
.controls-row input[type=text]:focus { outline: none; border-color: var(--accent); background: var(--bg); }
.controls-row button, .controls-row a.btn {
  font-size: 12.5px; font-weight: 600; padding: 6px 13px; border: 1px solid var(--border);
  border-radius: 7px; background: var(--bg); cursor: pointer; text-decoration: none;
  color: var(--text); font-family: inherit;
}
.controls-row button:hover, .controls-row a.btn:hover { border-color: var(--accent); color: var(--accent); }
.layout { display: grid; grid-template-columns: 260px 1fr; min-height: calc(100vh - 130px); }
.sidebar { border-right: 1px solid var(--border); padding: 20px; }
.side-heading { font-size: 10.5px; font-weight: 700; letter-spacing: 0.07em; color: var(--muted); text-transform: uppercase; margin: 0 0 8px; }
.side-heading:not(:first-child) { margin-top: 24px; }
.finding-item {
  display: flex; align-items: center; gap: 8px; width: 100%; text-align: left; padding: 8px 10px;
  margin: 0 -10px 2px; border: none; background: none; border-radius: 7px; cursor: pointer;
  font-family: inherit; font-size: 13px;
}
.finding-item:hover { background: var(--bg-subtle); }
.finding-item.active { background: var(--accent-soft); }
.fi-symbol { font-weight: 600; }
.fi-loc { margin-left: auto; font-size: 11.5px; }
.file-row { font-size: 13px; padding: 4px 0; }
.file-M { color: var(--medium); font-weight: 700; font-size: 11px; margin-right: 4px; }
.dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.dot-high { background: var(--high); }
.dot-medium { background: var(--medium); }
.dot-low { background: var(--low); }
.muted { color: var(--muted); font-size: 13px; }
.main { padding: 28px 36px; max-width: 720px; }
.finding-detail { display: none; }
.finding-detail.active { display: block; }
.fd-header { display: flex; align-items: center; gap: 12px; }
.fd-title { font-size: 20px; font-weight: 700; letter-spacing: -0.01em; }
.risk-chip { font-size: 11px; font-weight: 700; letter-spacing: 0.02em; padding: 4px 10px; border-radius: 6px; }
.fd-location { margin-top: 4px; }
.fd-tags { display: flex; gap: 6px; margin-top: 10px; }
.tag { font-size: 12px; color: var(--muted); background: var(--bg-subtle); padding: 4px 10px; border-radius: 6px; }
.fd-section { margin-top: 26px; }
.section-heading { font-size: 11px; font-weight: 700; letter-spacing: 0.07em; color: var(--muted); text-transform: uppercase; margin-bottom: 10px; }
.impact-strip { display: flex; align-items: center; gap: 18px; padding: 14px 16px; background: var(--bg-subtle); border-radius: 10px; flex-wrap: wrap; }
.impact-root { flex-shrink: 0; }
.impact-branches { display: flex; flex-direction: column; gap: 8px; }
.branch { display: flex; align-items: center; gap: 8px; }
.arrow { color: var(--muted); font-size: 14px; }
.chip {
  font-size: 13px; font-weight: 600; padding: 5px 12px; border-radius: 7px; border: 1.5px solid;
  background: var(--bg); white-space: nowrap;
}
.chip-root { font-size: 14px; }
.chip-gap { color: var(--medium); border-color: var(--medium); background: #FBF2E4; }
.chip-ok { color: var(--low); border-color: var(--low); background: #EAF6EF; }
.chip-sub { font-size: 11.5px; color: var(--muted); }
.why-list { list-style: none; margin: 0; padding: 0; }
.why-list li { font-size: 13.5px; padding: 3px 0; }
.gap-line { color: var(--medium); background: #FBF2E4; font-size: 12.5px; padding: 7px 10px; border-radius: 6px; display: inline-block; }
.ok-line { color: var(--low); background: #EAF6EF; font-size: 12.5px; padding: 7px 10px; border-radius: 6px; display: inline-block; }
.evidence-details { margin-top: 12px; }
.evidence-details summary { cursor: pointer; font-size: 12.5px; color: var(--muted); font-weight: 500; }
.evidence-details summary:hover { color: var(--text); }
.evidence-box { margin-top: 8px; font-family: 'JetBrains Mono', ui-monospace, monospace; font-size: 11.5px; background: var(--bg-subtle); border-radius: 8px; padding: 12px; }
.ev-row { display: flex; justify-content: space-between; padding: 2px 0; }
.ev-key { color: var(--muted); }
.fd-actions { display: flex; align-items: center; gap: 10px; margin-top: 26px; }
.explain-btn {
  background: var(--accent); color: #fff; border: none; padding: 9px 18px; border-radius: 8px;
  cursor: pointer; font-size: 13px; font-weight: 600; font-family: inherit;
}
.explain-btn:hover { background: #4A4DD9; }
.provider-select {
  font-size: 12.5px; padding: 8px 10px; border-radius: 8px; border: 1px solid var(--border);
  background: var(--bg); font-family: inherit; color: var(--muted);
}
.explain-panel { margin-top: 14px; padding: 16px; background: var(--accent-soft); border-radius: 10px; font-size: 13.5px; line-height: 1.6; }
.footer { display: flex; justify-content: space-between; padding: 12px 28px; border-top: 1px solid var(--border); color: var(--muted); font-size: 12.5px; }
.empty-state { text-align: center; color: var(--muted); padding: 100px 20px; font-size: 14px; grid-column: 1 / -1; }
"""

_JS = """
document.querySelectorAll('.finding-item').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.finding-item').forEach(b => b.classList.toggle('active', b === btn));
    document.querySelectorAll('.finding-detail').forEach(d => d.classList.toggle('active', d.id === btn.dataset.finding));
  });
});

document.querySelectorAll('.explain-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    const symbol = btn.dataset.symbol;
    const provider = btn.parentElement.querySelector('.provider-select').value.toLowerCase();
    const panel = btn.closest('.finding-detail').querySelector('.explain-panel');
    panel.hidden = false;
    panel.textContent = 'Asking ' + provider + '...';
    const params = new URLSearchParams(window.location.search);
    params.set('symbol', symbol);
    params.set('provider', provider);
    try {
      const res = await fetch('/explain?' + params.toString());
      const data = await res.json();
      panel.textContent = data.explanation || data.explanation_status || 'No explanation available.';
    } catch (e) {
      panel.textContent = 'Request failed: ' + e;
    }
  });
});
"""


def render_page(report: ImpactReport, repo_path: str, diff_ref: str | None, staged: bool, elapsed_seconds: float) -> str:
    diff_label = "staged" if staged else (diff_ref or "HEAD")
    n_files = len({f.changed_symbol.file for f in report.findings})
    n_symbols = len(report.findings)
    n_gaps = sum(len(f.test_gaps) for f in report.findings)

    counts = {RiskLevel.HIGH: 0, RiskLevel.MEDIUM: 0, RiskLevel.LOW: 0}
    for f in report.findings:
        counts[f.risk] = counts.get(f.risk, 0) + 1

    risk_counts_html = "".join(
        f'<div class="risk-count"><span class="dot dot-{r.value.lower()}"></span>{counts[r]} {r.value}</div>'
        for r in (RiskLevel.HIGH, RiskLevel.MEDIUM, RiskLevel.LOW)
    )

    if not report.findings:
        body = '<div class="empty-state">No changed symbols detected.<br>Nothing to report.</div>'
    else:
        detail_panels = "".join(
            _finding_detail_html(f, f"finding-{i}", active=(i == 0)) for i, f in enumerate(report.findings)
        )
        body = f"""
        <div class="sidebar">
          <div class="side-heading">Findings</div>
          {_findings_list_html(report)}
          <div class="side-heading">Changed files</div>
          {_changed_files_html(report)}
        </div>
        <div class="main">{detail_panels}</div>
        """

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>AI Impact</title>
<style>{_CSS}</style>
</head>
<body>
  <div class="topbar">
    <div class="brand-row"><span class="logo">&#9670;</span> AI IMPACT</div>
    <div class="topbar-right">{_e(repo_path)} &middot; {_e(diff_label)}</div>
  </div>
  <div class="stat-bar">
    {risk_counts_html}
    <span class="stat-sep">|</span>
    <span class="stat-plain">{n_files} file{'s' if n_files != 1 else ''} &middot; {n_symbols} symbol{'s' if n_symbols != 1 else ''} &middot; {n_gaps} test gap{'s' if n_gaps != 1 else ''}</span>
    <div class="controls-row">
      <form method="get">
        <input type="text" name="diff_ref" placeholder="HEAD~1" value="{_e(diff_ref or '')}">
        <label><input type="checkbox" name="staged" value="1" {"checked" if staged else ""}> staged</label>
        <button type="submit">Analyze</button>
      </form>
      <a class="btn" href="?diff_ref={_e(diff_ref or '')}{'&staged=1' if staged else ''}">Refresh</a>
    </div>
  </div>
  <div class="layout">{body}</div>
  <div class="footer">
    <span>AI Impact Workbench</span>
    <span>Analyzed in {elapsed_seconds:.2f}s</span>
  </div>
  <script>{_JS}</script>
</body>
</html>"""
