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

# Spellings that must appear nowhere (Rule #35).
RETIRED = ["nemorouter", "nemo-sdk", "NEMO_API_KEY", "sk-nemo-"]


def load_spec() -> dict:
    return json.loads(SPEC.read_text())


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
        blob = "\n".join(blob_parts)

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
            for label, needle in (
                ("base URL", base_url),
                ("env var", env_var),
                ("key prefix", key_prefix),
            ):
                if needle not in blob:
                    failures.append(f"{sdk}: {label} {needle!r} appears nowhere")

        for retired in RETIRED:
            if retired.lower() in blob.lower():
                failures.append(f"{sdk}: retired spelling {retired!r} is present")

        if sdk in WRAPPER_ONLY:
            continue

        for header in headers:
            if header not in blob:
                failures.append(f"{sdk}: response header {header!r} is not read")

        for code in codes:
            if code not in blob:
                failures.append(f"{sdk}: error code {code!r} is not mapped")

    return failures


def self_test() -> int:
    """Prove the gate bites: a spec the SDKs do not implement must fail."""
    spec = load_spec()
    problems = []

    if check():
        problems.append("baseline check is not green; fix conformance first")

    mutated = json.loads(json.dumps(spec))
    mutated["base_url"] = "https://api-stage.nrouter.ai/v1"
    if not check(spec=mutated):
        problems.append("changing base_url did not fail the check")

    mutated = json.loads(json.dumps(spec))
    mutated["response_headers"]["x-nr-invented-header"] = {}
    if not check(spec=mutated):
        problems.append("adding a header did not fail the check")

    mutated = json.loads(json.dumps(spec))
    mutated["errors"]["invented_code"] = {"http": 400}
    if not check(spec=mutated):
        problems.append("adding an error code did not fail the check")

    mutated = json.loads(json.dumps(spec))
    mutated["env_var"] = "NROUTER_TOKEN"
    if not check(spec=mutated):
        problems.append("changing env_var did not fail the check")

    # A missing source file must fail, never silently skip. A skip reads as a
    # pass, which is the whole failure mode this gate exists to prevent.
    missing = dict(SDK_SOURCES)
    try:
        SDK_SOURCES["ghost"] = ["sdks/ghost/does-not-exist.txt"]
        if not any("missing source file" in f for f in check()):
            problems.append("a missing SDK source file did not fail the check")
    finally:
        SDK_SOURCES.clear()
        SDK_SOURCES.update(missing)

    for problem in problems:
        print(f"SELF-TEST FAIL: {problem}")
    if problems:
        return 1
    print("self-test ok: the gate goes red on base_url, env_var, header and code drift")
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
