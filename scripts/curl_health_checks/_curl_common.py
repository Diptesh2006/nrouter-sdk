#!/usr/bin/env python3
"""Shared plumbing for the nRouter pure-curl health checks.

ONE curl invocation, ONE response parser, ONE credential rule. Every check
module imports these rather than carrying its own copy, because a parsing defect
that lives in ten copies gets fixed in one of them.

Three rules are encoded here and are worth stating out loud, because each of
them was a real defect before it was a function:

1. CREDENTIALS COME FROM `NROUTER_API_KEY`, AND NOWHERE ELSE.
   There is deliberately no fallback that reads a key out of a file on disk.
   This repository is public: a hardcoded path is itself a disclosure of an
   internal convention, and a fallback is worse than untidy — it would pick up
   whatever key it found and send it to whatever `NROUTER_BASE_URL` the caller
   happened to set, including someone else's host. A missing key is a usage
   error with a clear message, never a silent substitution.

2. A NON-ZERO CURL EXIT IS A TRANSPORT FAILURE, WHATEVER ARRIVED ON STDOUT.
   `curl` exits 18 (partial file) or 56 (recv failure) with a half-read body
   still on stdout. Parsing that fragment as if it were the response turns a
   broken read into a passing assertion — the headers look right because they
   arrived first, and the truncated body is never inspected.

3. THE BODY IS EVERYTHING AFTER THE LAST HEADER BLOCK, PRESERVED INTACT.
   Splitting the whole response on blank lines and keeping the final chunk is
   correct exactly until a body CONTAINS a blank line — which every SSE stream
   does, between every event. Such a split silently reduces a stream to its last
   frame, so a check asserting "the body carries N events" reads 1 and a check
   asserting content-type passes anyway.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

DEFAULT_BASE_URL = "https://api.nrouter.ai/v1"
ENV_VAR = "NROUTER_API_KEY"

# Check results. NOT-CONFIGURED is not a soft PASS: it means the PRECONDITION
# for the check is provably absent on this plane (a route answered 404, an
# organization opted out, an operator supplied no fixture). It is never used to
# describe an assertion that simply did not hold.
PASS = "PASS"
FAIL = "FAIL"
NOT_CONFIGURED = "NOT-CONFIGURED"

# Exit codes: 0 = every check passed, 1 = at least one check FAILED,
# 2 = the module could not run at all (no credential).
EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UNRUNNABLE = 2

SECRET_PATTERNS = [
    re.compile(r"sk-nrouter-[A-Za-z0-9_-]+"),
    re.compile(r"sk-ant-[A-Za-z0-9_-]+"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]+", re.IGNORECASE),
]

# Headers worth carrying into a JSON report beyond the x-nr-* namespace.
REPORTED_HEADERS = (
    "content-type",
    "cache-control",
    "retry-after",
    "x-content-type-options",
)

MISSING_KEY_MESSAGE = (
    f"NOT-CONFIGURED: {ENV_VAR} is not set, so no live check can run.\n"
    f"  export {ENV_VAR}=sk-nrouter-...      # your own virtual key\n"
    "  ...or pass --self-test for the offline verification, which needs no key.\n"
    "This tool reads the key from the environment only. It will not search your\n"
    "disk for a credential, because it cannot know which host you pointed it at."
)


def sanitize(text: str) -> str:
    """Redact anything key-shaped before it reaches a report or a terminal."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def resolve_api_key(explicit: str = "") -> str:
    """The key comes from `--api-key` or `NROUTER_API_KEY`. There is no third source.

    See rule 1 in the module docstring: a credentials-file fallback in a public
    repository leaks a path convention and can send a key to an arbitrary host.
    """
    return explicit or os.environ.get(ENV_VAR, "")


def split_head_body(raw: str) -> Tuple[str, str]:
    """Return (last header block, body) from `curl -D -` output.

    `curl` writes one header block per response it receives — a `100 Continue`,
    a redirect hop, a proxy `CONNECT` — and then the body verbatim. So the walk
    is: consume header blocks from the front while the text still starts with a
    status line, and whatever remains is the body, UNTOUCHED. The body is never
    re-split on blank lines, which is what keeps an SSE stream whole.
    """
    position = 0
    header_block = ""
    while raw.startswith("HTTP/", position):
        crlf = raw.find("\r\n\r\n", position)
        lf = raw.find("\n\n", position)
        ends = [(index, length) for index, length in ((crlf, 4), (lf, 2)) if index != -1]
        if not ends:
            # A header block with no terminator: a truncated response.
            header_block = raw[position:]
            position = len(raw)
            break
        end, terminator = min(ends)
        header_block = raw[position:end]
        position = end + terminator
    return header_block, raw[position:]


def parse_header_block(header_block: str) -> Tuple[int, Dict[str, str]]:
    """Return (status code, lowercased headers) for one header block."""
    headers: Dict[str, str] = {}
    status = 0
    for line in header_block.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("HTTP/"):
            match = re.match(r"^HTTP/[0-9.]+\s+(\d+)", line)
            if match:
                status = int(match.group(1))
        elif ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip().lower()] = value.strip()
    return status, headers


def parse_curl_output(raw: str) -> Tuple[int, Dict[str, str], str]:
    """Parse raw `curl -sS -D -` output into (status, headers, body)."""
    header_block, body = split_head_body(raw)
    status, headers = parse_header_block(header_block)
    return status, headers, body


def run_curl(
    args: List[str],
    timeout_s: int = 45,
    stdin_data: Optional[str] = None,
    _runner: Callable = subprocess.run,
) -> Tuple[int, Dict[str, str], str, float]:
    """Execute raw curl and return (status, headers, body, latency_ms).

    A status of 0 means the request never completed: timeout, spawn failure, or
    a non-zero curl exit. Callers assert on the status they expect, so a
    transport failure can only ever make a check FAIL — it can never be mistaken
    for the response the check was hoping for.

    `_runner` exists so the parser and the transport-failure rule can be
    exercised offline; production callers never pass it.
    """
    cmd = ["curl", "-sS", "-D", "-"] + args
    start = time.monotonic()
    try:
        proc = _runner(
            cmd,
            input=stdin_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        return 0, {}, "Request timed out", round((time.monotonic() - start) * 1000.0, 1)
    except Exception as exc:  # pragma: no cover - defensive
        return 0, {}, f"Subprocess error: {exc}", round((time.monotonic() - start) * 1000.0, 1)

    latency = round((time.monotonic() - start) * 1000.0, 1)

    if proc.returncode != 0:
        # Rule 2: bytes on stdout do NOT redeem a non-zero exit. curl 18 and 56
        # both hand back a partial body, and treating it as the response is how
        # a truncated read becomes a green check.
        reason = (proc.stderr or "").strip() or "transport failure"
        return 0, {}, sanitize(f"curl exit code {proc.returncode}: {reason}"), latency

    status, headers, body = parse_curl_output(proc.stdout)
    return status, headers, body, latency


def assert_all(conditions: List[Tuple[bool, str]]) -> Tuple[bool, str]:
    """Collect EVERY failed clause, so one check reports all of its reasons."""
    failed = [message for ok, message in conditions if not ok]
    return (not failed, "; ".join(failed))


def parse_json(body: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(body)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def error_of(body: str) -> Dict[str, Any]:
    err = parse_json(body).get("error")
    return err if isinstance(err, dict) else {}


def header_float(headers: Dict[str, str], name: str) -> Optional[float]:
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def header_int(headers: Dict[str, str], name: str) -> Optional[int]:
    raw = headers.get(name)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def reported_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """The contract-relevant headers, for the JSON report."""
    return {
        key: value
        for key, value in sorted(headers.items())
        if key.startswith("x-nr-") or key in REPORTED_HEADERS
    }


def emit_results(
    suite: Dict[str, Any],
    markdown: str = "",
    as_json: bool = False,
    step_summary: bool = False,
    header: str = "",
) -> int:
    """Print a completed run and return its exit code.

    THE `--json` CONTRACT: with `as_json`, STDOUT carries EXACTLY ONE JSON
    document and nothing else, so `module.py --json > report.json` produces a
    parseable file. The human report is not discarded — it is written to stderr,
    so a person watching the terminal still sees both, and a pipeline that
    redirects stdout gets clean JSON.

    Printing a banner and a check list above the document is the defect this
    exists to prevent: it costs nothing on screen and makes the artifact
    unusable to every consumer that reads stdout.
    """
    stream = sys.stderr if as_json else sys.stdout
    if header:
        print(header, file=stream)
    for row in suite.get("checks", []):
        print(f"[{row['result']}] {row['name']} - HTTP {row['status']}", file=stream)
        if row.get("detail"):
            print(f"        {row['detail']}", file=stream)
    print(
        f"Checks: {suite.get('total_checks', 0)} | "
        f"passed {suite.get('passed_checks', 0)} | "
        f"failed {suite.get('failed_checks', 0)} | "
        f"not-configured {suite.get('not_configured_checks', 0)}",
        file=stream,
    )

    if step_summary and markdown:
        target = os.environ.get("GITHUB_STEP_SUMMARY")
        if target:
            try:
                with open(target, "a") as handle:
                    handle.write("\n" + markdown + "\n")
            except Exception as exc:
                print(f"Warning: could not write step summary: {exc}", file=sys.stderr)

    if as_json:
        # The one and only thing this function writes to stdout.
        print(json.dumps(suite, indent=2))

    return EXIT_OK if suite.get("all_passed") else EXIT_FAILED


def json_stdout_contract_self_test(suite: Dict[str, Any], markdown: str = "") -> None:
    """Prove `--json` leaves EXACTLY one JSON document on stdout.

    Captures the real reporting path rather than asserting about it: anything
    that leaks onto stdout — a banner, a `[FAIL]` line, a trailing summary —
    makes `json.loads` raise here, which is precisely what it does to the
    caller's `> report.json`.
    """
    captured_out, captured_err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(captured_out), contextlib.redirect_stderr(captured_err):
        emit_results(suite, markdown, as_json=True, header="=== human banner ===")

    stdout_text = captured_out.getvalue()
    parsed = json.loads(stdout_text)  # raises if ANYTHING else reached stdout
    assert parsed.get("feature") == suite.get("feature"), parsed.get("feature")
    assert isinstance(parsed.get("checks"), list) and parsed["checks"], "the JSON carried no checks"
    for row in parsed["checks"]:
        assert {
            "name", "request", "status", "headers", "assertion", "result", "expected_failure"
        } <= set(row), f"{row.get('name')} is missing a required JSON field"

    # The human report must still exist — on stderr.
    stderr_text = captured_err.getvalue()
    assert "=== human banner ===" in stderr_text, "the banner vanished instead of moving to stderr"
    assert "Checks:" in stderr_text, "the human summary vanished instead of moving to stderr"
    assert "=== human banner ===" not in stdout_text, "the banner leaked onto stdout"

    # Without --json the human report goes to stdout and NO JSON is printed.
    plain_out = io.StringIO()
    with contextlib.redirect_stdout(plain_out):
        emit_results(suite, markdown, as_json=False, header="=== human banner ===")
    plain_text = plain_out.getvalue()
    assert "Checks:" in plain_text, "the human report vanished from the default path"
    try:
        json.loads(plain_text)
    except json.JSONDecodeError:
        pass
    else:  # pragma: no cover - only reachable if the human report disappears
        raise AssertionError("the default path printed a JSON document instead of a report")


def parser_contract_self_test() -> None:
    """Mutation checks for the two transport rules. Every module calls this.

    These are not decoration: each assertion here corresponds to a defect that
    previously lived in ten copy-pasted parsers at once.
    """
    # RULE 3 — an SSE body is full of blank lines and must survive INTACT.
    #
    # The framing here is CRLF THROUGHOUT, because that is what curl actually
    # receives: HTTP/1.1 headers are CRLF-terminated and an SSE event ends with
    # a blank CRLF line. A fixture that mixes CRLF headers with LF body
    # separators is NOT a regression test — the naive `split("\r\n\r\n")` parser
    # survives it (one split, body intact) and the gate passes while the defect
    # is still present. Measured 2026-09-17: the first version of this assertion
    # was exactly that shape and did not bite when the old parser was restored.
    sse = (
        "HTTP/1.1 200 OK\r\n"
        "content-type: text/event-stream\r\n"
        "x-nr-response-cache: bypass\r\n"
        "\r\n"
        'data: {"choices":[{"delta":{"content":"one"}}]}\r\n'
        "\r\n"
        'data: {"choices":[{"delta":{"content":"two"}}]}\r\n'
        "\r\n"
        "data: [DONE]\r\n"
        "\r\n"
    )
    status, headers, body = parse_curl_output(sse)
    assert status == 200, f"SSE status parsed as {status}"
    assert headers.get("content-type") == "text/event-stream", headers
    assert headers.get("x-nr-response-cache") == "bypass", headers
    assert body.count("data:") == 3, (
        f"the SSE body was truncated to {body.count('data:')} of 3 events — "
        "the parser split the whole response on blank lines and kept only the "
        "last chunk, which reduces every stream to its final frame"
    )
    assert body.startswith('data: {"choices"'), "the SSE body lost its opening event"
    assert "[DONE]" in body, "the SSE body lost its terminating event"

    # The same stream with LF-only framing (some proxies normalize it) must also
    # survive: this is the second truncation path in the old parser, where the
    # CRLF split finds nothing and it falls back to splitting on "\n\n".
    sse_lf = (
        "HTTP/1.1 200 OK\n"
        "content-type: text/event-stream\n"
        "\n"
        "data: one\n"
        "\n"
        "data: two\n"
        "\n"
        "data: [DONE]\n"
        "\n"
    )
    lf_status, lf_headers, lf_body = parse_curl_output(sse_lf)
    assert lf_status == 200, lf_status
    assert lf_headers.get("content-type") == "text/event-stream", lf_headers
    assert lf_body.count("data:") == 3, (
        f"the LF-framed SSE body was truncated to {lf_body.count('data:')} of 3 events"
    )

    # A multi-paragraph plain body must survive intact too, in both framings.
    prose = "HTTP/1.1 200 OK\r\ncontent-type: text/plain\r\n\r\nfirst para\r\n\r\nsecond para\r\n"
    _, _, prose_body = parse_curl_output(prose)
    assert prose_body == "first para\r\n\r\nsecond para\r\n", repr(prose_body)

    # Multiple header blocks: the LAST one before the body wins.
    hops = (
        "HTTP/1.1 100 Continue\r\n\r\n"
        "HTTP/1.1 200 OK\r\nx-nr-request-id: abc-123\r\n\r\n"
        '{"ok":true}'
    )
    hop_status, hop_headers, hop_body = parse_curl_output(hops)
    assert hop_status == 200, hop_status
    assert hop_headers.get("x-nr-request-id") == "abc-123", hop_headers
    assert hop_body == '{"ok":true}', repr(hop_body)

    # RULE 2 — curl rc 56 with a partial body on stdout is a TRANSPORT FAILURE.
    class _PartialRead:
        returncode = 56
        stdout = (
            "HTTP/1.1 200 OK\r\n"
            "content-type: application/json\r\n"
            "x-nr-request-cost: 0.000031\r\n"
            "\r\n"
            '{"choices":[{"message":{"content":"tru'
        )
        stderr = "curl: (56) Recv failure: Connection reset by peer"

    status, headers, body, _ = run_curl(
        ["https://example.invalid"], _runner=lambda *a, **k: _PartialRead()
    )
    assert status == 0, (
        f"a truncated read (curl rc 56) was reported as HTTP {status}; the "
        "partial body would have been asserted against as if it were complete"
    )
    assert headers == {}, f"headers survived a transport failure: {headers}"
    assert "56" in body, body

    # A clean rc 0 with the same bytes still parses normally.
    class _CleanRead:
        returncode = 0
        stdout = 'HTTP/1.1 200 OK\r\ncontent-type: application/json\r\n\r\n{"ok":1}'
        stderr = ""

    ok_status, ok_headers, ok_body, _ = run_curl(
        ["https://example.invalid"], _runner=lambda *a, **k: _CleanRead()
    )
    assert ok_status == 200 and ok_body == '{"ok":1}', (ok_status, ok_body)
    assert ok_headers.get("content-type") == "application/json"

    # RULE 1 — the credential resolver reads the environment and nothing else.
    previous = os.environ.pop(ENV_VAR, None)
    try:
        assert resolve_api_key("") == "", "a key appeared from somewhere other than the environment"
        os.environ[ENV_VAR] = "sk-nrouter-from-env"
        assert resolve_api_key("") == "sk-nrouter-from-env"
        assert resolve_api_key("sk-nrouter-explicit") == "sk-nrouter-explicit"
    finally:
        os.environ.pop(ENV_VAR, None)
        if previous is not None:
            os.environ[ENV_VAR] = previous

    # Sanitization actually bites.
    assert "sk-nrouter-" not in sanitize("key sk-nrouter-abc123 leaked")
    assert "[REDACTED]" in sanitize("Authorization: Bearer sk-nrouter-abc123")


def run_self_test() -> int:
    """Offline verification of the shared plumbing."""
    print("Running _curl_common.py --self-test (offline mode)...")
    parser_contract_self_test()
    print("[PASS] _curl_common.py self-test passed cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_self_test())
