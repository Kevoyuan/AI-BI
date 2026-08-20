"""Vercel entry point for the protected bakery dashboard."""

from __future__ import annotations

import base64
import hmac
import os

# Vercel's filesystem is read-only outside /tmp. Keep the report cache usable
# for warm function instances without attempting to write into the deployment.
os.environ.setdefault("POSPAL_REPORT_CACHE_DIR", "/tmp/pospal-months")

from web_dashboard_server import DashboardHandler


class handler(DashboardHandler):
    """Serve the dashboard only after HTTP Basic authentication."""

    def _authenticate(self) -> bool:
        username = os.environ.get("DASHBOARD_AUTH_USER")
        password = os.environ.get("DASHBOARD_AUTH_PASSWORD")
        if not username or not password:
            self._send_json(
                {"error": "Dashboard authentication is not configured"},
                status=503,
            )
            return False

        expected = "Basic " + base64.b64encode(
            f"{username}:{password}".encode("utf-8")
        ).decode("ascii")
        supplied = self.headers.get("Authorization", "")
        if not hmac.compare_digest(supplied, expected):
            body = "Authentication required".encode("utf-8")
            self.send_response(401)
            self.send_header("WWW-Authenticate", 'Basic realm="dhbakery"')
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return False
        return True

    def do_GET(self) -> None:
        if not self._authenticate():
            return
        super().do_GET()

    def do_POST(self) -> None:
        if not self._authenticate():
            return
        super().do_POST()
