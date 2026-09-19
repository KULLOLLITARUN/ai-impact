"""Local-only web server for the Impact Workbench (ai-impact serve).

Deliberately stdlib-only (http.server), matching the core engine's
zero-required-dependency philosophy. GET / re-runs core.pipeline.analyze()
fresh on every request (so Refresh / Analyze always reflects the current
repo state) and server-renders it via ui.render.render_page -- the browser
never computes anything itself. GET /explain is the one endpoint that can
touch the network (the optional AI layer), and only when explicitly clicked.

Binds to 127.0.0.1 only -- this is a local developer tool, never meant to be
reachable off the machine, so there is no auth layer to bypass.
"""

from __future__ import annotations

import json
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from ai.explainer import ExplainerError, explain as explain_finding_text
from core.pipeline import analyze
from core.serialize import finding_to_dict
from ui.render import render_page


class _Handler(BaseHTTPRequestHandler):
    repo_path: str = "."

    def log_message(self, format: str, *args) -> None:  # noqa: A002 -- stdlib signature
        pass  # keep the terminal quiet; errors still surface via do_GET's own handling

    def address_string(self) -> str:
        # BaseHTTPRequestHandler.address_string() does socket.getfqdn(), a
        # reverse DNS lookup, on every single request to build the log line --
        # even though log_message() above discards it. On Windows this can
        # add multi-second latency per request. Skip DNS entirely; the raw
        # client IP is all a local dev server needs.
        return self.client_address[0]

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        # Strict routing: browsers auto-request /favicon.ico after every page
        # load. Without this check, that request fell through to the index
        # handler and silently triggered a full second re-analysis (another
        # git subprocess call, full pipeline run) per page load -- doubling
        # real work and perceived load time for no reason.
        if parsed.path == "/explain":
            self._handle_explain(params)
        elif parsed.path in ("/", ""):
            self._handle_index(params)
        else:
            self.send_response(404)
            self.end_headers()

    def _handle_index(self, params: dict) -> None:
        diff_ref = (params.get("diff_ref", [None])[0]) or None
        staged = params.get("staged", ["0"])[0] == "1"

        start = time.time()
        try:
            report = analyze(self.repo_path, diff_ref=diff_ref, staged=staged)
        except Exception as exc:  # noqa: BLE001 -- surface analysis errors in-page, don't crash the server
            self._send_html(f"<h1>Analysis error</h1><pre>{exc}</pre>", status=500)
            return
        elapsed = time.time() - start

        html_out = render_page(report, self.repo_path, diff_ref, staged, elapsed)
        self._send_html(html_out)

    def _handle_explain(self, params: dict) -> None:
        diff_ref = (params.get("diff_ref", [None])[0]) or None
        staged = params.get("staged", ["0"])[0] == "1"
        symbol = params.get("symbol", [None])[0]
        provider = params.get("provider", ["gemini"])[0]

        if not symbol:
            self._send_json({"error": "missing symbol"}, status=400)
            return

        try:
            report = analyze(self.repo_path, diff_ref=diff_ref, staged=staged)
        except Exception as exc:  # noqa: BLE001
            self._send_json({"error": str(exc)}, status=500)
            return

        match = next((f for f in report.findings if f.changed_symbol.qualified_name == symbol), None)
        if match is None:
            self._send_json({"error": f"no finding for symbol '{symbol}'"}, status=404)
            return

        finding_dict = finding_to_dict(match)
        try:
            prose = explain_finding_text(finding_dict, provider=provider)
            self._send_json({"explanation": prose, "explanation_status": "ok"})
        except ExplainerError as exc:
            self._send_json({"explanation": None, "explanation_status": f"unavailable: {exc}"})

    def _send_html(self, body: str, status: int = 200) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, obj: dict, status: int = 200) -> None:
        data = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(repo_path: str, diff_ref: str | None, staged: bool, port: int, open_browser: bool = True) -> None:
    _Handler.repo_path = repo_path
    server = HTTPServer(("127.0.0.1", port), _Handler)
    url = f"http://127.0.0.1:{port}/"
    if diff_ref:
        url += f"?diff_ref={diff_ref}"
    elif staged:
        url += "?staged=1"

    print(f"AI Impact Workbench running at {url}")
    print("Press Ctrl+C to stop.")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
