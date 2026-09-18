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

# ---------------------------------------------------------------- the wire
#
# A virtual key can be scoped to a subset of routes and models, and most keys
# worth testing with ARE. So the route and the model are a RUNTIME choice, not a
# constant: a module that hardcodes `/chat/completions` against a key scoped to
# `/messages` does not test the gateway, it tests the key policy, 95 times.
#
# The names match the pair `guardrail_curl.py` already exposes, so there is one
# convention across the directory rather than two.
ROUTE_ENV = "NROUTER_HEALTH_ROUTE"
MODEL_ENV = "NROUTER_HEALTH_MODEL"
DEFAULT_HEALTH_ROUTE = "/chat/completions"
DEFAULT_HEALTH_MODEL = "openai/gpt-4o-mini"

# route -> the wire shape it speaks. Each wire names its request body fields and
# where a served completion actually lives, because they genuinely differ: a
# check that asserts `body.choices` on the Anthropic-shaped wire is asserting
# against a key that is never there, and would fail a perfectly good response.
WIRE_OF_ROUTE = {
    "/chat/completions": "chat",
    "/messages": "messages",
    "/responses": "responses",
    "/completions": "completions",
}
ALLOWED_ROUTES = tuple(WIRE_OF_ROUTE)

# wire -> (prompt field, output-ceiling field, human description of where a
# served completion lives)
WIRE_SHAPE = {
    "chat": ("messages", "max_tokens", "choices[0].message.content"),
    "messages": ("messages", "max_tokens", "content[0].text"),
    "responses": ("input", "max_output_tokens", "output_text / output[0].content[0].text"),
    "completions": ("prompt", "max_tokens", "choices[0].text"),
}

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


def resolve_route(explicit: str = "") -> str:
    """The route under test: `--route`, then NROUTER_HEALTH_ROUTE, then chat."""
    route = explicit or os.environ.get(ROUTE_ENV, "") or DEFAULT_HEALTH_ROUTE
    if not route.startswith("/"):
        route = "/" + route
    if route not in WIRE_OF_ROUTE:
        raise ValueError(
            f"{route!r} is not a supported health-check route. "
            f"Choose one of: {', '.join(ALLOWED_ROUTES)}"
        )
    return route


def resolve_model(explicit: str = "") -> str:
    """The model under test: `--model`, then NROUTER_HEALTH_MODEL, then default."""
    return explicit or os.environ.get(MODEL_ENV, "") or DEFAULT_HEALTH_MODEL


def wire_of(route: str) -> str:
    return WIRE_OF_ROUTE.get(route, "chat")


def prompt_field(route: str) -> str:
    """The request field carrying the prompt on this wire (`input` on /responses)."""
    return WIRE_SHAPE[wire_of(route)][0]


def max_tokens_field(route: str) -> str:
    """The output-ceiling field name for this wire (`max_output_tokens` on /responses)."""
    return WIRE_SHAPE[wire_of(route)][1]


def served_location(route: str) -> str:
    """Where a served completion lives on this wire, for assertion prose."""
    return WIRE_SHAPE[wire_of(route)][2]


def add_wire_arguments(parser: Any) -> None:
    """Add the shared `--route` / `--model` flags, matching guardrail_curl's pair."""
    parser.add_argument(
        "--route",
        default=os.environ.get(ROUTE_ENV, DEFAULT_HEALTH_ROUTE),
        help=f"Route under test, one of: {', '.join(ALLOWED_ROUTES)} (env {ROUTE_ENV})",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get(MODEL_ENV, DEFAULT_HEALTH_MODEL),
        help=f"Model under test (env {MODEL_ENV})",
    )


def build_body(
    route: str,
    model: str,
    prompt: str,
    max_tokens: Optional[int] = 16,
    **extra: Any,
) -> Dict[str, Any]:
    """Build a request body in the shape the route's wire actually accepts.

    `max_tokens` is REQUIRED on the Anthropic-shaped wire, so it is always sent
    rather than defaulted away; pass `max_tokens=None` to omit it deliberately.
    """
    wire = wire_of(route)
    body: Dict[str, Any] = {"model": model}
    if wire in ("chat", "messages"):
        body["messages"] = [{"role": "user", "content": prompt}]
    elif wire == "responses":
        body["input"] = prompt
    else:  # completions
        body["prompt"] = prompt
    if max_tokens is not None:
        body[max_tokens_field(route)] = max_tokens
    body.update(extra)
    return body


def build_multiturn_body(
    route: str,
    model: str,
    turns: List[str],
    max_tokens: Optional[int] = 16,
    **extra: Any,
) -> Dict[str, Any]:
    """The same, for a multi-turn conversation.

    The single-field wires (`/responses`, `/completions`) have nowhere to put a
    turn structure, so the turns are joined — the request still carries the same
    text, which is what a ceiling or a guardrail is reading.
    """
    wire = wire_of(route)
    body: Dict[str, Any] = {"model": model}
    if wire in ("chat", "messages"):
        body["messages"] = [
            {"role": "user" if index % 2 == 0 else "assistant", "content": turn}
            for index, turn in enumerate(turns)
        ]
        # The Anthropic-shaped wire requires the conversation to end on a user
        # turn, so drop a trailing assistant turn rather than send a 400 that
        # has nothing to do with what is under test.
        if body["messages"] and body["messages"][-1]["role"] == "assistant":
            body["messages"].pop()
    elif wire == "responses":
        body["input"] = "\n\n".join(turns)
    else:
        body["prompt"] = "\n\n".join(turns)
    if max_tokens is not None:
        body[max_tokens_field(route)] = max_tokens
    body.update(extra)
    return body


def served_text(route: str, body_text: str) -> Optional[str]:
    """The completion text a served response carries, per wire. None if absent."""
    doc = parse_json(body_text)
    wire = wire_of(route)
    if wire == "chat":
        choices = doc.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            message = choices[0].get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content
    elif wire == "messages":
        content = doc.get("content")
        if isinstance(content, list) and content and isinstance(content[0], dict):
            text = content[0].get("text")
            if isinstance(text, str):
                return text
    elif wire == "responses":
        text = doc.get("output_text")
        if isinstance(text, str):
            return text
        output = doc.get("output")
        if isinstance(output, list) and output and isinstance(output[0], dict):
            parts = output[0].get("content")
            if isinstance(parts, list) and parts and isinstance(parts[0], dict):
                inner = parts[0].get("text")
                if isinstance(inner, str):
                    return inner
    else:  # completions
        choices = doc.get("choices")
        if isinstance(choices, list) and choices and isinstance(choices[0], dict):
            text = choices[0].get("text")
            if isinstance(text, str):
                return text
    return None


def served_body_ok(route: str, body_text: str) -> Tuple[bool, str]:
    """Assert a served body actually carries a completion, at THIS wire's location."""
    if served_text(route, body_text) is None:
        return False, (
            f"the served body carries no completion at {served_location(route)}, "
            f"which is where the {wire_of(route)} wire puts one"
        )
    return True, ""


def route_scope_message(route: str, model: str) -> str:
    """The NOT-CONFIGURED explanation for a key that may not use this route."""
    return (
        f"the gateway answered 403 with x-nr-auth-reason: key_route_not_allowed for "
        f"{route} — this key's route policy does not include it, so nothing about the "
        f"gateway was tested. Point the suite at a route the key allows, e.g. "
        f"{ROUTE_ENV}=/messages {MODEL_ENV}=<a model the key allows> "
        f"(current: {ROUTE_ENV}={route}, {MODEL_ENV}={model})"
    )


def fixed_route_scope_detail(
    route: str, status: int, headers: Dict[str, str]
) -> Optional[str]:
    """NOT-CONFIGURED prose for a check pinned to a route the key may not use.

    `note_route_scope` covers the route UNDER TEST and short-circuits the module.
    Some checks are pinned to a different route by their own nature — embeddings
    billing must ask `/embeddings`, an MCP probe must ask `/mcp` — and a key
    scoped away from that one route says nothing about the rest of the suite. So
    this reports the single check NOT-CONFIGURED, names the route, and lets
    every other check run.

    Deliberately as narrow as the module guard: only a 403 that NAMES
    `key_route_not_allowed`. Any other 403, and any other status, is a real
    failure and falls through to the check's own assertions.
    """
    if status != 403 or headers.get("x-nr-auth-reason") != "key_route_not_allowed":
        return None
    return (
        f"the gateway answered 403 with x-nr-auth-reason: key_route_not_allowed for "
        f"{route} — this check can only be made on that route, and this key's route "
        f"policy does not include it, so nothing about the behaviour was tested. Run "
        f"it with a key whose route policy covers {route}."
    )


def auth_denial_note(
    status: int, headers: Dict[str, str], expect_status: Tuple[int, ...]
) -> str:
    """Name an unexpected auth denial, and whether the gateway said WHY.

    A 401/403 where the check expected some other refusal means the request never
    reached the behaviour under test. That is a failure, and the detail has to
    carry the evidence: the observed status, and the value of `x-nr-auth-reason`
    or the fact that the header is ABSENT. A denial that names no machine reason
    leaves a client string-matching prose, so its absence is the finding, not a
    blank.
    """
    if status not in (401, 403) or status in expect_status:
        return ""
    reason = headers.get("x-nr-auth-reason")
    if reason:
        return (
            f"the gateway answered {status} with x-nr-auth-reason: {reason} — an "
            f"authorization denial, not the {expect_status} refusal under test, so "
            "the behaviour was never reached"
        )
    return (
        f"the gateway answered {status} with NO x-nr-auth-reason header — an "
        f"authorization denial, not the {expect_status} refusal under test, and it "
        "names no machine-readable reason, so a client has only the prose to "
        "classify it by"
    )


def note_route_scope(checker: Any, status: int, headers: Dict[str, str]) -> bool:
    """Record, once, that this key is not scoped to the route under test.

    This IS a provably absent precondition — the request never reached the
    behaviour under test — so it reports NOT-CONFIGURED rather than FAIL. It is
    deliberately narrow: only a 403 that NAMES `key_route_not_allowed`, and only
    for a request actually made on the route under test. A 403 for any other
    reason, or on some other path, still fails the check that saw it.
    """
    if status != 403 or headers.get("x-nr-auth-reason") != "key_route_not_allowed":
        return False
    route = getattr(checker, "route", None)
    if getattr(checker, "_current_path", None) != route:
        return False
    if not getattr(checker, "scope_detail", None):
        checker.scope_detail = route_scope_message(route, getattr(checker, "model", "?"))
    return True


def run_checks_with_scope_guard(checker: Any, checks: List[Callable]) -> None:
    """Run checks, short-circuiting the whole module on a route-scope refusal.

    Without this, a key scoped to another route reports 95 gateway failures, and
    the one fact worth knowing — that the suite was pointed at a route this key
    may not use — is buried under them.
    """
    for index, check in enumerate(checks):
        check()
        if getattr(checker, "scope_detail", None):
            for skipped in checks[index + 1:]:
                name = skipped.__name__
                if name.startswith("check_"):
                    name = name[len("check_"):]
                checker._record(
                    name, "(not executed)", 0, {},
                    "(skipped: this key is not scoped to the route under test)",
                    False, False, detail=checker.scope_detail, not_configured=True,
                )
            return


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


def main_json_stdout_contract_self_test(
    main_fn: Callable[[], int],
    argv: List[str],
    banner_marker: str,
    expect_keys: Tuple[str, ...],
) -> None:
    """Prove a module's REAL `main()` leaves EXACTLY one JSON document on stdout.

    `json_stdout_contract_self_test` covers modules that report through
    `emit_results`. The three older modules print their banner and their check
    list inline in `main()`, so the only honest way to pin the contract is to RUN
    `main()` — banner included — and parse what it wrote to stdout. Anything that
    leaks (a banner, a `[FAIL]` line, a trailing summary) makes `json.loads`
    raise here, which is exactly what it does to the caller's `> report.json`.

    The caller supplies `argv` and is responsible for making `main()` reach its
    reporting path without a network: it substitutes the module's checker class
    for a double first. No key ever leaves this process — the placeholder below
    exists only to get past the "no credential" early return.
    """
    saved_argv = sys.argv
    saved_key = os.environ.get(ENV_VAR)
    os.environ[ENV_VAR] = "sk-nrouter-self-test-placeholder-not-a-credential"
    captured_out, captured_err = io.StringIO(), io.StringIO()
    try:
        sys.argv = list(argv)
        with contextlib.redirect_stdout(captured_out), contextlib.redirect_stderr(captured_err):
            main_fn()
    finally:
        sys.argv = saved_argv
        if saved_key is None:
            os.environ.pop(ENV_VAR, None)
        else:
            os.environ[ENV_VAR] = saved_key

    stdout_text = captured_out.getvalue()
    stderr_text = captured_err.getvalue()
    if "--json" in argv:
        parsed = json.loads(stdout_text)  # raises if ANYTHING else reached stdout
        for key in expect_keys:
            assert key in parsed, f"the JSON document lost its {key!r} key"
        assert banner_marker not in stdout_text, (
            f"the human banner leaked onto stdout, so `--json > report.json` is "
            f"unparseable: {stdout_text[:120]!r}"
        )
        assert banner_marker in stderr_text, (
            "the banner vanished instead of moving to stderr — the human report "
            "must not be lost, only redirected"
        )
        return

    # Without --json the human report goes to stdout and NO JSON is printed.
    assert banner_marker in stdout_text, "the human report vanished from the default path"
    try:
        json.loads(stdout_text)
    except json.JSONDecodeError:
        return
    raise AssertionError("the default path printed a JSON document instead of a report")


def wire_contract_self_test() -> None:
    """Prove each wire builds the body it accepts and reads the body it returns.

    The point of this is the NEGATIVE half: a chat-shaped assertion must not
    pass on the Anthropic-shaped wire, and vice versa. Without that, "it works
    on both wires" means "it looks at neither".
    """
    served = {
        "/chat/completions": '{"choices":[{"message":{"role":"assistant","content":"hello"}}]}',
        "/messages": '{"content":[{"type":"text","text":"hello"}],"role":"assistant"}',
        "/responses": '{"output":[{"content":[{"type":"output_text","text":"hello"}]}]}',
        "/completions": '{"choices":[{"text":"hello"}]}',
    }
    for route, document in served.items():
        assert served_text(route, document) == "hello", (
            f"{route}: the completion was not found at {served_location(route)}"
        )
        ok, detail = served_body_ok(route, document)
        assert ok, f"{route}: {detail}"

        # A body from ANOTHER wire must NOT satisfy this one.
        for other_route, other_document in served.items():
            if other_route == route or wire_of(other_route) == wire_of(route):
                continue
            wrong_ok, _ = served_body_ok(route, other_document)
            assert not wrong_ok, (
                f"{route} accepted a {wire_of(other_route)}-shaped body; the assertion "
                "is not actually reading this wire"
            )

    # `/responses` also accepts the convenience field.
    assert served_text("/responses", '{"output_text":"hi"}') == "hi"

    # A refusal envelope is never a served completion, on any wire.
    refusal = '{"error":{"type":"invalid_request_error","message":"nope"}}'
    for route in served:
        ok, _ = served_body_ok(route, refusal)
        assert not ok, f"{route} read a refusal envelope as a served completion"

    # Request bodies carry the fields each wire requires, and no foreign ones.
    chat = build_body("/chat/completions", "m", "ping")
    assert chat["messages"][0]["content"] == "ping" and chat["max_tokens"] == 16, chat

    messages = build_body("/messages", "m", "ping")
    assert messages["messages"][0]["content"] == "ping", messages
    assert "max_tokens" in messages, "max_tokens is REQUIRED on the messages wire"
    assert "input" not in messages and "prompt" not in messages, messages

    responses = build_body("/responses", "m", "ping")
    assert responses["input"] == "ping", responses
    assert responses["max_output_tokens"] == 16, "the responses wire names its ceiling differently"
    assert "messages" not in responses and "max_tokens" not in responses, responses

    completions = build_body("/completions", "m", "ping")
    assert completions["prompt"] == "ping" and completions["max_tokens"] == 16, completions
    assert "messages" not in completions and "input" not in completions, completions

    assert max_tokens_field("/responses") == "max_output_tokens"
    assert max_tokens_field("/messages") == "max_tokens"
    assert prompt_field("/responses") == "input"
    assert prompt_field("/completions") == "prompt"
    assert prompt_field("/messages") == "messages"
    for route in ALLOWED_ROUTES:
        assert prompt_field(route) in build_body(route, "m", "ping"), route
    assert build_body("/messages", "m", "ping", max_tokens=None).get("max_tokens") is None

    # Multi-turn: structured where the wire has turns, joined where it does not.
    turns = ["first", "second", "third"]
    for route in ("/chat/completions", "/messages"):
        multi = build_multiturn_body(route, "m", turns)
        assert len(multi["messages"]) == 3, multi
        assert multi["messages"][-1]["role"] == "user", (
            "the messages wire requires the conversation to end on a user turn"
        )
    joined = build_multiturn_body("/responses", "m", turns)
    assert all(turn in joined["input"] for turn in turns), joined
    # An even number of turns would otherwise end on an assistant turn.
    trimmed = build_multiturn_body("/messages", "m", ["a", "b"])
    assert trimmed["messages"][-1]["role"] == "user", trimmed

    # Route resolution, and its refusal of anything outside the allowed set.
    previous_route = os.environ.pop(ROUTE_ENV, None)
    previous_model = os.environ.pop(MODEL_ENV, None)
    try:
        assert resolve_route("") == DEFAULT_HEALTH_ROUTE
        assert resolve_model("") == DEFAULT_HEALTH_MODEL
        assert resolve_route("messages") == "/messages", "a bare route name should normalize"
        os.environ[ROUTE_ENV] = "/messages"
        os.environ[MODEL_ENV] = "claude-haiku-4-5-20251001"
        assert resolve_route("") == "/messages"
        assert resolve_model("") == "claude-haiku-4-5-20251001"
        assert resolve_route("/responses") == "/responses", "an explicit flag outranks the env"
        try:
            resolve_route("/v1/embeddings")
        except ValueError as exc:
            assert "not a supported health-check route" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("an unsupported route was accepted")
    finally:
        os.environ.pop(ROUTE_ENV, None)
        os.environ.pop(MODEL_ENV, None)
        if previous_route is not None:
            os.environ[ROUTE_ENV] = previous_route
        if previous_model is not None:
            os.environ[MODEL_ENV] = previous_model

    # The route-scope guard: narrow, and NOT-CONFIGURED rather than FAIL.
    class _Checker:
        route = "/messages"
        model = "claude-haiku-4-5-20251001"
        scope_detail = None
        _current_path = "/messages"

    checker = _Checker()
    assert note_route_scope(checker, 403, {"x-nr-auth-reason": "key_route_not_allowed"})
    assert "key_route_not_allowed" in checker.scope_detail
    assert ROUTE_ENV in checker.scope_detail, "the message must name the override to set"

    other = _Checker()
    assert not note_route_scope(other, 403, {"x-nr-auth-reason": "key_blocked"}), (
        "a 403 for a different reason is a real failure, not a scope refusal"
    )
    assert not note_route_scope(other, 401, {"x-nr-auth-reason": "key_route_not_allowed"})
    off_route = _Checker()
    off_route._current_path = "/openapi.json"
    assert not note_route_scope(
        off_route, 403, {"x-nr-auth-reason": "key_route_not_allowed"}
    ), "a refusal on some other path must not short-circuit the route under test"
    assert other.scope_detail is None and off_route.scope_detail is None


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
    wire_contract_self_test()
    print("[PASS] _curl_common.py self-test passed cleanly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_self_test())
