"""Primary HTTP server for the Boulangerie Ledger Web Dashboard.

Serves ``web_dashboard/`` and the live ``/api/dashboard`` endpoint from the
same origin. PosPal credentials are loaded from the project-root ``.env``.

Usage:
    python3 web_dashboard_server.py --host 127.0.0.1 --port 8600
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import mimetypes
import os
import re
import time
import traceback
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from modules.dashboard_api import DashboardQuery, get_dashboard_payload

logger = logging.getLogger("dashboard")


STATIC_DIR = ROOT / "web_dashboard"
CACHE_TTL_SECONDS = int(os.environ.get("POSPAL_DASHBOARD_CACHE_TTL", "900"))
CACHE: dict[tuple, tuple[float, dict]] = {}


class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/dashboard":
            self._handle_dashboard_api(parsed.query)
            return
        self._handle_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/ai/chat":
            self._handle_ai_chat()
            return
        self._send_json({"error": "not found"}, status=404)

    def _handle_ai_chat(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            body = {}

        question = (body.get("question") or "").strip()
        payload = body.get("payload") or {}
        history = body.get("history") or []
        if not question:
            self._send_json({"error": "question is required"}, status=400)
            return

        if not os.getenv("DEEPSEEK_API_KEY"):
            self._send_json(
                {"error": "DEEPSEEK_API_KEY 未设置，AI 助手不可用"},
                status=503,
            )
            return

        try:
            from modules.ai_assistant import build_context_from_payload, stream_answer
        except Exception as exc:
            logger.exception("AI 助手模块初始化失败: %s", exc)
            self._send_json(
                {"error": f"AI 助手服务初始化失败: {exc}"},
                status=500,
            )
            return

        # Prefer the server's own payload cache (keyed by the displayed
        # range) so the frontend doesn't have to ship the whole 250KB
        # payload — saves request size and keeps context consistent.
        context = None
        try:
            query = _query_from_range(body.get("range") or "")
            if query is not None:
                try:
                    context = build_context_from_payload(
                        _get_cached_payload(query, refresh=False)
                    )
                except Exception as exc:
                    logger.warning("服务端 AI 上下文构建失败(按 range): %s", exc)
            if context is None and payload:
                context = build_context_from_payload(payload)
            if context is None:
                try:
                    context = build_context_from_payload(
                        _get_cached_payload(DashboardQuery.current(), refresh=False)
                    )
                except Exception as exc:
                    logger.warning("服务端 AI 上下文构建失败(默认): %s", exc)
        except Exception as exc:
            logger.warning("构建 AI 上下文失败: %s", exc)

        if context is None:
            context = "（暂无看板数据，请先加载经营数据）"

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Connection", "keep-alive")
        self.end_headers()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:

            async def _run() -> None:
                try:
                    async for item in stream_answer(question, context, history):
                        # item is already a dict: {"token": ...} or {"status": ...}
                        data = json.dumps(item, ensure_ascii=False)
                        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                        self.wfile.flush()
                except Exception as exc:  # surface stream errors to the client
                    logger.error("AI 流式回答失败: %s", exc)
                    err = json.dumps({"error": str(exc)}, ensure_ascii=False)
                    self.wfile.write(f"data: {err}\n\n".encode("utf-8"))
                    self.wfile.flush()
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

            loop.run_until_complete(_run())
        finally:
            try:
                loop.close()
            except Exception:
                pass

    def _handle_dashboard_api(self, query_string: str) -> None:
        query = parse_qs(query_string)
        current = DashboardQuery.current()
        preset = query.get("preset", [""])[0]
        if preset in ("today", "yesterday", "week", "month"):
            q = DashboardQuery.from_preset(preset)
        else:
            year = _int_param(query, "year", current.year)
            month = _int_param(query, "month", current.month)
            q = DashboardQuery(year=year, month=month)

        # Optional explicit date override.
        # Supports both API-style date_from/date_to and short from/to aliases.
        date_from = _first_param(query, "date_from", "from", "start_date", "start")
        date_to = _first_param(query, "date_to", "to", "end_date", "end")
        if date_from or date_to:
            if not (date_from and date_to):
                self._send_json(
                    {"error": "date_from and date_to must be provided together"},
                    status=400,
                )
                return
            try:
                parsed_from = date.fromisoformat(date_from)
                parsed_to = date.fromisoformat(date_to)
            except ValueError:
                self._send_json({"error": "dates must use YYYY-MM-DD"}, status=400)
                return
            if parsed_from > parsed_to:
                self._send_json(
                    {"error": "date_from cannot be later than date_to"}, status=400
                )
                return
            q = DashboardQuery(
                year=_int_param(query, "year", q.year),
                month=_int_param(query, "month", q.month),
                date_from=date_from,
                date_to=date_to,
            )
        refresh = query.get("refresh", ["0"])[0] == "1"

        try:
            payload = _get_cached_payload(q, refresh)
        except Exception as exc:
            logger.error("dashboard payload failed: %s", exc)
            traceback.print_exc()
            self._send_json({"error": str(exc), "type": type(exc).__name__}, status=500)
            return
        self._send_json(payload)

    def _handle_static(self, path: str) -> None:
        rel_path = path.lstrip("/") or "index.html"
        if rel_path == "dashboard":
            rel_path = "index.html"
        target = (STATIC_DIR / rel_path).resolve()

        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.exists():
            target = STATIC_DIR / "index.html"

        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        content = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_json(self, payload: object, status: int = 200) -> None:
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        print("%s - %s" % (self.address_string(), format % args))


def _int_param(query: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int(query.get(key, [str(default)])[0])
    except (TypeError, ValueError):
        return default


def _first_param(query: dict[str, list[str]], *keys: str) -> str | None:
    for key in keys:
        value = query.get(key, [""])[0].strip()
        if value:
            return value
    return None


def _query_from_range(range_str: str) -> DashboardQuery | None:
    """Parse a dashboard ``meta.range`` label back into a DashboardQuery.

    Accepts presets, ``YYYY-MM``, and ``d1 → d2`` / ``d1 至 d2`` ranges.
    Returns None when unparseable so callers can fall back.
    """
    if not range_str:
        return None
    label = str(range_str).strip()
    if label in ("today", "yesterday", "week", "month"):
        return DashboardQuery.from_preset(label)
    m = re.fullmatch(r"(\d{4})-(\d{2})", label)
    if m:
        return DashboardQuery(year=int(m.group(1)), month=int(m.group(2)))
    m = re.fullmatch(
        r"(\d{4}-\d{2}-\d{2})\s*(?:→|至|~|-)\s*(\d{4}-\d{2}-\d{2})", label
    )
    if m:
        d1, d2 = m.group(1), m.group(2)
        start = date.fromisoformat(d1)
        return DashboardQuery(
            year=start.year, month=start.month, date_from=d1, date_to=d2
        )
    return None


def _get_cached_payload(query: DashboardQuery, refresh: bool = False) -> dict:
    key = (query.year, query.month, query.date_from, query.date_to)
    now = time.time()
    if not refresh and key in CACHE:
        created_at, payload = CACHE[key]
        if now - created_at < CACHE_TTL_SECONDS:
            return payload

    payload = get_dashboard_payload(query, force_refresh=refresh)
    CACHE[key] = (now, payload)
    return payload


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8600)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    logger.info("Dashboard running at http://localhost:%d", args.port)
    server.serve_forever()


if __name__ == "__main__":
    main()
