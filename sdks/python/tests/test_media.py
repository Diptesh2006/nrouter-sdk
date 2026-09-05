"""Unit tests for media helpers (validate_audio_format, wait_for_video)."""

from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import pytest

from nroutersdk import (
    AsyncnRouter,
    VALID_AUDIO_FORMATS,
    nRouter,
    nRouterError,
    nRouterRequestError,
    nRouterServiceError,
    validate_audio_format,
)

KEY = "sk-nrouter-test000000000000"


def test_validate_audio_format_accepts_valid():
    for fmt in VALID_AUDIO_FORMATS:
        validate_audio_format(fmt)
        validate_audio_format(f" {fmt.upper()} ")


def test_validate_audio_format_rejects_invalid():
    with pytest.raises(nRouterRequestError):
        validate_audio_format("ogg")
    with pytest.raises(nRouterRequestError):
        validate_audio_format("mp4")
    with pytest.raises(nRouterRequestError):
        validate_audio_format("")
    with pytest.raises(nRouterRequestError):
        validate_audio_format(123)  # type: ignore[arg-type]


def test_sync_wait_for_video_success():
    calls = 0

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            nonlocal calls
            calls += 1
            status = "completed" if calls >= 2 else "processing"
            payload = f'{{"id":"vid_123","status":"{status}"}}'.encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args, **kwargs) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        with nRouter(api_key=KEY, base_url=f"http://127.0.0.1:{server.server_port}/v1") as client:
            resp = client.wait_for_video("vid_123", poll_interval=0.01, timeout=2.0)
            assert resp.get("status") == "completed"
            assert calls >= 2
    finally:
        server.shutdown()
        server.server_close()
        t.join(timeout=1)


def test_sync_wait_for_video_failed():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            payload = b'{"id":"vid_fail","status":"failed"}'
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args, **kwargs) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    t = Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        with nRouter(api_key=KEY, base_url=f"http://127.0.0.1:{server.server_port}/v1") as client:
            with pytest.raises(nRouterServiceError) as exc_info:
                client.wait_for_video("vid_fail", poll_interval=0.01, timeout=2.0)
            assert "ended with status: failed" in str(exc_info.value)
    finally:
        server.shutdown()
        server.server_close()
        t.join(timeout=1)


def test_wait_for_video_empty_id():
    with nRouter(api_key=KEY) as client:
        with pytest.raises(nRouterRequestError):
            client.wait_for_video("  ")
