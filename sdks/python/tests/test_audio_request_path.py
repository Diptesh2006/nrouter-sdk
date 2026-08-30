"""SDK-021: pin the vendor client's real multipart gateway contract."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from nroutersdk import nRouter


KEY = "sk-nrouter-test"


def test_sdk_021_vendor_audio_uses_gateway_multipart_path():
    observed: dict[str, object] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers["content-length"])
            observed.update(
                path=self.path,
                authorization=self.headers["authorization"],
                content_type=self.headers["content-type"],
                body=self.rfile.read(length),
            )
            payload = b'{"text":"hello"}'
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.send_header("x-nr-request-id", "req_python_audio")
            self.send_header("x-nr-request-cost", "0.00042")
            self.send_header("x-nr-cost-status", "exact")
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *_args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with nRouter(
            api_key=KEY,
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            max_retries=0,
        ) as client:
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=("sample.wav", b"RIFF-test-audio", "audio/wav"),
            )
            assert response.text == "hello"
            assert client.last_response is not None
            assert client.last_response.request_id == "req_python_audio"
            assert client.last_response.cost == 0.00042
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    assert observed["path"] == "/v1/audio/transcriptions"
    assert observed["authorization"] == f"Bearer {KEY}"
    assert str(observed["content_type"]).startswith("multipart/form-data; boundary=")
    body = bytes(observed["body"])
    assert b'name="model"' in body and b"whisper-1" in body
    assert b'name="file"; filename="sample.wav"' in body
    assert b"RIFF-test-audio" in body
