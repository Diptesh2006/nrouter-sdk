#!/usr/bin/env python3
"""Prove every documented snippet calls a wire the gateway serves for its model.

Two independent failures live in the same corpus (`README.md`, `LANGUAGES.md`,
`examples/**`, `sdks/*/README.md`, `sdks/*/docs/**`), and both ship as
copy-pasteable code:

1. **Wire mismatch.** The gateway resolves a provider endpoint per wire, and a
   provider that declares no endpoint for a wire answers 404
   `model_unavailable_on_route` — the model exists, just not on the route it was
   asked for. Anthropic declares `messages` ONLY (`chat_completions: None`,
   `responses: None`), so a Claude id posted to `/v1/chat/completions` fails for
   a customer holding a valid key and a real model id, and reads as "nRouter is
   broken". Derive the gateway side rather than trusting this docstring::

       cd nrouter-rust-gateway
       grep -n "fn endpoints" -A 12 src/sdk/providers/anthropic/transformation.rs

2. **Unserved endpoint.** `spec/nrouter-sdk-spec.json` › `unsupported_endpoints`
   names the paths the gateway does not mount. A committed example that calls
   one is a documented 404.

The corpus is DOCUMENTATION, so this is a text gate by design: the snippets are
never executed, which is exactly why nothing else notices when they rot.

    python3 conformance/doc_wires.py             # check
    python3 conformance/doc_wires.py --self-test # prove the gate bites
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- the corpus -------------------------------------------------------------
# Customer-facing prose and runnable examples. SDK *source* is deliberately out
# of scope: `check_conformance.py` holds that to the spec.
DOC_FILES = ("README.md", "LANGUAGES.md")
DOC_GLOBS = ("examples/**/*", "sdks/*/README.md", "sdks/*/docs/**/*")
SKIP_PARTS = {"node_modules", ".git", "target", "build", "dist", ".dart_tool"}

# --- what counts as an Anthropic-family model id ----------------------------
ANTHROPIC_MODEL = re.compile(r"(?:anthropic/[A-Za-z0-9._-]+|\bclaude-[A-Za-z0-9._-]+)")

# A response-metadata ECHO is not a request. `x-nr-model` lines quote what the
# gateway ANSWERED with, so they carry no wire of their own and must not be
# classified as if they did.
ECHO_LINE = re.compile(r"x-nr-model")

# An explicit override, for a snippet whose wire no marker below can see.
# Spelled in a comment: `nrouter-doc-wire: messages`.
EXPLICIT_WIRE = re.compile(r"nrouter-doc-wire:\s*(messages|responses|chat_completions)")

# --- wire markers -----------------------------------------------------------
# Each pattern names the CALL that performs the request, never a response field:
# `choices` appears in an OpenAI-shaped response the SDK synthesises from a
# Messages call, so keying on it would flag correct code.
WIRE_MARKERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "messages",
        re.compile(
            r"/v1/messages"
            r"|messages\.create"
            r"|messages\(\)\.create"
            r"|count_tokens"
            r"|countTokens"
            # The per-language Messages helpers. Omitting these is what made an
            # early draft of this gate flag every correct `messagesStream`
            # example in `sdks/*/README.md`.
            r"|messages_stream"
            r"|[Mm]essagesStream"
            r"|nrouter_messages"
            r"|client\.messages\("
            # `client.nr.*` is the JS helper family, which selects /v1/messages
            # for Claude ids itself (`sdks/js/src/chat.ts::usesMessagesWire`).
            r"|\bnr\.chat\("
            r"|\bnr\.messages\("
            r"|\bnr\.stream\("
            r"|\bnr\.compare\("
            r"|client\.nr\."
            r"|MESSAGES_PATH"
        ),
    ),
    (
        "responses",
        re.compile(r"/v1/responses|responses\.create|responses\(\)"),
    ),
    (
        "chat_completions",
        re.compile(
            r"/v1/chat/completions"
            r"|chat/completions"
            r"|chat\.completions"
            r"|chatCompletions"
            r"|chat_completions"
            r"|ChatCompletion"
            r"|CompleteChatAsync"
            r"|ChatClient\("
            r"|->chat\(\)"
            r"|chat\(\)\.completions"
            r"|nrouter_chat_completions"
            # OpenAI-compatible framework adapters: every one of these posts to
            # /v1/chat/completions.
            r"|ChatOpenAI\("
            r"|OpenAIChatCompletionClient"
            r"|OpenAI::Client"
            r"|client\.chat\("
            r"|llm\s*=\s*[\"']"
            r"|config_list"
        ),
    ),
)

# Which wires the gateway's Anthropic provider declares. Anything else is a 404
# for a Claude id, whatever the key or the catalogue says.
ANTHROPIC_WIRES = {"messages"}

# How far a marker may sit from the model id and still describe the same call.
WINDOW = 40


def _iter_files(root: Path) -> list[Path]:
    seen: dict[Path, None] = {}
    for rel in DOC_FILES:
        path = root / rel
        if path.is_file():
            seen[path] = None
    for pattern in DOC_GLOBS:
        for path in sorted(root.glob(pattern)):
            if not path.is_file():
                continue
            if SKIP_PARTS & set(path.relative_to(root).parts):
                continue
            seen[path] = None
    return list(seen)


def classify(lines: list[str], index: int) -> str | None:
    """Name the wire the snippet around ``lines[index]`` calls, or ``None``.

    Nearest marker wins, searched in BOTH directions: a builder-style SDK names
    the model before the call (`ChatClient(model: ...)` ... `CompleteChatAsync`)
    and a fluent one names it after (`chat.completions.create(model=...)`).
    """
    explicit = None
    best: tuple[int, str] | None = None
    for offset, line in enumerate(lines):
        distance = abs(offset - index)
        if distance > WINDOW:
            continue
        match = EXPLICIT_WIRE.search(line)
        if match and (explicit is None or distance < explicit[0]):
            explicit = (distance, match.group(1))
        for name, pattern in WIRE_MARKERS:
            if not pattern.search(line):
                continue
            if best is None or distance < best[0]:
                best = (distance, name)
    if explicit is not None:
        return explicit[1]
    return best[1] if best else None


def check_doc_wires(root: Path = ROOT, spec: dict | None = None) -> list[str]:
    """Return a list of failure strings; empty means every snippet is callable."""
    if spec is None:
        spec = json.loads((root / "spec" / "nrouter-sdk-spec.json").read_text())
    unsupported = sorted(spec.get("unsupported_endpoints", {}))
    unsupported_paths = re.compile(
        r"/v1/(?:" + "|".join(re.escape(name) for name in unsupported) + r")\b"
    ) if unsupported else None

    failures: list[str] = []
    for path in _iter_files(root):
        try:
            lines = path.read_text().splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        rel = path.relative_to(root)

        for index, line in enumerate(lines):
            if unsupported_paths is not None:
                hit = unsupported_paths.search(line)
                if hit:
                    name = hit.group(0).split("/")[-1]
                    failures.append(
                        f"{rel}:{index + 1}: example calls {hit.group(0)}, which the "
                        f"gateway does not mount — spec unsupported_endpoints says: "
                        f"{spec['unsupported_endpoints'][name]}"
                    )
            if ECHO_LINE.search(line):
                continue
            model = ANTHROPIC_MODEL.search(line)
            if not model:
                continue
            wire = classify(lines, index)
            if wire is None:
                failures.append(
                    f"{rel}:{index + 1}: Anthropic model {model.group(0)!r} in a snippet "
                    f"whose wire cannot be determined — the gateway serves Anthropic on "
                    f"/v1/messages ONLY, so an undeclared wire is an unverifiable "
                    f"example. Name it with a `nrouter-doc-wire: <wire>` comment or use "
                    f"a chat-completions-capable model."
                )
            elif wire not in ANTHROPIC_WIRES:
                failures.append(
                    f"{rel}:{index + 1}: Anthropic model {model.group(0)!r} is called on "
                    f"the {wire} wire. The gateway's Anthropic provider declares "
                    f"{sorted(ANTHROPIC_WIRES)} only, so this snippet answers 404 "
                    f"model_unavailable_on_route for a customer with a valid key."
                )
    return failures


# --------------------------------------------------------------------------
# self-test — plant each violation and assert the gate reports it
# --------------------------------------------------------------------------

_CLEAN_README = """\
# Fixture

```python
response = client.chat.completions.create(
    model="gpt-5.4-mini",
    messages=[{"role": "user", "content": "Hello!"}],
)
```

```python
message = client.messages.create(
    model="anthropic/claude-sonnet-4-5-20250929",
    messages=[{"role": "user", "content": "Hello!"}],
)
```
"""

_SPEC = {"unsupported_endpoints": {"moderations": "not mounted"}}


def _fixture(tmp: Path, readme: str, example: str = "") -> Path:
    root = tmp / "repo"
    (root / "examples" / "curl").mkdir(parents=True, exist_ok=True)
    (root / "spec").mkdir(parents=True, exist_ok=True)
    (root / "README.md").write_text(readme)
    (root / "LANGUAGES.md").write_text("# Languages\n")
    (root / "examples" / "curl" / "quickstart.sh").write_text(example or "#!/bin/sh\n")
    (root / "spec" / "nrouter-sdk-spec.json").write_text(json.dumps(_SPEC))
    return root


def self_test() -> int:
    import tempfile

    problems: list[str] = []

    if check_doc_wires():
        problems.append(
            "baseline is not green against the real repository; fix the docs first"
        )

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)

        # 1. a clean fixture must pass, or every case below proves nothing.
        root = _fixture(tmp / "a", _CLEAN_README)
        found = check_doc_wires(root)
        if found:
            problems.append(f"clean fixture reported failures: {found}")

        # 2. a Claude id on chat completions must be reported.
        broken = _CLEAN_README.replace('model="gpt-5.4-mini"', 'model="claude-sonnet-4-5"')
        root = _fixture(tmp / "b", broken)
        found = check_doc_wires(root)
        if not any("chat_completions wire" in f for f in found):
            problems.append(f"planted chat-completions mismatch NOT reported: {found}")

        # 3. a Claude id on the responses wire must be reported.
        resp = _CLEAN_README.replace(
            "client.messages.create(", "client.responses.create("
        )
        root = _fixture(tmp / "c", resp)
        found = check_doc_wires(root)
        if not any("responses wire" in f for f in found):
            problems.append(f"planted responses mismatch NOT reported: {found}")

        # 4. a Claude id with no wire marker at all must be reported, not skipped.
        orphan = "# Fixture\n\n```text\nMODEL = \"anthropic/claude-sonnet-4-5\"\n```\n"
        root = _fixture(tmp / "d", orphan)
        found = check_doc_wires(root)
        if not any("cannot be determined" in f for f in found):
            problems.append(f"planted undeclared-wire model NOT reported: {found}")

        # 5. ...unless the snippet declares its wire explicitly.
        declared = (
            "# Fixture\n\n```text\n# nrouter-doc-wire: messages\n"
            'MODEL = "anthropic/claude-sonnet-4-5"\n```\n'
        )
        root = _fixture(tmp / "e", declared)
        found = check_doc_wires(root)
        if found:
            problems.append(f"explicit `nrouter-doc-wire` override ignored: {found}")

        # 6. an example calling an endpoint the gateway does not mount.
        root = _fixture(
            tmp / "f",
            _CLEAN_README,
            example='curl "$BASE/v1/moderations" -d \'{"input": "x"}\'\n',
        )
        found = check_doc_wires(root)
        if not any("does not mount" in f for f in found):
            problems.append(f"planted unsupported-endpoint call NOT reported: {found}")

    if problems:
        for problem in problems:
            print(f"SELF-TEST FAIL {problem}")
        return 1
    print("OK  doc_wires self-test: 6 planted violations, all reported")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    failures = check_doc_wires()
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        print(f"\n{len(failures)} documented snippet(s) call a wire the gateway refuses")
        return 1
    print("OK  every documented snippet calls a wire the gateway serves for its model")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
