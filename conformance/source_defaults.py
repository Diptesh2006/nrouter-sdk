#!/usr/bin/env python3
"""Prove every SDK's DEFAULT model is callable on the wire that SDK defaults to.

A default model is the one line of an SDK that no test exercises and every new
user hits. Two of the ten SDKs ship one — Python's ``DEFAULT_MODEL`` and R's
``nrouter_chat(model = ...)`` — and both convenience wrappers post to
``/v1/chat/completions`` unconditionally, with no per-model wire switch.

The gateway resolves a provider endpoint PER WIRE. A provider that declares no
endpoint for a wire answers 404 ``model_unavailable_on_route``: the model
exists, just not on the route it was asked for. Anthropic declares Messages
ONLY, so an Anthropic-family default meant ``client.nrouter.chat("hello")`` —
the shortest call in the quickstart, from a customer holding a valid key —
returned a not-found error. It reads as "nRouter is broken", it is world-visible
in a published package, and no suite saw it because none of them call the
network. Derive the gateway side rather than trusting this docstring::

    cd nrouter-rust-gateway
    grep -n "fn endpoints" -A 12 src/sdk/providers/anthropic/transformation.rs
    # => messages: Some(...), responses: None, chat_completions: None

Scope, and why it is a separate file. ``doc_wires.py`` holds the DOCUMENTATION
corpus (README, LANGUAGES.md, examples, ``sdks/*/docs``) and says in its own
docstring that SDK source is out of scope. ``check_conformance.py`` holds SDK
source to the spec — but the spec fixes headers, endpoints and error codes, and
carries no default model at all. A default model therefore fell between the two
gates, which is exactly how it rotted unnoticed. This file closes that seam and
is imported by ``check_conformance.py`` the same way ``doc_wires`` is.

The two halves are equally load-bearing:

1. **Declared defaults** must name a model whose family the gateway serves on
   that SDK's default wire.
2. **SDKs declared to have NO default** must genuinely have none. Without this,
   a default added to Go tomorrow is invisible to the gate — the failure mode
   that a registry-only check always has.

    python3 conformance/source_defaults.py             # check
    python3 conformance/source_defaults.py --self-test # prove the gate bites
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- which model families the gateway serves on which wire ------------------
# Keyed by wire, valued by the model-id prefixes the gateway REFUSES there.
# Anthropic is the only provider in the tree declaring a partial layout today;
# add a family here when a provider declares another `None`, and derive it from
# `src/sdk/providers/*/transformation.rs::endpoints` rather than guessing.
#
# Spelled as a REFUSAL list rather than an allowlist on purpose: an allowlist
# would have to enumerate every servable model id and would go stale the moment
# Super Admin publishes a new one, so it would be quietly loosened until it
# meant nothing. The refusal list only grows when a provider narrows its layout.
MESSAGES_ONLY_FAMILIES = ("anthropic/", "claude-")
REFUSED_ON_WIRE: dict[str, tuple[str, ...]] = {
    "chat_completions": MESSAGES_ONLY_FAMILIES,
    "responses": MESSAGES_ONLY_FAMILIES,
    "messages": (),
}

# --- the registry -----------------------------------------------------------
# sdk -> (source file, pattern whose group 1 is the model literal, default wire)
#
# The wire is the one the SDK's OWN default call path reaches, traced to the
# request URL — not the one the SDK is capable of. Python's `_nRouterChat.chat`
# ends in `self._c.chat.completions.create(...)`; R's `nrouter_chat` calls
# `nrouter_chat_completions` -> `nrouter_request(client, "/chat/completions")`.
DECLARED_DEFAULTS: dict[str, tuple[str, re.Pattern[str], str]] = {
    "python": (
        "sdks/python/nroutersdk/client.py",
        re.compile(r'^DEFAULT_MODEL\s*=\s*"([^"]+)"', re.M),
        "chat_completions",
    ),
    "r": (
        "sdks/r/R/client.R",
        re.compile(r'^nrouter_chat\s*<-\s*function\([^)]*?model\s*=\s*"([^"]+)"', re.M | re.S),
        "chat_completions",
    ),
}

# Every other SDK requires the caller to name a model. Listed explicitly so that
# adding a default to one of them fails this gate rather than shipping silently.
# The files are the executable source only: doc comments legitimately carry
# model ids and `doc_wires.py` does not read SDK source, so a doc-comment id is
# checked here by the SAME rule instead of being exempt.
NO_DEFAULT_SDKS: dict[str, list[str]] = {
    "js": ["sdks/js/src"],
    "go": ["sdks/go"],
    "java": ["sdks/java/src/main"],
    "kotlin": ["sdks/kotlin/src/main"],
    "android": ["sdks/android/src/main"],
    "swift": ["sdks/swift/Sources"],
    "rust": ["sdks/rust/src"],
    "dart": ["sdks/dart/lib"],
}

# What a default-model declaration LOOKS like. TWO shapes, because the defect
# shipped in both and a gate that knew only one would have caught Python while
# passing R.
#
# 1. A NAMED constant: `DEFAULT_MODEL`, `defaultModel`, `modelDefault`.
# 2. A PARAMETER default: `model = "…"`, the form `nrouter_chat` used. Kotlin,
#    Swift, Dart and JS all support this too, so a registry-only check that knew
#    shape 1 alone would let the identical defect back in through any of them.
#
# Both are deliberately narrow. Shape 2 excludes a `model` preceded by a quote,
# which is what keeps every `"model": "claude-sonnet-4-5"` map literal in a doc
# comment — Go, Kotlin, Swift and Dart each ship one — from tripping it. A
# `.model("…")` builder call is likewise not an assignment and does not match.
DEFAULT_DECLARATIONS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"""(?ix)
        \b[A-Za-z_.]*default[A-Za-z_]*model[A-Za-z_]*\b   # DEFAULT_MODEL, defaultModel...
        \s*(?::[^=\n]*)?                                  # optional type annotation
        \s*(?:=|:=|<-)\s*                                 # = / := / <-
        ["'`]([A-Za-z0-9][A-Za-z0-9._/:-]{2,})["'`]       # a quoted model-shaped id
        """
    ),
    re.compile(
        r"""(?x)
        (?<!["'`])                                        # not `"model": "…"` in a map literal
        \bmodel\b
        \s*(?::\s*[A-Za-z_][\w<>?\[\].]*\??)?             # optional `: String` / `: String?`
        \s*=\s*
        ["'`]([A-Za-z0-9][A-Za-z0-9._/:-]{2,})["'`]
        """,
        re.IGNORECASE,
    ),
)

SOURCE_SUFFIXES = {
    ".py", ".ts", ".js", ".go", ".java", ".kt", ".kts", ".swift", ".rs",
    ".dart", ".R", ".r",
}
SKIP_PARTS = {
    "node_modules", ".git", "target", "build", "dist", ".dart_tool",
    "test", "tests", "__pycache__", "generated",
}


def _model_is_refused(model: str, wire: str) -> bool:
    return model.startswith(REFUSED_ON_WIRE.get(wire, ()))


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


def check_source_defaults(root: Path = ROOT) -> list[str]:
    """Return a list of failure strings; empty means every default is callable."""
    failures: list[str] = []

    # --- half one: every declared default must be callable on its own wire ---
    for sdk, (rel, pattern, wire) in sorted(DECLARED_DEFAULTS.items()):
        path = root / rel
        if not path.is_file():
            # A vanished source must not read as a pass.
            failures.append(f"{sdk}: {rel} is missing — its default model cannot be checked")
            continue
        match = pattern.search(path.read_text(encoding="utf-8"))
        if match is None:
            failures.append(
                f"{sdk}: no default model found in {rel}. Either the declaration moved "
                f"(update DECLARED_DEFAULTS) or the default was removed (move {sdk} to "
                f"NO_DEFAULT_SDKS). An unreadable registry entry is not a pass."
            )
            continue
        model = match.group(1)
        if _model_is_refused(model, wire):
            failures.append(
                f"{rel}: {sdk} defaults to {model!r}, which the gateway serves on "
                f"/v1/messages ONLY, but this SDK's default call path posts to the "
                f"{wire} wire. A caller who names no model gets 404 "
                f"model_unavailable_on_route."
            )

    # --- half two: SDKs declared default-free must stay default-free ---------
    for sdk, dirs in sorted(NO_DEFAULT_SDKS.items()):
        seen_any = False
        for rel_dir in dirs:
            sources = _iter_sources(root, rel_dir)
            seen_any = seen_any or bool(sources)
            for path in sources:
                text = path.read_text(errors="replace")
                for index, line in enumerate(text.splitlines(), start=1):
                    for pattern in DEFAULT_DECLARATIONS:
                        found = pattern.search(line)
                        if not found:
                            continue
                        failures.append(
                            f"{path.relative_to(root)}:{index}: {sdk} is registered as "
                            f"having no default model, but declares one "
                            f"({found.group(1)!r}). Add it to DECLARED_DEFAULTS with "
                            f"the wire its default call path posts to, so this gate "
                            f"can prove the gateway serves it there."
                        )
                        break
        if not seen_any:
            failures.append(
                f"{sdk}: none of {dirs} contain readable source — an SDK that vanished "
                f"must not read as passing"
            )

    return failures


# --------------------------------------------------------------------------
# self-test — plant each violation and assert the gate reports it
# --------------------------------------------------------------------------

_PY_CLEAN = 'DEFAULT_MODEL = "gpt-5.4-mini"\n'
_R_CLEAN = 'nrouter_chat <- function(messages, model = "gpt-5.4-mini", api_key = NULL,\n'
_GO_CLEAN = "package nrouter\n\nfunc ChatCompletions(body any) {}\n"


def _fixture(tmp: Path, py: str = _PY_CLEAN, r: str = _R_CLEAN, go: str = _GO_CLEAN) -> Path:
    root = tmp / "repo"
    (root / "sdks/python/nroutersdk").mkdir(parents=True, exist_ok=True)
    (root / "sdks/r/R").mkdir(parents=True, exist_ok=True)
    (root / "sdks/python/nroutersdk/client.py").write_text(py)
    (root / "sdks/r/R/client.R").write_text(r)
    for sdk, dirs in NO_DEFAULT_SDKS.items():
        for rel_dir in dirs:
            target = root / rel_dir
            target.mkdir(parents=True, exist_ok=True)
            (target / ("stub.go" if sdk == "go" else "stub.ts")).write_text(
                go if sdk == "go" else "export const x = 1;\n"
            )
    return root


def self_test() -> int:
    import tempfile

    problems: list[str] = []

    if check_source_defaults():
        problems.append(
            "baseline is not green against the real repository; fix the defaults first"
        )

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)

        # 1. a clean fixture must pass, or every case below proves nothing.
        found = check_source_defaults(_fixture(tmp / "a"))
        if found:
            problems.append(f"clean fixture reported failures: {found}")

        # 2. a Claude id as the Python default must be reported.
        found = check_source_defaults(
            _fixture(tmp / "b", py='DEFAULT_MODEL = "anthropic/claude-sonnet-4-5-20250929"\n')
        )
        if not any("python defaults to" in f for f in found):
            problems.append(f"planted Python Anthropic default NOT reported: {found}")

        # 3. the unprefixed `claude-…` spelling must be reported too. R shipped
        #    exactly that form, so a gate keyed only on `anthropic/` would have
        #    passed the R defect while catching the Python one.
        found = check_source_defaults(
            _fixture(tmp / "c", r='nrouter_chat <- function(messages, model = "claude-sonnet-4-5", api_key = NULL,\n')
        )
        if not any("r defaults to" in f for f in found):
            problems.append(f"planted R Anthropic default NOT reported: {found}")

        # 4. a default APPEARING in an SDK registered as default-free must be
        #    reported — the hole a registry-only gate always has.
        found = check_source_defaults(
            _fixture(tmp / "d", go='package nrouter\n\nconst DefaultModel = "claude-sonnet-4-5"\n')
        )
        if not any("registered as having no default model" in f for f in found):
            problems.append(f"planted new default in a default-free SDK NOT reported: {found}")

        # 5. ...and it is reported whatever the model is, because the point is
        #    that the registry no longer describes the tree.
        found = check_source_defaults(
            _fixture(tmp / "e", go='package nrouter\n\nconst DefaultModel = "gpt-5.4-mini"\n')
        )
        if not any("registered as having no default model" in f for f in found):
            problems.append(f"planted servable default in a default-free SDK NOT reported: {found}")

        # 5b. a PARAMETER default — the shape R actually shipped — must be
        #     reported in a default-free SDK too. A gate knowing only the named
        #     -constant shape would have caught Python and passed R, and Kotlin,
        #     Swift, Dart and JS can all express this form.
        root = _fixture(tmp / "e2")
        victim = root / "sdks/kotlin/src/main/stub.ts"
        victim.write_text('fun chat(messages: X, model: String = "claude-sonnet-4-5") {}\n')
        found = check_source_defaults(root)
        if not any("registered as having no default model" in f for f in found):
            problems.append(f"planted PARAMETER default NOT reported: {found}")

        # 5c. ...but a `"model": "claude-…"` map literal inside a doc comment is
        #     NOT a default, and flagging it would make the gate unusable. Every
        #     one of Go, Kotlin, Swift and Dart ships exactly such a comment.
        root = _fixture(tmp / "e3")
        victim = root / "sdks/kotlin/src/main/stub.ts"
        victim.write_text(
            ' * .put("model", "claude-sonnet-4-5")\n'
            ' * {"model": "anthropic/claude-sonnet-4-5"}\n'
            ' * .model("claude-sonnet-4-5")\n'
        )
        found = check_source_defaults(root)
        if found:
            problems.append(f"a doc-comment model id was misread as a default: {found}")

        # 6. a declaration that MOVED must be reported, not silently skipped —
        #    a registry that can no longer find its target is not a pass.
        found = check_source_defaults(_fixture(tmp / "f", py="MODEL = 'gpt-5.4-mini'\n"))
        if not any("no default model found" in f for f in found):
            problems.append(f"a moved declaration was silently skipped: {found}")

        # 7. a vanished SDK source must ERROR rather than read as passing.
        root = _fixture(tmp / "g")
        (root / "sdks/r/R/client.R").unlink()
        found = check_source_defaults(root)
        if not any("is missing" in f for f in found):
            problems.append(f"a vanished SDK source did not fail the check: {found}")

    if problems:
        for problem in problems:
            print(f"SELF-TEST FAIL {problem}")
        return 1
    print("OK  source_defaults self-test: 9 planted violations, all reported")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    failures = check_source_defaults()
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        print(f"\n{len(failures)} SDK default(s) name a wire the gateway refuses")
        return 1
    print(
        f"OK  {len(DECLARED_DEFAULTS)} declared default model(s) are callable on their "
        f"own wire; {len(NO_DEFAULT_SDKS)} SDK(s) declare none"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
