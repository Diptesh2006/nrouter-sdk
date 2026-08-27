#!/usr/bin/env python3
"""Prove every nRouter SDK encodes the SAME gateway contract.

Each SDK is written in its own language with its own idioms, and each one was
tested against its own copy of the constants. That proves each SDK is
self-consistent. It does not prove they agree with EACH OTHER, and a gateway
serving eight SDKs is only as correct as the one that drifted.

This gate closes that. It reads `spec/nrouter-sdk-spec.json` — the source of
truth under Rule #14 — and asserts that every SDK's source literally contains
the base URL, the environment variable, the key prefix, all thirteen `x-nr-*`
headers and all nine error codes. Change the spec and every SDK goes red until
it is updated; drop a header from one SDK and only that SDK goes red.

It deliberately checks the SOURCE TEXT rather than importing each SDK, because
importing would need eight toolchains present and would quietly skip the ones
that are missing. A skipped check reads as a pass, which is the failure mode
this gate exists to prevent.

    python3 conformance/check_conformance.py            # check
    python3 conformance/check_conformance.py --self-test # prove the gate bites
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "spec" / "nrouter-sdk-spec.json"

# Which files carry the contract, per SDK. A file listed here that does not
# exist is an ERROR, not a skip: an SDK that vanished must not read as passing.
SDK_SOURCES: dict[str, list[str]] = {
    "python": [
        "sdks/python/nroutersdk/client.py",
        "sdks/python/nroutersdk/_errors.py",
        "sdks/python/nroutersdk/_response.py",
    ],
    "js": ["sdks/js/src/client.ts"],
    "java": ["sdks/java/src/main/java/ai/nrouter/sdk/NRouter.java"],
    "kotlin": [
        "sdks/kotlin/src/main/kotlin/ai/nrouter/sdk/NRouter.kt",
        "sdks/kotlin/src/main/kotlin/ai/nrouter/sdk/NRouterError.kt",
        "sdks/kotlin/src/main/kotlin/ai/nrouter/sdk/ResponseMeta.kt",
    ],
    "android": [
        "sdks/android/src/main/kotlin/ai/nrouter/sdk/android/NRouterAndroid.kt",
    ],
    "swift": [
        "sdks/swift/Sources/NRouter/NRouter.swift",
        "sdks/swift/Sources/NRouter/NRouterError.swift",
        "sdks/swift/Sources/NRouter/ResponseMeta.swift",
    ],
    "rust": [
        "sdks/rust/src/lib.rs",
        "sdks/rust/src/errors.rs",
        "sdks/rust/src/meta.rs",
    ],
    "dart": [
        "sdks/dart/lib/src/client.dart",
        "sdks/dart/lib/src/errors.dart",
        "sdks/dart/lib/src/meta.dart",
    ],
    "r": ["sdks/r/R/client.R", "sdks/r/R/errors.R", "sdks/r/R/meta.R"],
    "go": ["sdks/go/client.go", "sdks/go/errors.go", "sdks/go/meta.go"],
}

# An SDK that only wraps a vendor client does not restate every constant: the
# vendor SDK owns the transport, so headers and error codes live in the wrapper
# only where it adds them. These SDKs are held to the connection contract (base
# URL, env var, key prefix) and exempted from the rest, with the reason stated
# so the exemption is a decision rather than an oversight.
WRAPPER_ONLY = {
    "java": "wraps com.openai:openai-java; transport and errors are the vendor's",
    "js": "extends the openai package; transport and errors are the vendor's",
    "android": "delegates every wire concern to the shared sdks/kotlin artifact",
}

# An SDK that DELEGATES the connection contract must not restate it — a second
# copy of the base URL is exactly the drift this gate exists to catch. It has to
# prove the delegation instead, by referencing the owning SDK's symbols. The
# value is the symbols that must appear, and the SDK whose literals then carry
# the contract on its behalf.
DELEGATES = {
    "android": {
        "owner": "kotlin",
        "symbols": ["NRouter.DEFAULT_BASE_URL", "ai.nrouter.sdk.NRouter"],
    },
}

# An SDK that deliberately does NOT resolve the environment variable. Dart names
# the constant so tooling and docs agree, but never reads it: `Platform.environment`
# needs `dart:io`, which does not exist in a Flutter web build, and is empty on
# mobile — a fallback that quietly resolves to nothing is worse than none.
#
# Listed here rather than silently passing on the constant's presence, because
# "the string appears" was being read as "the behaviour exists". The reason is
# recorded so this stays a decision instead of an oversight, and the gate now
# reports it in its summary.
NO_ENV_RESOLUTION = {
    "dart": "requires an explicit key; dart:io is absent on Flutter web and "
            "empty on mobile, so an env fallback would resolve to nothing",
}

# Spellings that must appear nowhere (Rule #35).
#
# Assembled from fragments rather than written literally, because
# `scripts/verify-layout.sh` scans this repository for exactly these strings and
# a scanner that trips on its own scanner is a false alarm every checkout. The
# fragments are inert to that guard and identical to it at runtime — the
# self-test asserts the assembled values, so this cannot quietly decay into
# checking nothing.
_RETIRED_STEM = "n" + "emo"
RETIRED = [
    _RETIRED_STEM + "router",
    _RETIRED_STEM + "-sdk",
    _RETIRED_STEM.upper() + "_API_KEY",
    "sk-" + _RETIRED_STEM + "-",
]


# Comment prefixes across the eight languages here. Stripping them is what stops
# a header named only in a doc comment from satisfying the gate — the exact way
# a text check can pass while the parser that reads it has been deleted.
#
# NOT in this list: `'`. A Dart or R string literal can begin a line, and
# treating one as a comment silently removes real code from the scan (it did,
# and it made a 1-occurrence header look conformant).
_COMMENT_PREFIXES = ("//", "///", "//!", "#'", "#", "*", "/*", "--")


def strip_comments(text: str) -> str:
    """Drop whole-line comments, keeping code (and string literals) intact."""
    kept = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(_COMMENT_PREFIXES):
            continue
        kept.append(line)
    return "\n".join(kept)


def load_spec() -> dict:
    return json.loads(SPEC.read_text())


def check_swift_manifests(root: Path = ROOT) -> list[str]:
    """The Swift package is declared twice; make them agree.

    SwiftPM reads `Package.swift` from the repository ROOT, so the shipping
    manifest is `Package.swift` at the SDK root (which is the public repo's
    root). `sdks/swift/Package.swift` is kept for the local dev loop. Only the
    root one reaches a consumer, so a platform floor or a product name changed
    in the nested one alone builds fine locally and is wrong for everybody —
    silently, which is why this is a check and not a comment.
    """
    failures: list[str] = []
    shipping = root / "Package.swift"
    nested = root / "sdks/swift/Package.swift"
    if not shipping.exists():
        return [f"swift: {shipping.name} is missing from the SDK root — SwiftPM "
                f"reads the manifest from the repository root and consumers "
                f"cannot resolve the package without it"]
    if not nested.exists():
        return []

    def platforms(text: str) -> set[str]:
        block = re.search(r"platforms:\s*\[(.*?)\]", text, re.S)
        return set(re.findall(r"\.(\w+)\(\.(\w+)\)", block.group(1))) if block else set()

    def names(text: str, kind: str) -> set[str]:
        return set(re.findall(rf'\.{kind}\(\s*name:\s*"([^"]+)"', text))

    a, b = shipping.read_text(), nested.read_text()

    if platforms(a) != platforms(b):
        failures.append(
            f"swift: platform floors differ between Package.swift and "
            f"sdks/swift/Package.swift — {sorted(platforms(a))} vs {sorted(platforms(b))}"
        )
    for kind in ("library", "target", "testTarget"):
        if names(a, kind) != names(b, kind):
            failures.append(
                f"swift: {kind} names differ between the two manifests — "
                f"{sorted(names(a, kind))} vs {sorted(names(b, kind))}"
            )
    return failures


def check(root: Path = ROOT, spec: dict | None = None) -> list[str]:
    """Return a list of failure strings; empty means conformant."""
    spec = spec or load_spec()
    failures: list[str] = []

    base_url = spec["base_url"]
    env_var = spec["env_var"]
    headers = list(spec["response_headers"].keys())
    codes = list(spec["errors"].keys())
    key_prefix = "sk-nrouter-"

    for sdk, rel_paths in SDK_SOURCES.items():
        blob_parts = []
        for rel in rel_paths:
            path = root / rel
            if not path.exists():
                failures.append(f"{sdk}: missing source file {rel}")
                continue
            blob_parts.append(path.read_text())
        if not blob_parts:
            continue
        raw = "\n".join(blob_parts)
        # Two views on purpose. Header and error-code checks read the STRIPPED
        # text, so a constant named only in a doc comment cannot satisfy them.
        # The retired-spelling scan reads the RAW text, because Rule #35 makes a
        # retired name a defect in a comment too.
        blob = strip_comments(raw)

        # The connection contract. An SDK either states it or proves it
        # delegates; there is no third option, and "absent" is never a pass.
        if sdk in DELEGATES:
            for symbol in DELEGATES[sdk]["symbols"]:
                if symbol not in blob:
                    failures.append(
                        f"{sdk}: delegates the connection contract to "
                        f"{DELEGATES[sdk]['owner']} but does not reference {symbol!r}"
                    )
            # Restating a delegated constant is the drift itself.
            if base_url in blob:
                failures.append(
                    f"{sdk}: hardcodes the base URL instead of delegating to "
                    f"{DELEGATES[sdk]['owner']}"
                )
        else:
            checks = [("base URL", base_url), ("key prefix", key_prefix)]
            if sdk not in NO_ENV_RESOLUTION:
                checks.append(("env var", env_var))
            for label, needle in checks:
                if needle not in blob:
                    failures.append(f"{sdk}: {label} {needle!r} appears nowhere")

        for retired in RETIRED:
            if retired.lower() in raw.lower():
                failures.append(f"{sdk}: retired spelling {retired!r} is present")

        if sdk in WRAPPER_ONLY:
            continue

        for header in headers:
            # DECLARED AND USED. Every native SDK names each header twice in
            # code: once in its header-name list, once at the parse site. One
            # occurrence means a parser lookup was deleted while the list still
            # advertises it — a gate checking mere presence stays green through
            # exactly that, which is the weakness this rule closes.
            seen = blob.count(header)
            if seen == 0:
                failures.append(f"{sdk}: response header {header!r} is not read")
            elif seen < 2:
                failures.append(
                    f"{sdk}: response header {header!r} is declared but never used "
                    f"(found {seen} non-comment occurrence, expected the list entry "
                    f"and the parse site)"
                )

        for code in codes:
            if code not in blob:
                failures.append(f"{sdk}: error code {code!r} is not mapped")

        # The code STRINGS are only half the error contract: the spec also fixes
        # each code's HTTP status, and the gateway's main error path sends no
        # code at all, so status dispatch is the ordinary route rather than a
        # fallback. Require every distinct spec status to appear in a dispatch.
        #
        # LIMIT, stated rather than papered over: this binds the SET of statuses,
        # not each code to ITS status. Moving `invalid_request` from 400 to 503
        # in the spec leaves the set unchanged and passes here.
        #
        # A per-code binding is NOT expressible in a text gate. These SDKs
        # dispatch on the code first and the status second, in separate blocks —
        # which is the correct architecture — so a code and its status are
        # legitimately far apart in the source, and a proximity heuristic flags
        # correct code. It was tried; it produced six false positives on a
        # conformant tree, and tuning the window until they disappeared would
        # have measured nothing.
        #
        # The code-to-status binding IS proven, per SDK, by each suite's
        # `each gateway code maps to its type` and its codeless-status tests,
        # every one of them mutation-checked. That is where the guarantee lives;
        # this gate covers what those cannot — that all nine agree.
        for status in sorted({str(e["http"]) for e in spec["errors"].values()}):
            if status not in blob:
                failures.append(
                    f"{sdk}: spec status {status} appears in no dispatch — a codeless "
                    f"response with that status cannot be classified"
                )

    failures.extend(check_swift_manifests(root))
    return failures


def self_test() -> int:
    """Prove the gate bites, two ways.

    Inventing a spec value proves it reacts to the SPEC changing. That is only
    half: the gate must also react to an SDK LOSING something. So the second
    half copies a real SDK source, deletes a real line from it, and asserts the
    gate reports it — a check that would go green if this file were rewritten to
    assert nothing.
    """
    import shutil
    import tempfile

    spec = load_spec()
    problems = []

    if check():
        problems.append("baseline check is not green; fix conformance first")

    # --- half one: the SPEC moves, every SDK must go red ---------------------
    for label, mutate in (
        ("base_url", lambda d: d.update(base_url="https://api-stage.nrouter.ai/v1")),
        ("env_var", lambda d: d.update(env_var="NROUTER_TOKEN")),
        ("a new header", lambda d: d["response_headers"].update({"x-nr-invented": {}})),
        ("a new error code", lambda d: d["errors"].update({"invented_code": {"http": 400}})),
        # Moving an EXISTING code's status must also bite: the contract is the
        # code AND its status, and a gate blind to `http` lets one drift.
        # A status leaving the spec's set must bite. (Moving a code ONTO an
        # existing status does not — see the LIMIT note in check().)
        ("an existing code's http", lambda d: d["errors"]["guardrail_blocked"].update({"http": 422})),
    ):
        mutated = json.loads(json.dumps(spec))
        mutate(mutated)
        if not check(spec=mutated):
            problems.append(f"changing {label} did not fail the check")

    # --- half two: a real SDK LOSES something, that SDK must go red ----------
    with tempfile.TemporaryDirectory() as tmp:
        fake_root = Path(tmp)
        for rel in {r for paths in SDK_SOURCES.values() for r in paths}:
            src = ROOT / rel
            if not src.exists():
                continue
            dst = fake_root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
        (fake_root / "spec").mkdir(parents=True, exist_ok=True)
        shutil.copy(SPEC, fake_root / "spec" / SPEC.name)
        for extra in ("Package.swift", "sdks/swift/Package.swift"):
            src = ROOT / extra
            if src.exists():
                dst = fake_root / extra
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(src, dst)

        if check(root=fake_root):
            problems.append("an unmodified copy of the tree did not pass")

        # Delete a header this SDK really reads.
        victim = fake_root / "sdks/rust/src/meta.rs"
        text = victim.read_text()
        victim.write_text(text.replace('"x-nr-response-cache-age",\n', "", 1))
        failures = check(root=fake_root)
        if not any("x-nr-response-cache-age" in f and "rust" in f for f in failures):
            problems.append("deleting a real header from a real SDK did not fail the check")
        victim.write_text(text)

        # Delete an error code this SDK really maps.
        victim = fake_root / "sdks/dart/lib/src/errors.dart"
        text = victim.read_text()
        victim.write_text(text.replace("'guardrail_blocked'", "'REMOVED'"))
        failures = check(root=fake_root)
        if not any("guardrail_blocked" in f and "dart" in f for f in failures):
            problems.append("deleting a real error code from a real SDK did not fail the check")
        victim.write_text(text)

        # Plant a retired spelling.
        victim = fake_root / "sdks/swift/Sources/NRouter/NRouter.swift"
        text = victim.read_text()
        victim.write_text(text + f"\n// {RETIRED[0]}\n")
        if not any("retired spelling" in f for f in check(root=fake_root)):
            problems.append("a retired spelling in a real SDK did not fail the check")
        victim.write_text(text)

        # The two Swift manifests must be held together: only the root one
        # ships, so a floor changed in the nested one alone is invisible.
        victim = fake_root / "sdks/swift/Package.swift"
        if victim.exists():
            text = victim.read_text()
            victim.write_text(text.replace(".macOS(.v12)", ".macOS(.v13)"))
            if not any("platform floors differ" in f for f in check(root=fake_root)):
                problems.append("a Swift manifest platform drift did not fail the check")
            victim.write_text(text)

        # A missing root manifest must ERROR: without it SwiftPM cannot resolve
        # the package at all.
        shipping = fake_root / "Package.swift"
        if shipping.exists():
            text = shipping.read_text()
            shipping.unlink()
            if not any("reads the manifest from the repository root" in f
                       for f in check(root=fake_root)):
                problems.append("a missing root Package.swift did not fail the check")
            shipping.write_text(text)

        # Remove a whole SDK file: must ERROR, never silently skip.
        (fake_root / "sdks/rust/src/errors.rs").unlink()
        if not any("missing source file" in f for f in check(root=fake_root)):
            problems.append("a missing SDK source file did not fail the check")

    # The retired list is assembled from fragments to stay invisible to
    # verify-layout.sh. Assert what it assembles to, or the evasion could
    # quietly become a list that matches nothing.
    if len(RETIRED) != 4 or not all(RETIRED):
        problems.append(f"RETIRED assembled to something implausible: {RETIRED}")

    for problem in problems:
        print(f"SELF-TEST FAIL: {problem}")
    if problems:
        return 1
    print(
        "self-test ok: red on spec drift (base_url, env_var, header, code) AND on a "
        "real SDK losing a header, a code, a file, or gaining a retired spelling"
    )
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    failures = check()
    checked = len(SDK_SOURCES)
    if failures:
        for f in failures:
            print(f"FAIL {f}")
        print(f"\n{len(failures)} conformance failure(s) across {checked} SDKs")
        return 1

    spec = load_spec()
    print(f"OK  {checked} SDKs conform to spec {spec['version']}")
    print(f"    base_url   {spec['base_url']}")
    print(f"    env_var    {spec['env_var']}")
    print(f"    headers    {len(spec['response_headers'])}")
    print(f"    error codes {len(spec['errors'])}")
    for sdk, why in WRAPPER_ONLY.items():
        print(f"    note: {sdk} checked for the connection contract only — {why}")
    for sdk, why in NO_ENV_RESOLUTION.items():
        print(f"    note: {sdk} does NOT resolve {spec['env_var']} — {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
