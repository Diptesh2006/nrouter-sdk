#!/usr/bin/env python3
"""Prove every SDK bounds how long it waits, and none of them re-sends a bill.

Two client-side properties, one file, because they fail the same way: silently,
in a published package, on the first call a customer makes.

**Waiting.** A default timeout is the line nobody writes and every transport
already has an opinion about — usually the wrong one. `URLSession.shared` waits
60 s for the response and seven days for the resource; `package:http` waits
FOREVER; `httr` passes no timeout to libcurl and `CURLOPT_TIMEOUT` defaults to
zero, which also means forever; `reqwest::Client::new()` sets none either.
Sixty seconds is BELOW what the gateway may honestly take, so it aborts a
request the gateway goes on to finish and BILL. Forever is not a bound at all:
one silent gateway hangs the calling process, and on a phone that is a spinner
nobody can cancel.

The gateway's worst HONEST case before a first byte is roughly 410 s: up to
three provider attempts, each with a 10 s connect timeout and a 120 s
between-bytes read timeout, plus at most 20 s of cumulative backoff. Every
bound here therefore sits comfortably above that and comfortably below
infinity — and a STREAMING or BINARY response is bounded by when the bytes
STOP, never by a whole-request ceiling, because severing one of those truncates
a response the customer has already paid for.

**Re-sending.** This is the money half. A retry is a SECOND CALL and a SECOND
BILL: the gateway reserves credit exactly once per customer request and owns
retry and failover on its own side, above the provider and below that
reservation, so a client retrying on top of it pays twice for one answer and
the gateway has nothing to dedupe the second call against (gateway gate 8). The
dangerous case is the timeout or the 5xx, not the honest refusal — the gateway
may have accepted, dispatched and billed the request before the socket died, so
the attempt that "failed" is a completed purchase. Both SDKs built on a vendor
client inherit automatic retries unless they say otherwise: the Python vendor
client defaults to TWO, and the JS one likewise, which is why `nroutersdk` pins
`DEFAULT_MAX_RETRIES = 0` and the JS client forces `maxRetries: 0` on every
non-GET. That pin is a REQUIRED PROPERTY here, not an observation someone made
once.

Scope, and why it is a separate file. `check_conformance.py` holds SDK source
to `spec/nrouter-sdk-spec.json` — but the spec fixes headers, endpoints and
error codes and carries nothing about CLIENT BEHAVIOUR, so no timeout and no
retry policy is expressible in it. `doc_wires.py` reads the documentation
corpus and says in its own docstring that SDK source is out of scope.
`source_defaults.py` reads SDK source but only for the default MODEL. A default
timeout therefore falls between all three, which is exactly how `URLSession
.shared`, a bare `http.Client()` and a naked `httr::GET` survived ten SDKs and
several audits. This file closes that seam and is imported by
`check_conformance.py` the same way `doc_wires` and `source_defaults` are.

Both properties carry BOTH halves, for the reason `source_defaults.py` gives:

1. An SDK declared to HAVE the property must have it — the value AND a site
   that applies it, because a constant nobody wires in is decoration. (Measured:
   deleting the Swift line that copies the session's bound onto the outgoing
   request leaves every constant in place and restores Foundation's 60 s.)
2. An SDK declared NOT to have it must genuinely not have it. Without this a
   timeout added to an inheriting SDK tomorrow, or a retry loop added to Dart,
   is invisible to the gate — the hole a registry-only check always has.

An SDK may ride a transport's default instead of declaring its own, and two
say so here. What it may not do is ride one that has NO default: an entry whose
inherited bound is `None` FAILS. Inheriting is a decision about which bound
applies, never a way to have none, and a registry that could excuse an
unbounded SDK would be the exemption that ate the gate.

    python3 conformance/client_timeouts.py             # check
    python3 conformance/client_timeouts.py --self-test # prove the gate bites
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# registry shapes
# ---------------------------------------------------------------------------
class Declared(NamedTuple):
    """An SDK that declares its own deadlines in its own source.

    `values` are (label, pattern, expected) triples. `expected=None` asserts
    only that the declaration is THERE; a string asserts group 1 equals it
    exactly, and a drift is a failing gate rather than a warning.

    `applies` are (label, pattern) pairs that must MATCH somewhere in the same
    file: the site where the declared number reaches the transport. Splitting
    the two is the whole point. A number with no application site is a control
    that reads as present and is not.
    """

    source: str
    values: tuple[tuple[str, re.Pattern[str], str | None], ...]
    applies: tuple[tuple[str, re.Pattern[str]], ...]


class Inherited(NamedTuple):
    """An SDK that deliberately rides a vendor or transport default.

    `seconds` is the bound it actually gets, and `None` — the transport
    imposes none — is a FAILURE, not a note. `dirs` are scanned to prove the
    SDK declares no deadline of its own: one added there must be promoted to
    `DECLARED` with the site that applies it, or this gate cannot check it.
    """

    transport: str
    seconds: float | None
    note: str
    dirs: tuple[str, ...]


class Pinned(NamedTuple):
    """An SDK on a vendor client that retries by default and must pin it OFF."""

    source: str
    patterns: tuple[tuple[str, re.Pattern[str]], ...]


class NoRetry(NamedTuple):
    """An SDK that builds its own transport and must ship no retry at all."""

    dirs: tuple[str, ...]


# ---------------------------------------------------------------------------
# half one — the deadlines each SDK declares for itself
# ---------------------------------------------------------------------------
# Keyed by SDK, valued by the construct that SDK ACTUALLY uses. There is no
# common spelling to grep for: httpx takes a `Timeout` object, Go a
# `time.Duration` on a transport, URLSession a pair of `TimeInterval`s on a
# configuration, OkHttp millisecond longs, reqwest a `Duration` on a builder,
# Dart a `Duration` applied to a future, httr a seconds count handed to
# libcurl. One regex over ten languages would either match nothing or match
# prose, so each entry names its own.
#
# `values` are (label, pattern, expected) triples. `expected=None` asserts the
# declaration EXISTS; a string asserts group 1 equals it exactly.
#
# Most entries are presence-only ON PURPOSE, and the reason is not laziness.
# The numbers are not comparable across SDKs: Go's 600 s is a time-to-HEADERS
# bound, Rust's is BETWEEN-BYTES, Swift's is a whole-request ceiling, Kotlin's
# 120 000 is an OkHttp socket read in millis and Java's `ofMinutes(10)` a
# whole-exchange deadline. Pinning them all to one literal here would compare
# unlike things and would make this gate the owner of numbers that belong to
# each SDK's own suite, where they are asserted with the semantics attached.
# What THIS gate owns is the property those suites cannot state: that every SDK
# has such a bound at all, and that something applies it.
#
# `applies` are (label, pattern) pairs that must MATCH in the same file: the
# site where the declared number reaches the transport. Splitting the two is
# the point. Measured on this repo: deleting the one Swift line that copies the
# session's bound onto the outgoing request leaves every constant in place and
# silently restores Foundation's 60 s, because a request-level timeout wins
# over the session configuration. A constant nobody wires in is decoration.
DECLARED_TIMEOUTS: dict[str, Declared] = {
    "python": Declared(
        source="sdks/python/nroutersdk/client.py",
        values=(
            (
                "request+connect",
                re.compile(r"^DEFAULT_TIMEOUT\s*=\s*httpx\.Timeout\(", re.M),
                None,
            ),
        ),
        applies=(
            (
                "handed to the vendor client",
                re.compile(r'kwargs\["timeout"\]\s*=\s*DEFAULT_TIMEOUT'),
            ),
        ),
    ),
    "go": Declared(
        source="sdks/go/client.go",
        values=(
            (
                "response-header",
                re.compile(r"\bDefaultResponseHeaderTimeout\s*=\s*\d+\s*\*\s*time\.Second"),
                None,
            ),
            (
                "connect",
                re.compile(r"\bDefaultConnectTimeout\s*=\s*\d+\s*\*\s*time\.Second"),
                None,
            ),
            (
                "body-idle",
                re.compile(r"\bDefaultBodyIdleTimeout\s*=\s*\d+\s*\*\s*time\.Second"),
                None,
            ),
        ),
        applies=(
            (
                "set on the transport",
                re.compile(r"ResponseHeaderTimeout:\s*responseHeaderTimeout"),
            ),
            (
                "wrap response bodies with the idle deadline",
                re.compile(r"res\.Body\s*=\s*newIdleReadCloser\(res\.Body,\s*c\.bodyIdleTimeout,\s*cancel\)"),
            ),
        ),
    ),
    "java": Declared(
        source="sdks/java/src/main/java/ai/nrouter/sdk/NRouterHttpClient.java",
        values=(
            (
                "whole-request",
                re.compile(r"\bDEFAULT_REQUEST_TIMEOUT\s*=\s*Duration\.\w+\("),
                None,
            ),
            (
                "connect",
                re.compile(r"\bDEFAULT_CONNECT_TIMEOUT\s*=\s*Duration\.\w+\("),
                None,
            ),
        ),
        applies=(
            ("set on the request", re.compile(r"\.timeout\(requestTimeout\)")),
            (
                "set on the client",
                re.compile(r"\.connectTimeout\(DEFAULT_CONNECT_TIMEOUT\)"),
            ),
        ),
    ),
    "kotlin": Declared(
        source="sdks/kotlin/src/main/kotlin/ai/nrouter/sdk/NRouter.kt",
        values=(
            ("socket read", re.compile(r"\bREAD_TIMEOUT_MILLIS\s*:\s*Long\s*=\s*[\d_]+"), None),
            (
                "connect",
                re.compile(r"\bCONNECT_TIMEOUT_MILLIS\s*:\s*Long\s*=\s*[\d_]+"),
                None,
            ),
        ),
        applies=(
            ("set on the OkHttp builder", re.compile(r"\.readTimeout\(READ_TIMEOUT_MILLIS")),
            (
                "set on the OkHttp builder",
                re.compile(r"\.connectTimeout\(CONNECT_TIMEOUT_MILLIS"),
            ),
        ),
    ),
    "rust": Declared(
        source="sdks/rust/src/http.rs",
        values=(
            (
                "between-bytes",
                re.compile(r"\bDEFAULT_READ_TIMEOUT\s*:\s*Duration\s*=\s*Duration::from_secs\("),
                None,
            ),
            (
                "connect",
                re.compile(
                    r"\bDEFAULT_CONNECT_TIMEOUT\s*:\s*Duration\s*=\s*Duration::from_secs\("
                ),
                None,
            ),
        ),
        applies=(
            ("set on the reqwest builder", re.compile(r"\.read_timeout\(read_timeout\)")),
            ("set on the reqwest builder", re.compile(r"\.connect_timeout\(connect_timeout\)")),
        ),
    ),
    # The three below pin their VALUES as well as their constructs. Each is a
    # bare literal in a single unit this gate can compare without knowing a
    # framework's unit convention, and each SDK's own suite asserts the same
    # number, so the two cannot drift apart silently.
    "swift": Declared(
        source="sdks/swift/Sources/NRouter/NRouter.swift",
        values=(
            (
                "between-bytes",
                re.compile(r"\bdefaultRequestTimeout\s*:\s*TimeInterval\s*=\s*([0-9_]+)"),
                "180",
            ),
            (
                "buffered whole-request",
                re.compile(r"\bdefaultResourceTimeout\s*:\s*TimeInterval\s*=\s*([0-9_]+)"),
                "600",
            ),
            (
                "streaming backstop",
                re.compile(
                    r"\bdefaultStreamingResourceTimeout\s*:\s*TimeInterval\s*=\s*([0-9_]+)"
                ),
                "86_400",
            ),
        ),
        applies=(
            (
                "set on the session configuration",
                re.compile(r"timeoutIntervalForRequest\s*=\s*defaultRequestTimeout"),
            ),
            (
                "copied onto the outgoing request",
                # URLRequest(url:) starts at Foundation's 60 s and a
                # request-level timeout WINS over the session configuration, so
                # without this line every constant above is set and unused.
                re.compile(
                    r"request\.timeoutInterval\s*=\s*session\.configuration\.timeoutIntervalForRequest"
                ),
            ),
        ),
    ),
    "dart": Declared(
        source="sdks/dart/lib/src/client.dart",
        values=(
            (
                "buffered whole-request",
                re.compile(r"\bdefaultTimeout\s*=\s*Duration\(seconds:\s*(\d+)\)"),
                "600",
            ),
            (
                "time-to-headers",
                re.compile(r"\bdefaultStreamTimeout\s*=\s*Duration\(seconds:\s*(\d+)\)"),
                "180",
            ),
            (
                "body-idle",
                re.compile(r"\bdefaultBodyIdleTimeout\s*=\s*Duration\(seconds:\s*(\d+)\)"),
                "130",
            ),
        ),
        applies=(
            # package:http's Client interface carries no timeout at all, so the
            # bound has to be applied to the FUTURE. Both names must appear:
            # one applied and the other merely declared is the shape where
            # streaming silently keeps the unbounded default.
            ("buffered bound applied", re.compile(r"\.timeout\(\s*timeout\s*,")),
            ("stream bound applied", re.compile(r"\.timeout\(\s*\n?\s*streamTimeout\s*,")),
            (
                "body-idle bound applied",
                re.compile(r"response\.stream\.timeout\(\s*bodyIdleTimeout\s*,"),
            ),
        ),
    ),
    "r": Declared(
        source="sdks/r/R/client.R",
        values=(
            (
                "buffered whole-request",
                re.compile(r"^nrouter_default_timeout_seconds\s*<-\s*function\(\)\s*(\d+)", re.M),
                "600",
            ),
            (
                "connect",
                re.compile(
                    r"^nrouter_default_connect_timeout_seconds\s*<-\s*function\(\)\s*(\d+)",
                    re.M,
                ),
                "10",
            ),
            (
                "transfer stall",
                re.compile(
                    r"^nrouter_default_stream_idle_seconds\s*<-\s*function\(\)\s*(\d+)", re.M
                ),
                "180",
            ),
        ),
        applies=(
            ("handed to httr", re.compile(r"httr::timeout\(nrouter_timeout_seconds\(client\)\)")),
            (
                "stall bound handed to libcurl",
                re.compile(r"low_speed_time\s*=\s*nrouter_stream_idle_seconds\(client\)"),
            ),
        ),
    ),
}

# Application sites that live outside an SDK's declaration file. Keeping them
# explicit prevents a shared helper from being perfectly bounded while one
# public path quietly bypasses it.
AUXILIARY_TIMEOUT_APPLICATIONS: tuple[
    tuple[str, str, str, re.Pattern[str], int], ...
] = (
    (
        "go",
        "sdks/go/stream.go",
        "route streaming responses through the body-idle helper",
        re.compile(r"res,\s*err\s*:=\s*c\.doHTTP\(req\)"),
        1,
    ),
    (
        "dart",
        "sdks/dart/lib/src/client.dart",
        "wrap its SSE response with the body-idle helper",
        re.compile(r"response\s*=\s*_withBodyIdleTimeout\("),
        1,
    ),
    (
        "dart",
        "sdks/dart/lib/src/client.dart",
        "wrap multipart response bodies with the body-idle helper",
        re.compile(r"final boundedMultipartResponse\s*=\s*_withBodyIdleTimeout\("),
        1,
    ),
    (
        "dart",
        "sdks/dart/lib/src/client.dart",
        "wrap binary response bodies with the body-idle helper",
        re.compile(r"final boundedBinaryResponse\s*=\s*_withBodyIdleTimeout\("),
        1,
    ),
)


# ---------------------------------------------------------------------------
# half two — the SDKs that declare none of their own
# ---------------------------------------------------------------------------
# Named, with the bound each one actually gets, so "it inherits a sensible
# default" is a claim with a number attached rather than a shrug. Two checks
# follow from an entry here, and both matter:
#
#   * `seconds=None` — the transport imposes NO bound — is a FAILURE. Riding a
#     transport is a decision about which bound applies, never a way to have
#     none. This registry cannot be used to license an unbounded SDK.
#   * the SDK must still declare nothing of its own. A deadline added to one of
#     these must move into DECLARED_TIMEOUTS with the site that applies it, or
#     it goes unchecked forever — the hole a registry-only gate always has.
INHERITED_TIMEOUTS: dict[str, Inherited] = {
    "js": Inherited(
        transport="the openai-node vendor client",
        seconds=600.0,
        note="every request goes through the vendor pipeline, so the vendor's own "
        "600 s default applies and a caller's `timeout` option overrides it",
        dirs=("sdks/js/src",),
    ),
    "android": Inherited(
        transport="the shared sdks/kotlin client",
        seconds=120.0,
        note="delegates every wire concern to sdks/kotlin, whose socket read bound "
        "is the one in force here",
        dirs=("sdks/android/src/main",),
    ),
}


# ---------------------------------------------------------------------------
# half three — nobody re-sends a billed request
# ---------------------------------------------------------------------------
RETRY_PINNED: dict[str, Pinned] = {
    "python": Pinned(
        source="sdks/python/nroutersdk/client.py",
        patterns=(
            ("retries pinned to zero", re.compile(r"^DEFAULT_MAX_RETRIES\s*=\s*0\s*$", re.M)),
            (
                "the pin reaches the vendor client",
                re.compile(r'kwargs\.setdefault\(\s*"max_retries",\s*DEFAULT_MAX_RETRIES\s*\)'),
            ),
        ),
    ),
    "js": Pinned(
        source="sdks/js/src/client.ts",
        patterns=(
            ("client-level retries pinned to zero", re.compile(r"\bDEFAULT_MAX_RETRIES\s*=\s*0\b")),
            (
                "non-GET forced to zero retries",
                re.compile(
                    r"req\.method\s*===\s*'GET'\s*\?\s*\{\}\s*:\s*\{\s*maxRetries:\s*0\s*\}"
                ),
            ),
        ),
    ),
}

# Everything else builds its own transport and must ship no retry construct at
# all. Listed explicitly so a retry loop added to one of them fails here rather
# than shipping in a published package.
RETRY_FREE: dict[str, NoRetry] = {
    "go": NoRetry(dirs=("sdks/go",)),
    "swift": NoRetry(dirs=("sdks/swift/Sources",)),
    "dart": NoRetry(dirs=("sdks/dart/lib",)),
    "r": NoRetry(dirs=("sdks/r/R",)),
    "rust": NoRetry(dirs=("sdks/rust/src",)),
    "java": NoRetry(dirs=("sdks/java/src/main",)),
    "kotlin": NoRetry(dirs=("sdks/kotlin/src/main",)),
    "android": NoRetry(dirs=("sdks/android/src/main",)),
}

# What a client-side retry LOOKS like, narrowly.
#
# Narrow in BOTH directions, deliberately. Every SDK here ships `isRetryable` /
# `is_retryable` / `retry_after` — advertising to the CALLER that a failure is
# transient is the opposite of retrying it yourself, and flagging those would
# make the gate unusable within a day. A pin of ZERO is likewise not a retry;
# it is the fix. So what follows is a retry SETTING with a NON-ZERO value, or an
# actual attempt LOOP. Comment lines are stripped first, since every one of
# these files discusses retries at length.
RETRY_CONSTRUCTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("a non-zero retry setting", re.compile(r"\bmax_?[Rr]etries\b\s*[:=]{1,2}\s*[1-9]")),
    (
        "a retry-count setting",
        re.compile(
            r"\b(?:retryCount|retry_count|maxAttempts|max_attempts)\b\s*[:=]{1,2}\s*[1-9]"
        ),
    ),
    (
        "a retry policy object",
        re.compile(r"\b(?:RetryPolicy|RetryInterceptor|retryMiddleware|retryWhen)\b"),
    ),
    ("a retry helper call", re.compile(r"(?<![A-Za-z_])\.retry\s*\(")),
    ("an attempt loop", re.compile(r"\bfor\s+attempt\s+in\s+range\s*\(")),
    ("an attempt loop", re.compile(r"\bwhile\s*\(?\s*attempts?\s*[<!]")),
)

# Comment prefixes across the languages this file scans line-by-line, so prose
# about retries — and a doc comment quoting another SDK's timeout — never trips
# either scan. Python is absent on purpose: it is checked whole-file by pattern
# and never line-scanned, so its triple-quoted docstrings need no entry.
COMMENT_PREFIXES = ("//", "#", "*", "/*", "///", "--", "%")

SOURCE_SUFFIXES = {
    ".py", ".ts", ".js", ".go", ".java", ".kt", ".kts", ".swift", ".rs",
    ".dart", ".R", ".r",
}
SKIP_PARTS = {
    "node_modules", ".git", "target", "build", "dist", ".dart_tool",
    "test", "tests", "__pycache__", "generated",
}


def _iter_sources(root: Path, rel_dir: str) -> list[Path]:
    base = root / rel_dir
    if base.is_file():
        return [base]
    if not base.is_dir():
        return []
    out = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        if SKIP_PARTS & set(path.relative_to(root).parts):
            continue
        out.append(path)
    return out


def _is_comment(line: str) -> bool:
    stripped = line.strip()
    return any(stripped.startswith(prefix) for prefix in COMMENT_PREFIXES)


def _sdk_dirs(root: Path) -> set[str]:
    base = root / "sdks"
    if not base.is_dir():
        return set()
    return {d.name for d in base.iterdir() if d.is_dir() and not d.name.startswith(".")}


def check_client_timeouts(root: Path = ROOT) -> list[str]:
    """Return a list of failure strings; empty means every SDK is accounted for."""
    failures: list[str] = []

    # --- every SDK on disk is in exactly one timeout registry ---------------
    # Without this a new SDK ships with no deadline and no gate notices, which
    # is how the three fixed here got in.
    on_disk = _sdk_dirs(root)
    registered = set(DECLARED_TIMEOUTS) | set(INHERITED_TIMEOUTS)
    if not on_disk:
        failures.append("sdks/ contains no SDK directories — a vanished tree is not a pass")
    for sdk in sorted(on_disk - registered):
        failures.append(
            f"{sdk}: present under sdks/ but in neither DECLARED_TIMEOUTS nor "
            f"INHERITED_TIMEOUTS. Register the deadline it declares, or the "
            f"transport default it rides and the bound that gives it."
        )
    for sdk in sorted(registered - on_disk):
        failures.append(
            f"{sdk}: registered here but absent from sdks/ — a vanished SDK must "
            f"not read as passing"
        )
    for sdk in sorted(set(DECLARED_TIMEOUTS) & set(INHERITED_TIMEOUTS)):
        failures.append(f"{sdk}: registered as BOTH declaring and inheriting its deadlines")

    # --- declared deadlines: the value AND a site that applies it -----------
    for sdk, rule in sorted(DECLARED_TIMEOUTS.items()):
        path = root / rule.source
        if not path.is_file():
            failures.append(
                f"{sdk}: {rule.source} is missing — its deadlines cannot be checked"
            )
            continue
        text = path.read_text(errors="replace")
        for label, pattern, expected in rule.values:
            match = pattern.search(text)
            if match is None:
                failures.append(
                    f"{rule.source}: {sdk} declares no {label} timeout. Either the "
                    f"declaration moved (update DECLARED_TIMEOUTS) or it was removed, "
                    f"which puts this SDK back on its transport's default — 60 s, "
                    f"10 s or forever, depending on the transport."
                )
                continue
            if expected is None:
                continue
            found = match.group(1)
            if found != expected:
                failures.append(
                    f"{rule.source}: {sdk}'s {label} timeout is {found}, not {expected}. "
                    f"Change the expected value here in the same commit, with the "
                    f"reason: a client deadline below the gateway's ~410 s worst "
                    f"honest case aborts a request the customer is billed for anyway."
                )
        for label, pattern in rule.applies:
            if pattern.search(text) is None:
                failures.append(
                    f"{rule.source}: {sdk} declares its timeouts but the site that "
                    f"applies them ({label}) is gone. A constant nobody wires in is "
                    f"decoration and the transport default is back in force."
                )

    for sdk, source, label, pattern, minimum in AUXILIARY_TIMEOUT_APPLICATIONS:
        path = root / source
        if not path.is_file():
            failures.append(f"{source}: {sdk} timeout application file is missing")
            continue
        matches = pattern.findall(path.read_text(errors="replace"))
        if len(matches) < minimum:
            failures.append(
                f"{source}: {sdk} does not {label}. The shared timeout helper "
                f"exists, but this public path bypasses it ({len(matches)}/{minimum} sites)."
            )

    # --- inherited deadlines: they must still declare NONE ------------------
    for sdk, rule in sorted(INHERITED_TIMEOUTS.items()):
        seen_any = False
        for rel_dir in rule.dirs:
            sources = _iter_sources(root, rel_dir)
            seen_any = seen_any or bool(sources)
            for path in sources:
                text = path.read_text(errors="replace")
                for index, line in enumerate(text.splitlines(), start=1):
                    if _is_comment(line):
                        continue
                    for other, other_rule in DECLARED_TIMEOUTS.items():
                        for label, pattern, _ in other_rule.values:
                            if pattern.search(line):
                                failures.append(
                                    f"{path.relative_to(root)}:{index}: {sdk} is "
                                    f"registered as inheriting {rule.transport}'s "
                                    f"deadline, but declares one of its own "
                                    f"({other}-shaped {label}). Move it into "
                                    f"DECLARED_TIMEOUTS with its value so this gate "
                                    f"can check it."
                                )
        if not seen_any:
            failures.append(
                f"{sdk}: none of {list(rule.dirs)} contain readable source — an SDK "
                f"that vanished must not read as passing"
            )
        if rule.seconds is None:
            failures.append(
                f"{sdk}: registered as inheriting {rule.transport}, which imposes NO "
                f"bound at all ({rule.note}). Inheriting is a decision about WHICH "
                f"bound applies, never a way to have none: declare one in this SDK "
                f"and move it to DECLARED_TIMEOUTS."
            )

    # --- the money half: no client-side retry on a billed request -----------
    retry_registered = set(RETRY_PINNED) | set(RETRY_FREE)
    for sdk in sorted(on_disk - retry_registered):
        failures.append(
            f"{sdk}: present under sdks/ but in neither RETRY_PINNED nor RETRY_FREE. "
            f"Say whether it pins a vendor client's retries off or ships no retry at "
            f"all — a retry of a billed POST is a second call and a second bill."
        )

    for sdk, pinned in sorted(RETRY_PINNED.items()):
        path = root / pinned.source
        if not path.is_file():
            failures.append(
                f"{sdk}: {pinned.source} is missing — its retry pin cannot be checked"
            )
            continue
        text = path.read_text(errors="replace")
        for label, pattern in pinned.patterns:
            if pattern.search(text) is None:
                failures.append(
                    f"{pinned.source}: {sdk} no longer pins its vendor client's "
                    f"retries off ({label}). The vendor default is TWO automatic "
                    f"retries on 408, 409, 429 and every 5xx — on non-idempotent, "
                    f"already-billed POSTs, with nothing for the gateway to dedupe "
                    f"the second call against."
                )

    for sdk, rule in sorted(RETRY_FREE.items()):
        seen_any = False
        for rel_dir in rule.dirs:
            sources = _iter_sources(root, rel_dir)
            seen_any = seen_any or bool(sources)
            for path in sources:
                text = path.read_text(errors="replace")
                for index, line in enumerate(text.splitlines(), start=1):
                    if _is_comment(line):
                        continue
                    for label, pattern in RETRY_CONSTRUCTS:
                        if pattern.search(line):
                            failures.append(
                                f"{path.relative_to(root)}:{index}: {sdk} is registered "
                                f"as shipping no client-side retry, but this line is "
                                f"{label}. The gateway reserves credit ONCE per "
                                f"customer request and owns retry and failover; a "
                                f"client retry of a billed non-GET is a second call "
                                f"and a second bill."
                            )
                            break
        if not seen_any:
            failures.append(
                f"{sdk}: none of {list(rule.dirs)} contain readable source — an SDK "
                f"that vanished must not read as passing"
            )

    return failures


# ---------------------------------------------------------------------------
# self-test — plant each violation and assert the gate reports it
# ---------------------------------------------------------------------------

_CLEAN: dict[str, str] = {
    "sdks/python/nroutersdk/client.py": (
        "DEFAULT_MAX_RETRIES = 0\n"
        "DEFAULT_TIMEOUT = httpx.Timeout(600.0, connect=10.0)\n"
        "def _apply(kwargs):\n"
        '    kwargs.setdefault("max_retries", DEFAULT_MAX_RETRIES)\n'
        '    kwargs["timeout"] = DEFAULT_TIMEOUT\n'
    ),
    "sdks/go/client.go": (
        "package nrouter\n"
        "const (\n"
        "\tDefaultConnectTimeout = 10 * time.Second\n"
        "\tDefaultResponseHeaderTimeout = 600 * time.Second\n"
        "\tDefaultBodyIdleTimeout = 120 * time.Second\n"
        ")\n"
        "var t = &http.Transport{ResponseHeaderTimeout: responseHeaderTimeout}\n"
        "func apply() { res.Body = newIdleReadCloser(res.Body, c.bodyIdleTimeout, cancel) }\n"
    ),
    "sdks/go/stream.go": (
        "package nrouter\n"
        "func stream() { res, err := c.doHTTP(req) }\n"
    ),
    "sdks/java/src/main/java/ai/nrouter/sdk/NRouterHttpClient.java": (
        "public static final Duration DEFAULT_CONNECT_TIMEOUT = Duration.ofSeconds(15);\n"
        "public static final Duration DEFAULT_REQUEST_TIMEOUT = Duration.ofMinutes(10);\n"
        "HttpClient.newBuilder().connectTimeout(DEFAULT_CONNECT_TIMEOUT).build();\n"
        "return request(path).timeout(requestTimeout);\n"
    ),
    "sdks/kotlin/src/main/kotlin/ai/nrouter/sdk/NRouter.kt": (
        "public const val CONNECT_TIMEOUT_MILLIS: Long = 15_000\n"
        "public const val READ_TIMEOUT_MILLIS: Long = 120_000\n"
        "    .connectTimeout(CONNECT_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS)\n"
        "    .readTimeout(READ_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS)\n"
    ),
    "sdks/rust/src/http.rs": (
        "pub const DEFAULT_CONNECT_TIMEOUT: Duration = Duration::from_secs(10);\n"
        "pub const DEFAULT_READ_TIMEOUT: Duration = Duration::from_secs(600);\n"
        "reqwest::Client::builder()\n"
        "    .connect_timeout(connect_timeout)\n"
        "    .read_timeout(read_timeout)\n"
    ),
    "sdks/swift/Sources/NRouter/NRouter.swift": (
        "public static let defaultRequestTimeout: TimeInterval = 180\n"
        "public static let defaultResourceTimeout: TimeInterval = 600\n"
        "public static let defaultStreamingResourceTimeout: TimeInterval = 86_400\n"
        "configuration.timeoutIntervalForRequest = defaultRequestTimeout\n"
        "request.timeoutInterval = session.configuration.timeoutIntervalForRequest\n"
    ),
    "sdks/dart/lib/src/client.dart": (
        "static const Duration defaultTimeout = Duration(seconds: 600);\n"
        "static const Duration defaultStreamTimeout = Duration(seconds: 180);\n"
        "static const Duration defaultBodyIdleTimeout = Duration(seconds: 130);\n"
        "final b = response.stream.timeout(bodyIdleTimeout, onTimeout: fail);\n"
        "final r = await f.timeout(timeout, onTimeout: fail);\n"
        "final s = await g.timeout(streamTimeout, onTimeout: fail);\n"
        "response = _withBodyIdleTimeout(s);\n"
        "final boundedMultipartResponse = _withBodyIdleTimeout(s);\n"
        "final boundedBinaryResponse = _withBodyIdleTimeout(s);\n"
    ),
    "sdks/r/R/client.R": (
        "nrouter_default_timeout_seconds <- function() 600\n"
        "nrouter_default_connect_timeout_seconds <- function() 10\n"
        "nrouter_default_stream_idle_seconds <- function() 180\n"
        "cfg <- httr::timeout(nrouter_timeout_seconds(client))\n"
        "opt <- low_speed_time = nrouter_stream_idle_seconds(client)\n"
    ),
    "sdks/js/src/client.ts": (
        "export const DEFAULT_MAX_RETRIES = 0;\n"
        "const options = {\n"
        "  ...(req.method === 'GET' ? {} : { maxRetries: 0 }),\n"
        "};\n"
    ),
    "sdks/android/src/main/Stub.kt": "class Stub\n",
}


def _fixture(tmp: Path, **overrides: str) -> Path:
    root = tmp / "repo"
    files = dict(_CLEAN)
    files.update({key.replace("__", "/"): value for key, value in overrides.items()})
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


SWIFT = "sdks/swift/Sources/NRouter/NRouter.swift"
DART = "sdks/dart/lib/src/client.dart"
RLANG = "sdks/r/R/client.R"
PY = "sdks/python/nroutersdk/client.py"
JS = "sdks/js/src/client.ts"
ANDROID = "sdks/android/src/main/Stub.kt"


def _with(tmp: Path, rel: str, text: str) -> Path:
    """A fixture with one file replaced. Keyword names cannot hold slashes."""
    root = _fixture(tmp)
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return root


def self_test() -> int:
    import tempfile

    problems: list[str] = []

    if check_client_timeouts():
        problems.append(
            "baseline is not green against the real repository; fix the SDKs first"
        )

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)

        # 1. a clean fixture must pass, or every case below proves nothing.
        found = check_client_timeouts(_fixture(tmp / "a"))
        if found:
            problems.append(f"clean fixture reported failures: {found}")

        # 2. a REMOVED declaration must be reported. This is the regression the
        #    whole file exists for: delete the line and the SDK silently falls
        #    back to its transport's default — 60 s, or forever.
        found = check_client_timeouts(
            _with(
                tmp / "b",
                DART,
                "static const Duration defaultStreamTimeout = Duration(seconds: 180);\n"
                "final s = await g.timeout(streamTimeout, onTimeout: fail);\n"
                "final r = await f.timeout(timeout, onTimeout: fail);\n",
            )
        )
        if not any("declares no buffered whole-request timeout" in f for f in found):
            problems.append(f"a removed Dart timeout declaration NOT reported: {found}")

        # 2b. ...in a presence-only SDK too, where there is no value to compare
        #     and the declaration's absence is the entire signal.
        found = check_client_timeouts(
            _with(tmp / "b2", PY, "DEFAULT_MAX_RETRIES = 0\n")
        )
        if not any("declares no request+connect timeout" in f for f in found):
            problems.append(f"a removed Python timeout declaration NOT reported: {found}")

        # 3. a DRIFTED value must be reported. 60 s is the exact number
        #    URLSession.shared imposed, and it is BELOW the gateway's own worst
        #    honest case — so the drift that matters most is a silent shrink,
        #    not a missing line.
        found = check_client_timeouts(
            _with(
                tmp / "c",
                SWIFT,
                _CLEAN[SWIFT].replace("TimeInterval = 600", "TimeInterval = 60"),
            )
        )
        if not any("timeout is 60, not 600" in f for f in found):
            problems.append(f"a drifted Swift timeout value NOT reported: {found}")

        # 4. a declaration that is still there while the site APPLYING it is
        #    gone must be reported. Measured on the real SDK: deleting the line
        #    that copies the session's bound onto the outgoing request leaves
        #    every constant in place and restores Foundation's 60 s.
        found = check_client_timeouts(
            _with(
                tmp / "d",
                SWIFT,
                _CLEAN[SWIFT].replace(
                    "request.timeoutInterval = session.configuration.timeoutIntervalForRequest\n",
                    "",
                ),
            )
        )
        if not any("the site that applies them" in f for f in found):
            problems.append(f"an unwired Swift timeout constant NOT reported: {found}")

        # 4b. the same for R, where the constants are accessor functions and the
        #     application site is the one `httr::timeout()` call. Three functions
        #     returning three numbers that reach no request is exactly what this
        #     package shipped before.
        found = check_client_timeouts(
            _with(
                tmp / "d2",
                RLANG,
                _CLEAN[RLANG].replace(
                    "cfg <- httr::timeout(nrouter_timeout_seconds(client))\n", ""
                ),
            )
        )
        if not any("the site that applies them" in f for f in found):
            problems.append(f"an unwired R timeout constant NOT reported: {found}")

        # 4c. Go needs an SDK-owned wrapper because net/http has no response
        #     body idle setting. A declared constant without that wrapper is
        #     the exact post-header hang this gate is meant to catch.
        go = "sdks/go/client.go"
        found = check_client_timeouts(
            _with(
                tmp / "d3",
                go,
                _CLEAN[go].replace(
                    "func apply() { res.Body = newIdleReadCloser(res.Body, c.bodyIdleTimeout, cancel) }\n",
                    "",
                ),
            )
        )
        if not any("the site that applies them" in f for f in found):
            problems.append(f"an unwired Go body-idle deadline NOT reported: {found}")

        # 4d. The streaming path must go through the same helper. Checking only
        #     the helper would let SSE regress while buffered responses stayed
        #     bounded.
        go_stream = "sdks/go/stream.go"
        found = check_client_timeouts(
            _with(
                tmp / "d4",
                go_stream,
                _CLEAN[go_stream].replace("res, err := c.doHTTP(req)", "res, err := c.http.Do(req)"),
            )
        )
        if not any("public path bypasses it" in f for f in found):
            problems.append(f"an unbounded Go streaming body NOT reported: {found}")

        # 4e. Multipart and binary reads are separate paths; both must retain
        #     the body-idle wrapper even though they share the same helper.
        found = check_client_timeouts(
            _with(
                tmp / "d5",
                DART,
                _CLEAN[DART].replace(
                    "final boundedBinaryResponse = _withBodyIdleTimeout(s);\n",
                    "",
                ),
            )
        )
        if not any("wrap binary response bodies" in f for f in found):
            problems.append(f"an unbounded Dart response body NOT reported: {found}")

        # 4f. SSE has a distinct assignment shape from buffered response bodies.
        found = check_client_timeouts(
            _with(
                tmp / "d6",
                DART,
                _CLEAN[DART].replace(
                    "response = _withBodyIdleTimeout(s);\n",
                    "",
                ),
            )
        )
        if not any("wrap its SSE response" in f for f in found):
            problems.append(f"an unbounded Dart SSE body NOT reported: {found}")

        # 5. a timeout APPEARING in an SDK registered as inheriting one must be
        #    reported — the hole a registry-only gate always has, and the reason
        #    half two exists.
        found = check_client_timeouts(
            _with(
                tmp / "e",
                ANDROID,
                "class Stub\n"
                "public const val READ_TIMEOUT_MILLIS: Long = 5_000\n",
            )
        )
        if not any("declares one of its own" in f for f in found):
            problems.append(f"a new timeout in an inheriting SDK NOT reported: {found}")

        # 6. ...but PROSE about a timeout is not a declaration, and flagging it
        #    would make the gate unusable — every one of these files documents
        #    its numbers at length, and several quote another SDK's.
        found = check_client_timeouts(
            _with(
                tmp / "f",
                ANDROID,
                "class Stub\n"
                "// public const val READ_TIMEOUT_MILLIS: Long = 5_000 is kotlin's\n"
                "/** nrouter_default_timeout_seconds <- function() 600 */\n"
                " * static const Duration defaultTimeout = Duration(seconds: 600);\n",
            )
        )
        if found:
            problems.append(f"a doc comment was misread as a declaration: {found}")

        # 7. a LOST retry pin must be reported. The vendor default is two
        #    automatic retries on already-billed POSTs; losing the pin is a
        #    money defect no test in that SDK would catch, because nothing about
        #    a successful response changes.
        found = check_client_timeouts(
            _with(
                tmp / "g",
                PY,
                _CLEAN[PY].replace("DEFAULT_MAX_RETRIES = 0", "DEFAULT_MAX_RETRIES = 2"),
            )
        )
        if not any("no longer pins its vendor client's retries off" in f for f in found):
            problems.append(f"a lost Python retry pin NOT reported: {found}")

        # 8. ...and the JS pin has its own shape: forced to zero on non-GET
        #    only, because re-reading /models costs nothing.
        found = check_client_timeouts(
            _with(tmp / "h", JS, "const options = { maxRetries: 2 };\n")
        )
        if not any("no longer pins its vendor client's retries off" in f for f in found):
            problems.append(f"a lost JS retry pin NOT reported: {found}")

        # 9. a retry ADDED to an SDK registered as retry-free must be reported.
        found = check_client_timeouts(
            _with(tmp / "i", DART, _CLEAN[DART] + "final maxRetries = 3;\n")
        )
        if not any("a non-zero retry setting" in f for f in found):
            problems.append(f"a planted retry setting NOT reported: {found}")

        # 10. ...including an attempt LOOP, which carries no `retries` name at
        #     all and is the shape a hand-written retry actually takes.
        found = check_client_timeouts(
            _with(tmp / "j", RLANG, _CLEAN[RLANG] + "for attempt in range(3):\n")
        )
        if not any("an attempt loop" in f for f in found):
            problems.append(f"a planted retry loop NOT reported: {found}")

        # 11. ...but `is_retryable` and `retry_after` are the OPPOSITE of
        #     retrying: they hand the caller the decision. Every SDK ships them,
        #     so flagging them would make the gate unusable within a day. A pin
        #     of ZERO is likewise not a retry.
        found = check_client_timeouts(
            _with(
                tmp / "k",
                RLANG,
                _CLEAN[RLANG]
                + "nrouter_is_retryable <- function(cond) TRUE\n"
                + "retry_after <- 3\n"
                + "maxRetries = 0\n",
            )
        )
        if found:
            problems.append(f"retry ADVERTISING was misread as retrying: {found}")

        # 12. a NEW SDK must fail until it is registered in BOTH registries —
        #     otherwise the first thing an eleventh SDK ships is an unbounded
        #     wait and a vendor retry that nobody looked at.
        root = _fixture(tmp / "l")
        (root / "sdks/elixir/lib").mkdir(parents=True)
        (root / "sdks/elixir/lib/client.ex").write_text("defmodule NRouter do end\n")
        found = check_client_timeouts(root)
        if not any("in neither DECLARED_TIMEOUTS nor INHERITED_TIMEOUTS" in f for f in found):
            problems.append(f"an unregistered new SDK NOT reported (timeouts): {found}")
        if not any("in neither RETRY_PINNED nor RETRY_FREE" in f for f in found):
            problems.append(f"an unregistered new SDK NOT reported (retries): {found}")

        # 13. a vanished SDK source must ERROR rather than read as passing.
        root = _fixture(tmp / "m")
        (root / RLANG).unlink()
        found = check_client_timeouts(root)
        if not any("is missing" in f for f in found):
            problems.append(f"a vanished SDK source did not fail the check: {found}")

        # 14. an SDK registered as inheriting a transport that imposes NO bound
        #     must FAIL. Every entry in the shipped registry names a real bound,
        #     so the branch is unreachable from the tree — it is exercised here
        #     against a temporary entry, because an unexercised refusal is not a
        #     refusal, and this one is the exemption that would eat the gate.
        original = dict(INHERITED_TIMEOUTS)
        try:
            INHERITED_TIMEOUTS["android"] = Inherited(
                transport="a transport with no default",
                seconds=None,
                note="planted by the self-test",
                dirs=("sdks/android/src/main",),
            )
            found = check_client_timeouts(_fixture(tmp / "n"))
        finally:
            INHERITED_TIMEOUTS.clear()
            INHERITED_TIMEOUTS.update(original)
        if not any("imposes NO bound at all" in f for f in found):
            problems.append(f"an unbounded inherited transport NOT refused: {found}")
        if check_client_timeouts():
            problems.append("the self-test left the registry mutated")

    if problems:
        for problem in problems:
            print(f"SELF-TEST FAIL {problem}")
        return 1
    print("OK  client_timeouts self-test: 20 planted cases, all reported")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    failures = check_client_timeouts()
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        print(f"\n{len(failures)} client-behaviour defect(s)")
        return 1
    print(
        f"OK  {len(DECLARED_TIMEOUTS)} SDK(s) declare their own deadlines; "
        f"{len(INHERITED_TIMEOUTS)} ride a transport default; "
        f"{len(RETRY_PINNED)} pin a vendor client's retries off and "
        f"{len(RETRY_FREE)} ship no retry at all"
    )
    for sdk, rule in sorted(INHERITED_TIMEOUTS.items()):
        bound = "NO BOUND" if rule.seconds is None else f"{rule.seconds:g}s"
        print(f"    inherits  {sdk:<8} {bound:<8} from {rule.transport} — {rule.note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
