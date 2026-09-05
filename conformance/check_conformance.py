#!/usr/bin/env python3
"""Prove every nRouter SDK encodes the SAME gateway contract.

Each SDK is written in its own language with its own idioms, and each one was
tested against its own copy of the constants. That proves each SDK is
self-consistent. It does not prove they agree with EACH OTHER, and a gateway
serving ten SDKs is only as correct as the one that drifted.

This gate closes that. It reads `spec/nrouter-sdk-spec.json` — the source of
truth under Rule #14 — and asserts that every SDK's source literally contains
the base URL, the environment variable, the key prefix, every `x-nr-*` header
and every error code. Every one of the ten SDKs must also expose a
named helper for every supported operation or prove an explicit delegation
seam. Change the spec and
every SDK goes red until it is updated; drop a header or endpoint helper from
one SDK and only that SDK goes red.

It deliberately checks the SOURCE TEXT rather than importing each SDK, because
importing would need ten toolchains present and would quietly skip the ones
that are missing. A skipped check reads as a pass, which is the failure mode
this gate exists to prevent.

    python3 conformance/check_conformance.py            # check
    python3 conformance/check_conformance.py --self-test # prove the gate bites
"""

from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "spec" / "nrouter-sdk-spec.json"

# The DOCUMENTED snippets are a second corpus with its own failure mode: an SDK
# can encode the contract perfectly while `README.md` tells the customer to post
# a Claude id at `/v1/chat/completions`, which the gateway answers 404. Imported
# by path so this file keeps working whether it is run as a script or imported.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from doc_wires import check_doc_wires  # noqa: E402
from doc_wires import self_test as doc_wires_self_test  # noqa: E402

# A THIRD corpus with its own failure mode, and the one that fell between the
# other two: an SDK's own DEFAULT model. The spec fixes headers, endpoints and
# error codes but carries no default model, and `doc_wires` reads documentation
# rather than SDK source — so a default naming a wire the gateway refuses for
# that model was invisible to both gates while being the first call every new
# user makes.
from source_defaults import check_source_defaults  # noqa: E402
from doc_header_count import check_doc_header_count  # noqa: E402
from doc_header_count import check_doc_header_enumeration  # noqa: E402
from doc_header_count import self_test as doc_header_count_self_test  # noqa: E402
from source_defaults import self_test as source_defaults_self_test  # noqa: E402

# A FOURTH corpus, and the one none of the others can express: how each SDK
# BEHAVES on the wire. The spec fixes headers, endpoints and error codes and
# carries no timeout and no retry policy, `doc_wires` reads documentation and
# `source_defaults` reads only the default MODEL — so a client that waited 60 s,
# or forever, and a vendor client that silently retried an already-billed POST,
# were invisible to all three.
from client_timeouts import check_client_timeouts  # noqa: E402
from client_timeouts import self_test as client_timeouts_self_test  # noqa: E402

# Which files carry the contract, per SDK. A file listed here that does not
# exist is an ERROR, not a skip: an SDK that vanished must not read as passing.
SDK_SOURCES: dict[str, list[str]] = {
    "python": [
        "sdks/python/nroutersdk/client.py",
        "sdks/python/nroutersdk/_errors.py",
        "sdks/python/nroutersdk/_response.py",
    ],
    # js was WRAPPER_ONLY until it grew a native surface: it now owns the 14
    # headers, the 9 typed error classes and the status dispatch itself, so it
    # is held to the same contract as every other native SDK.
    "js": [
        "sdks/js/src/client.ts",
        "sdks/js/src/chat.ts",
        "sdks/js/src/multimodal.ts",
        "sdks/js/src/models.ts",
        # types.ts carries HEADER_NAMES; meta.ts carries the parse sites. The
        # gate's declared-AND-used rule needs both files or every header reads
        # as declared-but-never-parsed.
        "sdks/js/src/types.ts",
        "sdks/js/src/meta.ts",
        "sdks/js/src/errors.ts",
    ],
    "java": [
        "sdks/java/src/main/java/ai/nrouter/sdk/NRouter.java",
        "sdks/java/src/main/java/ai/nrouter/sdk/NRouterHttpClient.java",
        "sdks/java/src/main/java/ai/nrouter/sdk/NRouterException.java",
        "sdks/java/src/main/java/ai/nrouter/sdk/NRouterResponseMeta.java",
    ],
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
        "sdks/rust/src/http.rs",
        "sdks/rust/src/errors.rs",
        "sdks/rust/src/meta.rs",
    ],
    "dart": [
        "sdks/dart/lib/src/client.dart",
        "sdks/dart/lib/src/errors.dart",
        "sdks/dart/lib/src/meta.dart",
    ],
    "r": ["sdks/r/R/client.R", "sdks/r/R/errors.R", "sdks/r/R/meta.R"],
    "go": [
        "sdks/go/client.go",
        "sdks/go/errors.go",
        "sdks/go/meta.go",
        "sdks/go/stream.go",
    ],
}

# Distribution metadata read by the release-version gate. Swift and Go derive
# their public versions from tags, so their VERSION files are the reviewable
# source from which release automation creates those immutable tags.
RELEASE_METADATA_PATHS = {
    "sdks/js/package.json",
    "sdks/js/package-lock.json",
    "sdks/python/pyproject.toml",
    "sdks/python/nroutersdk/_version.py",
    "sdks/java/pom.xml",
    "sdks/kotlin/gradle.properties",
    "sdks/android/gradle.properties",
    "sdks/android/build.gradle.kts",
    "sdks/android/gradle.lockfile",
    "sdks/go/VERSION",
    "sdks/go/go.mod",
    "sdks/rust/Cargo.toml",
    "sdks/rust/Cargo.lock",
    "sdks/swift/VERSION",
    "sdks/dart/pubspec.yaml",
    "sdks/r/DESCRIPTION",
}

# These SDKs own their HTTP transport rather than delegating it to a vendor or
# sibling package. Every supported operation must therefore appear in their
# executable source. This is a source-level cross-language gate; each SDK's own
# wire tests prove that the named helper sends the path correctly.
FIRST_PARTY_NATIVE = {"go", "java", "kotlin", "swift", "rust", "dart", "r"}

# JS and Python deliberately combine their own gateway additions with a
# vendor-client inheritance seam. Each endpoint belongs to exactly one side of
# that boundary here: a native helper must be present in executable source; a
# delegated helper requires the inheritance declaration and bounded vendor
# dependency. "Wrapper" is never a blanket route exemption.
HYBRID_NATIVE_HELPERS = {
    "js": {
        "chat.completions.create()": r"\bchat\(opts:\s*NRouterCallOptions\)",
        "embeddings.create()": r"async\s+embeddings\(",
        "images.generate()": r"async\s+image\(",
        "videos.create()": r"async\s+video\(",
        "audio.speech.create()": r"async\s+speech\(",
        "audio.transcriptions.create()": r"async\s+transcribe\(",
        "models.list()": r"async\s+list\(\):\s*Promise<NRouterModelList>",
        "models.retrieve()": r"async\s+get\(modelId:\s*string\)",
        "messages.create()": r"\bmessages\(\s*body:\s*Record<string, unknown>",
        "messages.count_tokens()": r"\bcountTokens\(body:\s*Record<string, unknown>",
        "responses.create()": r"\bresponses\(\s*body:\s*Record<string, unknown>",
        "audio.translations.create()": r"async\s+translate\(",
        "videos.retrieve()": r"async\s+videoStatus\(",
        "videos.download_content()": r"async\s+videoContent\(",
    },
}

PYTHON_NATIVE_HELPERS = {
    "videos.create()": (("_Videos", "create"), ("_AsyncVideos", "create")),
    "messages.create()": (("_Messages", "create"), ("_AsyncMessages", "create")),
    "messages.count_tokens()": (
        ("_Messages", "count_tokens"),
        ("_AsyncMessages", "count_tokens"),
    ),
    "videos.retrieve()": (("_Videos", "retrieve"), ("_AsyncVideos", "retrieve")),
    "videos.download_content()": (
        ("_Videos", "download_content"),
        ("_AsyncVideos", "download_content"),
    ),
}

DELEGATED_ROUTE_PROOFS = {
    "js": {
        "completions.create()": r'OpenAI\["completions"\]\["create"\]',
    },
    "python": {
        "chat.completions.create()": r"sync\.chat\.completions\.create.*asynchronous\.chat\.completions\.create",
        "completions.create()": r"sync\.completions\.create.*asynchronous\.completions\.create",
        "embeddings.create()": r"sync\.embeddings\.create.*asynchronous\.embeddings\.create",
        "images.generate()": r"sync\.images\.generate.*asynchronous\.images\.generate",
        "audio.speech.create()": r"sync\.audio\.speech\.create.*asynchronous\.audio\.speech\.create",
        "audio.transcriptions.create()": r"sync\.audio\.transcriptions\.create.*asynchronous\.audio\.transcriptions\.create",
        "models.list()": r"sync\.models\.list.*asynchronous\.models\.list",
        "models.retrieve()": r"sync\.models\.retrieve.*asynchronous\.models\.retrieve",
        "responses.create()": r"sync\.responses\.create.*asynchronous\.responses\.create",
        "audio.translations.create()": r"sync\.audio\.translations\.create.*asynchronous\.audio\.translations\.create",
    },
}

R_ENDPOINT_PATH_KEYS = {
    "completions.create()": "completions",
    "images.generate()": "images_generations",
    "messages.count_tokens()": "count_tokens",
    "models.retrieve()": "model",
    "videos.create()": "create_video",
    "audio.speech.create()": "audio_speech",
    "videos.retrieve()": "retrieve_video",
    "videos.download_content()": "download_video_content",
}

# Dynamic paths must show the caller-provided identifier flowing through the
# language's encoder between the exact prefix and suffix. Prefix/suffix
# substring checks are insufficient: `/videos/static/content` is not evidence
# for `/videos/{id}/content`.
DYNAMIC_ROUTE_PATTERNS = {
    "go": {
        "models.retrieve()": r'"/models/"\s*\+\s*strings\.Join\(parts,\s*"/"\)',
        "videos.retrieve()": r'"/videos/"\s*\+\s*url\.PathEscape\(id\)',
        "videos.download_content()": r'"/videos/"\s*\+\s*url\.PathEscape\(id\)\s*\+\s*"/content"',
    },
    "java": {
        "models.retrieve()": r'"/models/"\s*\+\s*encodeModelId\(modelId\)',
        "videos.retrieve()": r'"/videos/"\s*\+\s*encodeSegment\(videoId,\s*"videoId"\)',
        "videos.download_content()": r'"/videos/"\s*\+\s*encodeSegment\(videoId,\s*"videoId"\)\s*\+\s*"/content"',
    },
    "kotlin": {
        "models.retrieve()": r'"/models/\$\{modelPath\(modelID\)\}"',
        "videos.retrieve()": r'"/videos/\$\{pathSegment\(videoID\)\}"',
        "videos.download_content()": r'"/videos/\$\{pathSegment\(videoID\)\}/content"',
    },
    "swift": {
        "models.retrieve()": r'"/models/\\\(modelPath\(modelID\)\)"',
        "videos.retrieve()": r'"/videos/\\\(pathSegment\(videoID\)\)"',
        "videos.download_content()": r'"/videos/\\\(pathSegment\(videoID\)\)/content"',
    },
    "rust": {
        "models.retrieve()": r'format!\("/models/\{\}",\s*percent_encode_model_id\(model_id\)\)',
        "videos.retrieve()": r'format!\("/videos/\{\}",\s*percent_encode_segment\(video_id\)\)',
        "videos.download_content()": r'format!\("/videos/\{\}/content",\s*percent_encode_segment\(video_id\)\)',
    },
    "dart": {
        "models.retrieve()": r"'/models/\$\{modelId\.split\('/'\)\.map\(Uri\.encodeComponent\)\.join\('/'\)\}'",
        "videos.retrieve()": r"'/videos/\$\{Uri\.encodeComponent\(videoId\)\}'",
        "videos.download_content()": r"'/videos/\$\{Uri\.encodeComponent\(videoId\)\}/content'",
    },
    "js": {
        "models.retrieve()": r"`/models/\$\{encodeModelId\(modelId\)\}`",
        "videos.retrieve()": r"`/videos/\$\{encodePathSegment\(id,\s*'video id'\)\}`",
        "videos.download_content()": r"`/videos/\$\{encodePathSegment\(id,\s*'video id'\)\}/content`",
    },
    "python": {
        "videos.retrieve()": r'f"/v1/videos/\{quote\(video_id,\s*safe=\'\'\)\}"',
        "videos.download_content()": r'f"/v1/videos/\{quote\(video_id,\s*safe=\'\'\)\}/content"',
    },
}

DYNAMIC_ROUTE_PRECONDITIONS = {
    "go": {
        "models.retrieve()": (
            r'parts\s*:=\s*strings\.Split\(id,\s*"/"\).*?'
            r"for\s+i\s*:=\s*range\s+parts\s*\{\s*"
            r"parts\[i\]\s*=\s*url\.PathEscape\(parts\[i\]\)\s*\}"
        ),
    },
}

TRANSPORT_CALL_PATTERNS = {
    "go": r"\bc\.(?:Post|Get|Bytes|Multipart)\(",
    "java": r"\b(?:post|postBinary|get|getBinary|postMultipart)\(",
    "kotlin": r"\b(?:post|get|bytes|multipart)\(",
    "swift": r"\b(?:post|get|bytes|multipart)\(",
    "rust": r"\bself\.(?:post|get|bytes|multipart)\(",
    "dart": r"\b(?:post|get|bytes|multipart)\(",
    "r": r"\bnrouter_(?:request|bytes|multipart)\(",
    "python": r"\b_nrouter_(?:post|get|get_bytes)\(",
    "js": r"\b(?:runChat|jsonRequest|this\.send|this\.audioUpload|this\.client\s*\.get)\(",
}

NEXT_FUNCTION_PATTERNS = {
    "go": r"^func\s+\(",
    "java": r"^\s+(?:public|private|protected)\s+",
    "kotlin": r"^\s+(?:public|private)\s+(?:suspend\s+)?fun\s+",
    "swift": r"^\s+(?:public|private)\s+func\s+",
    "rust": r"^\s+(?:pub\s+)?(?:async\s+)?fn\s+",
    "dart": r"^\s+(?:Future|Stream|void)\b",
    "r": r"^nrouter_[a-z0-9_]+\s*<-\s*function\(",
}

R_ENDPOINT_MAPPING_PATTERNS = {
    "completions.create()": r'completions\s*=\s*"/completions"',
    "images.generate()": r'images_generations\s*=\s*"/images/generations"',
    "messages.count_tokens()": r'count_tokens\s*=\s*"/messages/count_tokens"',
    "models.retrieve()": r'model\s*=\s*paste0\("/models/",\s*model_id\(id\)\)',
    "videos.create()": r'create_video\s*=\s*"/videos"',
    "audio.speech.create()": r'audio_speech\s*=\s*"/audio/speech"',
    "videos.retrieve()": r'retrieve_video\s*=\s*paste0\("/videos/",\s*segment\(id\)\)',
    "videos.download_content()": r'download_video_content\s*=\s*paste0\("/videos/",\s*segment\(id\),\s*"/content"\)',
}

DELEGATION_PROOFS = {
    "js": (
        ("source inheritance", "sdks/js/src/client.ts", r"export\s+class\s+nRouter\s+extends\s+OpenAI"),
        ("bounded vendor dependency", "sdks/js/package.json", r'"openai"\s*:\s*"\^7\.8\.0"'),
    ),
    "python": (
        ("sync source inheritance", "sdks/python/nroutersdk/client.py", r"class\s+nRouter\(_OpenAI\)"),
        ("async source inheritance", "sdks/python/nroutersdk/client.py", r"class\s+AsyncnRouter\(_AsyncOpenAI\)"),
        ("bounded vendor dependency", "sdks/python/pyproject.toml", r'"openai>=3\.6\.0,<4"'),
    ),
}

# The four text-generation wires are genuinely incremental in every native
# transport. Keep that a contract rather than a README claim.
STREAMING_NATIVE = FIRST_PARTY_NATIVE
STREAM_HELPERS = {
    "chatCompletions": "chatCompletionsStream",
    "completions": "completionsStream",
    "messages": "messagesStream",
    "responses": "responsesStream",
}

# Canonical operation names come from the spec. Every native SDK uses the same
# conceptual helper name, translated only into that language's naming style.
# Requiring the symbol as well as the path prevents `/videos/{id}/content` from
# accidentally satisfying the check for a deleted `/videos/{id}` helper.
HELPER_BASENAMES = {
    "chat.completions.create()": "chatCompletions",
    "completions.create()": "completions",
    "embeddings.create()": "embeddings",
    "images.generate()": "imagesGenerations",
    "videos.create()": "createVideo",
    "audio.speech.create()": "audioSpeech",
    "audio.transcriptions.create()": "audioTranscriptions",
    "models.list()": "models",
    "models.retrieve()": "model",
    "messages.create()": "messages",
    "messages.count_tokens()": "countTokens",
    "responses.create()": "responses",
    "audio.translations.create()": "audioTranslations",
    "videos.retrieve()": "retrieveVideo",
    "videos.download_content()": "downloadVideoContent",
}


def snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def native_helper_pattern(sdk: str, basename: str) -> str:
    snake = snake_case(basename)
    patterns = {
        "go": rf"func\s+\(c \*Client\)\s+{basename[0].upper() + basename[1:]}\(",
        "java": rf"public\s+NRouter(?:Http|Binary)Response\s+{basename}\(",
        "kotlin": rf"public\s+suspend\s+fun\s+{basename}\(",
        "swift": rf"public\s+func\s+{basename}\(",
        "rust": rf"pub\s+async\s+fn\s+{snake}\(",
        "dart": rf"Future<NRouter[^>]*>\s+{basename}\(",
        "r": rf"nrouter_{snake}\s*<-\s*function\(",
    }
    return patterns[sdk]


def stream_helper_pattern(sdk: str, basename: str) -> str:
    snake = snake_case(basename)
    patterns = {
        "go": rf"func\s+\(c \*Client\)\s+{basename[0].upper() + basename[1:]}\(",
        "java": rf"public\s+NRouterStreamResponse\s+{basename}\(",
        "kotlin": rf"public\s+fun\s+{basename}\(",
        "swift": rf"public\s+func\s+{basename}\(",
        "rust": rf"pub\s+async\s+fn\s+{snake}\(",
        "dart": rf"Stream<NRouterStreamChunk>\s+{basename}\(",
        "r": rf"nrouter_{snake}\s*<-\s*function\(",
    }
    return patterns[sdk]


def path_markers_present(region: str, endpoint: dict) -> bool:
    """Require one route's literals inside the helper that claims the route."""
    wire_path = endpoint["path"].removeprefix("/v1")
    candidates = (wire_path, "/v1" + wire_path)
    if "{" not in wire_path:
        return any(
            re.search(rf'["\']{re.escape(candidate)}["\']', region) is not None
            for candidate in candidates
        )

    prefix, remainder = wire_path.split("{", 1)
    suffix = remainder.split("}", 1)[1]
    prefix_seen = prefix in region or ("/v1" + prefix) in region
    return prefix_seen and (not suffix or suffix in region)


def helper_region(blob: str, sdk: str, operation: str) -> str | None:
    basename = HELPER_BASENAMES.get(operation)
    if basename is None:
        return None
    match = re.search(native_helper_pattern(sdk, basename), blob)
    if match is None:
        return None

    following = re.search(
        NEXT_FUNCTION_PATTERNS[sdk],
        blob[match.end():],
        flags=re.MULTILINE,
    )
    end = match.end() + following.start() if following is not None else len(blob)
    # The route call is adjacent to every public helper. Bound the last helper
    # too, so a generic transport path much later in the file cannot satisfy it.
    return blob[match.start():min(end, match.start() + 2_000)]


def braced_region(blob: str, signature_pattern: str) -> str | None:
    """Return one function body, balancing nested braces and quoted strings."""
    signature = re.search(
        signature_pattern,
        blob,
        flags=re.MULTILINE | re.DOTALL,
    )
    if signature is None:
        return None
    opening = (
        signature.end() - 1
        if signature.group(0).endswith("{")
        else blob.find("{", signature.end())
    )
    if opening < 0:
        return None

    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(opening, len(blob)):
        char = blob[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'", "`"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return blob[signature.start(): index + 1]
    return None


def js_chat_route_present(root: Path) -> bool:
    """Prove the scoped wrapper → selector → runner → POST call chain."""
    client_path = root / "sdks/js/src/client.ts"
    chat_path = root / "sdks/js/src/chat.ts"
    if not client_path.exists() or not chat_path.exists():
        return False
    client = strip_comments(client_path.read_text(encoding="utf-8", errors="replace"))
    chat = strip_comments(chat_path.read_text(encoding="utf-8", errors="replace"))

    wrapper = braced_region(
        client,
        r"^\s{2}chat\(opts:\s*NRouterCallOptions\):\s*Promise<",
    )
    selector = braced_region(chat, r"^export\s+async\s+function\s+chat\(")
    handoff = braced_region(chat, r"^async\s+function\s+send\(")
    request = braced_region(
        client,
        r"^\s{2}async\s+request\(.*?^\s{2}>\s*\{",
    )
    if any(part is None for part in (wrapper, selector, handoff, request)):
        return False
    assert wrapper is not None and selector is not None
    assert handoff is not None and request is not None

    selector_call = balanced_call(selector, r"\bsend")
    handoff_call = balanced_call(handoff, r"\brunner\.request")
    return (
        re.search(r"return\s+runChat\(this,\s*opts\)", wrapper) is not None
        and re.search(r"CHAT_PATH\s*=\s*['\"]/chat/completions['\"]", chat)
        is not None
        and selector_call is not None
        and re.search(
            r"messagesWire\s*\?\s*MESSAGES_PATH\s*:\s*CHAT_PATH",
            selector_call,
        )
        is not None
        and handoff_call is not None
        and re.search(r"runner\.request\(path,\s*body\)", handoff_call) is not None
        and re.search(
            r"typeof\s+pathOrReq\s*===\s*'string'.*?"
            r"\?\s*\{\s*method:\s*'POST',\s*path:\s*pathOrReq,",
            request,
            flags=re.DOTALL,
        )
        is not None
    )


def js_audio_upload_present(root: Path) -> bool:
    """Prove native audio helpers' shared upload seam performs a POST."""
    path = root / "sdks/js/src/multimodal.ts"
    if not path.exists():
        return False
    blob = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
    region = braced_region(blob, r"^\s{2}private\s+async\s+audioUpload\(")
    if region is None:
        return False
    call = balanced_call(region, r"\bthis\.send")
    return call is not None and re.search(
        r"this\.send\(\s*'POST'\s*,\s*path\s*,",
        call,
    ) is not None


def balanced_call(region: str, callee_pattern: str) -> str | None:
    """Return one complete call expression, including nested path builders."""
    callee = re.search(callee_pattern, region)
    if callee is None:
        return None
    opening = region.find("(", callee.end())
    if opening < 0:
        return None

    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(opening, len(region)):
        char = region[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {'"', "'", "`"}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return region[callee.start(): index + 1]
    return None


def transport_call(region: str, sdk: str, operation: str, method: str) -> str | None:
    """Return the single route call whose transport expresses the spec verb.

    Merely finding the right path is not enough: ``GET /models`` and
    ``POST /models`` are different contracts. These patterns intentionally
    inspect the named helper's own bounded body. The callee names are the SDKs'
    tested transport seams; multipart and binary helpers need their own forms.
    """
    if method not in {"GET", "POST"}:
        return None
    if len(re.findall(TRANSPORT_CALL_PATTERNS[sdk], region)) != 1:
        return None

    multipart = operation in {
        "audio.transcriptions.create()",
        "audio.translations.create()",
    }
    binary = operation in {
        "audio.speech.create()",
        "videos.download_content()",
    }

    if sdk == "go":
        if multipart:
            pattern = r"\bc\.Multipart"
        elif binary:
            pattern = r"\bc\.Bytes"
        else:
            pattern = rf"\bc\.{method.title()}"
    elif sdk == "java":
        if multipart:
            pattern = r"\bpostMultipart"
        elif binary:
            pattern = r"\bpostBinary" if method == "POST" else r"\bgetBinary"
        else:
            pattern = r"\bpost" if method == "POST" else r"\bget"
    elif sdk in {"kotlin", "swift"}:
        if multipart:
            pattern = r"\bmultipart"
        elif binary:
            pattern = r"\bbytes"
        else:
            pattern = r"\bpost" if method == "POST" else r"\bget"
    elif sdk == "rust":
        if multipart:
            pattern = r"\bself\.multipart"
        elif binary:
            pattern = r"\bself\.bytes"
        else:
            pattern = r"\bself\.post" if method == "POST" else r"\bself\.get"
    elif sdk == "dart":
        if multipart:
            pattern = r"\bmultipart"
        elif binary:
            pattern = r"\bbytes"
        else:
            pattern = r"\bpost" if method == "POST" else r"\bget"
    elif sdk == "r":
        if multipart:
            pattern = r"\bnrouter_multipart"
        elif binary:
            pattern = r"\bnrouter_bytes"
        else:
            pattern = r"\bnrouter_request"
    elif sdk == "python":
        if method == "POST":
            pattern = r"\b_nrouter_post"
        elif binary:
            pattern = r"\b_nrouter_get_bytes"
        else:
            pattern = r"\b_nrouter_get"
    elif sdk == "js":
        if operation == "chat.completions.create()":
            pattern = r"\brunChat"
        elif operation in {
            "messages.create()",
            "messages.count_tokens()",
            "responses.create()",
        }:
            pattern = r"\bjsonRequest"
        elif operation in {"models.list()", "models.retrieve()"}:
            pattern = r"\bthis\.client\s*\.get"
        elif multipart:
            pattern = r"\bthis\.audioUpload"
        else:
            pattern = r"\bthis\.send"
    else:
        return None

    call = balanced_call(region, pattern)
    if call is None:
        return None

    # These transports select the verb through an argument rather than a
    # method-specific callee. Check that argument inside this SAME call.
    if sdk == "go" and binary:
        if re.search(rf"\bhttp\.Method{method.title()}\s*,", call) is None:
            return None
    elif sdk == "rust" and binary:
        if re.search(rf'\bself\.bytes\(\s*"{method}"\s*,', call) is None:
            return None
    elif sdk == "js" and operation not in {
        "chat.completions.create()",
        "messages.create()",
        "messages.count_tokens()",
        "responses.create()",
        "models.list()",
        "models.retrieve()",
        "audio.transcriptions.create()",
        "audio.translations.create()",
    }:
        if re.search(rf"\bthis\.send\(\s*'{method}'\s*,", call) is None:
            return None
    elif (
        sdk in {"kotlin", "swift", "dart", "r"} and binary
    ) or (sdk == "r" and not multipart):
        has_body = re.search(r",\s*body\s*\)$", call) is not None
        if has_body != (method == "POST"):
            return None
    return call


def native_route_present(blob: str, sdk: str, endpoint: dict) -> bool:
    operation = endpoint["sdk"]
    region = helper_region(blob, sdk, operation)
    if region is None:
        return False
    precondition = DYNAMIC_ROUTE_PRECONDITIONS.get(sdk, {}).get(operation)
    if precondition is not None and re.search(
        precondition, region, flags=re.DOTALL
    ) is None:
        return False
    call = transport_call(region, sdk, operation, endpoint["method"])
    if call is None:
        return False
    if "{" in endpoint["path"]:
        dynamic = DYNAMIC_ROUTE_PATTERNS.get(sdk, {}).get(operation)
        if dynamic is not None:
            return re.search(dynamic, call) is not None
        if sdk == "r" and operation in R_ENDPOINT_PATH_KEYS:
            key = R_ENDPOINT_PATH_KEYS[operation]
            return (
                f'nrouter_endpoint_path("{key}"' in call
                and re.search(R_ENDPOINT_MAPPING_PATTERNS[operation], blob) is not None
            )
        return False
    if path_markers_present(call, endpoint):
        return True
    if sdk == "r" and operation in R_ENDPOINT_PATH_KEYS:
        key = R_ENDPOINT_PATH_KEYS[operation]
        mapping = R_ENDPOINT_MAPPING_PATTERNS[operation]
        return (
            f'nrouter_endpoint_path("{key}"' in call
            and re.search(mapping, blob) is not None
        )
    return False


def python_native_helper_regions(blob: str, operation: str) -> list[str] | None:
    owners = PYTHON_NATIVE_HELPERS.get(operation)
    if owners is None:
        return None
    regions: list[str] = []
    for class_name, method_name in owners:
        block = re.search(
            rf"^class\s+{re.escape(class_name)}:.*?(?=^class\s+|\Z)",
            blob,
            flags=re.MULTILINE | re.DOTALL,
        )
        if block is None:
            return None
        method = re.search(
            rf"^\s+(?:async\s+)?def\s+{re.escape(method_name)}\(.*?"
            rf"(?=^\s+(?:async\s+)?def\s+|\Z)",
            block.group(0),
            flags=re.MULTILINE | re.DOTALL,
        )
        if method is None:
            return None
        regions.append(method.group(0))
    return regions


def js_native_helper_region(blob: str, operation: str) -> str | None:
    pattern = HYBRID_NATIVE_HELPERS["js"].get(operation)
    if pattern is None:
        return None
    match = re.search(pattern, blob)
    if match is None:
        return None
    following = []
    for other in HYBRID_NATIVE_HELPERS["js"].values():
        found = re.search(other, blob[match.end():])
        if found is not None:
            following.append(match.end() + found.start())
    end = min(following, default=len(blob))
    return blob[match.start():min(end, match.start() + 2_000)]


def route_coverage(root: Path, spec: dict) -> tuple[list[str], int, int]:
    """Prove and count every endpoint-by-SDK ownership cell.

    Native cells bind a helper to its path and verb. Delegated cells prove a
    route-specific compiled resource on a bounded vendor dependency; they do
    not pretend a toolchain-free source scan can prove that dependency's
    internal HTTP implementation.
    """
    failures: list[str] = []
    verified = 0
    endpoints = spec["supported_endpoints"]
    total = len(SDK_SOURCES) * len(endpoints)

    blobs: dict[str, str] = {}
    for sdk, rel_paths in SDK_SOURCES.items():
        parts = []
        for rel in rel_paths:
            path = root / rel
            if path.exists():
                parts.append(path.read_text(encoding="utf-8", errors="replace"))
        blobs[sdk] = strip_comments("\n".join(parts))

    delegation_ok: dict[str, bool] = {}
    for sdk, proofs in DELEGATION_PROOFS.items():
        ok = True
        for label, rel, pattern in proofs:
            path = root / rel
            text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
            if re.search(pattern, text) is None:
                failures.append(f"{sdk}: explicit route delegation lost {label} in {rel}")
                ok = False
        delegation_ok[sdk] = ok

    js_chat_ok = js_chat_route_present(root)
    js_audio_upload_ok = js_audio_upload_present(root)

    for sdk, blob in blobs.items():
        for endpoint in endpoints:
            operation = endpoint["sdk"]
            cell_ok = False

            if sdk in FIRST_PARTY_NATIVE:
                if HELPER_BASENAMES.get(operation) is None:
                    failures.append(
                        f"conformance gate: no native helper mapping for {operation} "
                        f"({endpoint['method']} {endpoint['path']})"
                    )
                    continue
                cell_ok = native_route_present(blob, sdk, endpoint)
            elif sdk in DELEGATES:
                owner = DELEGATES[sdk]["owner"]
                owner_blob = blobs.get(owner, "")
                # Android returns the Kotlin NRouter itself; it has no second
                # route implementation to drift. Bind each delegated cell to
                # the corresponding owner helper so one missing/miswired
                # Kotlin route invalidates BOTH Kotlin and Android evidence.
                cell_ok = (
                    all(symbol in blob for symbol in DELEGATES[sdk]["symbols"])
                    and owner in FIRST_PARTY_NATIVE
                    and native_route_present(owner_blob, owner, endpoint)
                )
            elif sdk == "python" and operation in PYTHON_NATIVE_HELPERS:
                regions = python_native_helper_regions(blob, operation)
                dynamic = DYNAMIC_ROUTE_PATTERNS["python"].get(operation)
                cell_ok = regions is not None and all(
                    (call := transport_call(
                        region, "python", operation, endpoint["method"]
                    )) is not None
                    and (
                        re.search(dynamic, call) is not None
                        if dynamic is not None
                        else path_markers_present(call, endpoint)
                    )
                    for region in regions
                )
            elif operation in HYBRID_NATIVE_HELPERS.get(sdk, {}):
                region = js_native_helper_region(blob, operation)
                if sdk == "js" and operation == "chat.completions.create()":
                    cell_ok = region is not None and js_chat_ok
                else:
                    dynamic = DYNAMIC_ROUTE_PATTERNS["js"].get(operation)
                    call = (
                        transport_call(region, sdk, operation, endpoint["method"])
                        if region is not None
                        else None
                    )
                    cell_ok = call is not None and (
                        re.search(dynamic, call) is not None
                        if dynamic is not None
                        else path_markers_present(call, endpoint)
                    )
                    if operation in {
                        "audio.transcriptions.create()",
                        "audio.translations.create()",
                    }:
                        cell_ok = cell_ok and js_audio_upload_ok
            elif operation in DELEGATED_ROUTE_PROOFS.get(sdk, {}):
                cell_ok = delegation_ok.get(sdk, False) and re.search(
                    DELEGATED_ROUTE_PROOFS[sdk][operation], blob, flags=re.DOTALL
                ) is not None
            else:
                failures.append(
                    f"{sdk}: {endpoint['method']} {endpoint['path']} has no declared "
                    "native helper or explicit delegation owner"
                )
                continue

            if cell_ok:
                verified += 1
            else:
                failures.append(
                    f"{sdk}: supported endpoint {endpoint['method']} "
                    f"{endpoint['path']} has no executable native helper or valid delegation"
                )

    return failures, verified, total


# An SDK that only wraps a vendor client does not restate every constant: the
# vendor SDK owns the transport, so headers and error codes live in the wrapper
# only where it adds them. These SDKs are held to the connection contract (base
# URL, env var, key prefix) and exempted from the rest, with the reason stated
# so the exemption is a decision rather than an oversight.
WRAPPER_ONLY = {
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
    return json.loads(SPEC.read_text(encoding="utf-8"))


def check_release_versions(root: Path, spec: dict) -> list[str]:
    """Require one release version across all ten SDK distributions."""
    failures: list[str] = []
    canonical = spec["version"]

    def text(relative: str) -> str:
        path = root / relative
        if not path.exists():
            failures.append(f"release version: missing {relative}")
            return ""
        return path.read_text(encoding="utf-8", errors="replace")

    def match(relative: str, pattern: str) -> str | None:
        found = re.search(pattern, text(relative), flags=re.MULTILINE | re.DOTALL)
        if found is None:
            failures.append(f"release version: cannot parse {relative}")
            return None
        return found.group(1)

    def prop(relative: str, name: str) -> str | None:
        return match(relative, rf"^{re.escape(name)}\s*=\s*([^\s]+)$")

    js_manifest = text("sdks/js/package.json")
    js_lock = text("sdks/js/package-lock.json")
    try:
        js_version = json.loads(js_manifest)["version"]
        lock = json.loads(js_lock)
        js_lock_versions = [lock["version"], lock["packages"][""]["version"]]
    except (KeyError, TypeError, json.JSONDecodeError):
        failures.append("release version: cannot parse JavaScript package metadata")
        js_version = None
        js_lock_versions = []

    java_version = None
    java_pom = text("sdks/java/pom.xml")
    if java_pom:
        try:
            pom = ET.fromstring(java_pom)
            java_version = pom.findtext("{http://maven.apache.org/POM/4.0.0}version")
        except ET.ParseError:
            failures.append("release version: cannot parse sdks/java/pom.xml")

    versions = {
        "javascript": js_version,
        "python": match("sdks/python/pyproject.toml", r'^version\s*=\s*"([^"]+)"'),
        "java": java_version,
        "kotlin": prop("sdks/kotlin/gradle.properties", "version"),
        "android": prop("sdks/android/gradle.properties", "version"),
        "go": text("sdks/go/VERSION").strip() or None,
        "rust": match("sdks/rust/Cargo.toml", r'^version\s*=\s*"([^"]+)"'),
        "swift": text("sdks/swift/VERSION").strip() or None,
        "dart": match("sdks/dart/pubspec.yaml", r"^version:\s*([^\s]+)$"),
        "r": match("sdks/r/DESCRIPTION", r"^Version:\s*([^\s]+)$"),
    }
    for sdk, version in versions.items():
        if version != canonical:
            failures.append(
                f"{sdk}: release version {version!r} does not match spec {canonical!r}"
            )

    for version in js_lock_versions:
        if version != canonical:
            failures.append(
                f"javascript: package-lock version {version!r} does not match spec {canonical!r}"
            )

    coupled = {
        "python import": match(
            "sdks/python/nroutersdk/_version.py", r'^__version__\s*=\s*"([^"]+)"'
        ),
        "rust lock": match(
            "sdks/rust/Cargo.lock",
            r'\[\[package\]\]\s+name = "nrouter"\s+version = "([^"]+)"',
        ),
        "android Kotlin dependency": match(
            "sdks/android/build.gradle.kts", r'nrouter-sdk-kotlin:([^"]+)"'
        ),
        "android dependency lock": match(
            "sdks/android/gradle.lockfile",
            r"^ai\.nrouter:nrouter-sdk-kotlin:([^=]+)=",
        ),
    }
    for label, version in coupled.items():
        if version != canonical:
            failures.append(
                f"{label}: version {version!r} does not match spec {canonical!r}"
            )

    major = canonical.split(".", 1)[0]
    go_module = match("sdks/go/go.mod", r"^module\s+([^\s]+)$")
    if int(major) >= 2 and go_module and not go_module.endswith(f"/v{major}"):
        failures.append(
            f"go: version {canonical} requires module path suffix /v{major}; got {go_module}"
        )

    return failures


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
        return [
            f"swift: {shipping.name} is missing from the SDK root — SwiftPM "
            f"reads the manifest from the repository root and consumers "
            f"cannot resolve the package without it"
        ]
    if not nested.exists():
        return []

    def platforms(text: str) -> set[str]:
        block = re.search(r"platforms:\s*\[(.*?)\]", text, re.S)
        return (
            set(re.findall(r"\.(\w+)\(\.(\w+)\)", block.group(1))) if block else set()
        )

    def names(text: str, kind: str) -> set[str]:
        return set(re.findall(rf'\.{kind}\(\s*name:\s*"([^"]+)"', text))

    a, b = shipping.read_text(encoding="utf-8"), nested.read_text(encoding="utf-8")

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
            blob_parts.append(path.read_text(encoding="utf-8", errors="replace"))
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

        if sdk in STREAMING_NATIVE:
            for basename in STREAM_HELPERS.values():
                if re.search(stream_helper_pattern(sdk, basename), blob) is None:
                    failures.append(
                        f"{sdk}: native streaming helper {basename!r} is missing"
                    )

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

    route_failures, _, _ = route_coverage(root, spec)
    failures.extend(route_failures)
    failures.extend(check_swift_manifests(root))
    failures.extend(check_release_versions(root, spec))
    failures.extend(check_doc_wires(root, spec))
    failures.extend(check_source_defaults(root))
    failures.extend(check_client_timeouts(root))
    # SDKDOC-001 — a DERIVED count restated as prose rots on the next header.
    failures.extend(check_doc_header_count(root))
    # SDKENUM-001 — and the harder shape the count gate could not see: a
    # completeness PROMISE ("every `x-nr-*` header") standing over an
    # enumeration. `5f05390` created exactly that in five READMEs by obeying the
    # count gate and leaving the fourteen-item lists in place, which is a
    # STRONGER false claim than the count it replaced.
    failures.extend(check_doc_header_enumeration(root))
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

    # The fixtures intentionally mutate files containing Unicode. pathlib uses
    # the Windows ANSI code page when encoding is omitted, which can corrupt a
    # fixture before the gate gets a chance to inspect it.
    original_write_text = Path.write_text

    def write_fixture_text(path: Path, data: str, encoding=None, errors=None, newline=None):
        return original_write_text(
            path,
            data,
            encoding=encoding or "utf-8",
            errors=errors or "strict",
            newline=newline,
        )

    Path.write_text = write_fixture_text

    spec = load_spec()
    problems = []

    if check():
        problems.append("baseline check is not green; fix conformance first")

    # The doc-wire half proves itself the same way, by planting each violation
    # in a fixture tree and asserting it is reported.
    if doc_wires_self_test():
        problems.append("doc_wires self-test failed; see its own output above")

    # So does the default-model half.
    if source_defaults_self_test():
        problems.append("source_defaults self-test failed; see its own output above")

    # And the client-behaviour half — deadlines and the no-retry-on-a-billed-
    # request pin. Importing only `check_client_timeouts` and not its
    # `self_test` would leave its planted cases unreachable from here, so a
    # broken regex would print green while catching nothing.
    if client_timeouts_self_test():
        problems.append("client_timeouts self-test failed; see its own output above")

    # And the header-set half, which is now TWO checks — the hard-coded count
    # and the enumerated completeness promise — sharing one `self_test`.
    # Importing only the check functions and not their `self_test` would leave
    # the fixture cases
    # unreachable from `check_conformance.py --self-test`, so a broken regex
    # would go green here while catching nothing — the exact shape the
    # workspace calls "a gate that prints green while checking nothing".
    # Caught by the claude-opus-4-6-thinking review of the slice that added it.
    if doc_header_count_self_test():
        problems.append("doc_header_count self-test failed; see its own output above")

    # --- half one: the SPEC moves, every SDK must go red ---------------------
    for label, mutate in (
        ("base_url", lambda d: d.update(base_url="https://api-stage.nrouter.ai/v1")),
        ("env_var", lambda d: d.update(env_var="NROUTER_TOKEN")),
        ("a new header", lambda d: d["response_headers"].update({"x-nr-invented": {}})),
        (
            "a new error code",
            lambda d: d["errors"].update({"invented_code": {"http": 400}}),
        ),
        # Moving an EXISTING code's status must also bite: the contract is the
        # code AND its status, and a gate blind to `http` lets one drift.
        # A status leaving the spec's set must bite. (Moving a code ONTO an
        # existing status does not — see the LIMIT note in check().)
        (
            "an existing code's http",
            lambda d: d["errors"]["guardrail_blocked"].update({"http": 422}),
        ),
    ):
        mutated = json.loads(json.dumps(spec))
        mutate(mutated)
        if not check(spec=mutated):
            problems.append(f"changing {label} did not fail the check")

    # --- half two: a real SDK LOSES something, that SDK must go red ----------
    with tempfile.TemporaryDirectory() as tmp:
        fake_root = Path(tmp)
        copied_paths = {r for paths in SDK_SOURCES.values() for r in paths}
        copied_paths.update(RELEASE_METADATA_PATHS)
        for rel in copied_paths:
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

        # A package-version drift must stop every publish workflow that invokes
        # this gate, before any registry credential becomes reachable.
        victim = fake_root / "sdks/js/package.json"
        text = victim.read_text(encoding="utf-8")
        victim.write_text(
            text.replace(f'"version": "{spec["version"]}"', '"version": "0.0.0"', 1)
        )
        failures = check(root=fake_root)
        if not any("javascript: release version" in f for f in failures):
            problems.append("changing a real package version did not fail the check")
        victim.write_text(text)

        # Delete a header this SDK really reads.
        victim = fake_root / "sdks/rust/src/meta.rs"
        text = victim.read_text(encoding="utf-8")
        victim.write_text(text.replace('"x-nr-response-cache-age",\n', "", 1))
        failures = check(root=fake_root)
        if not any("x-nr-response-cache-age" in f and "rust" in f for f in failures):
            problems.append(
                "deleting a real header from a real SDK did not fail the check"
            )
        victim.write_text(text)

        # Delete one native streaming helper. Streaming is a public capability,
        # so a buffered-only regression must not pass the shared gate.
        victim = fake_root / "sdks/go/stream.go"
        text = victim.read_text(encoding="utf-8")
        victim.write_text(text.replace("MessagesStream(", "RemovedMessagesStream(", 1))
        failures = check(root=fake_root)
        if not any("messagesStream" in f and "go" in f for f in failures):
            problems.append("deleting a real streaming helper did not fail the check")
        victim.write_text(text)

        # Java's native metadata surface is additive to openai-java. Losing a
        # named native helper must not hide behind the vendor factory.
        victim = fake_root / "sdks/java/src/main/java/ai/nrouter/sdk/NRouterHttpClient.java"
        text = victim.read_text(encoding="utf-8")
        victim.write_text(
            text.replace(
                "public NRouterHttpResponse embeddings(",
                "public NRouterHttpResponse removedEmbeddings(",
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/embeddings" in f and "java" in f for f in failures):
            problems.append("deleting a real Java endpoint helper did not fail the check")
        victim.write_text(text)

        victim.write_text(
            text.replace(
                "public NRouterStreamResponse messagesStream(",
                "public NRouterStreamResponse removedMessagesStream(",
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("messagesStream" in f and "java" in f for f in failures):
            problems.append("deleting a real Java streaming helper did not fail the check")
        victim.write_text(text)

        # Delete a real native helper while leaving its path string behind.
        # A path-only gate would miss this because the generic transport can
        # still send arbitrary paths; completeness requires the public helper.
        victim = fake_root / "sdks/go/client.go"
        text = victim.read_text(encoding="utf-8")
        victim.write_text(
            text.replace(
                "func (c *Client) ImagesGenerations",
                "func (c *Client) RemovedImagesGenerations",
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/images/generations" in f and "go" in f for f in failures):
            problems.append(
                "deleting a real native endpoint helper did not fail the check"
            )
        victim.write_text(text)

        # JS owns its multimodal transport. Losing one of those helpers must
        # fail even though the inherited OpenAI client still has other routes.
        victim = fake_root / "sdks/js/src/multimodal.ts"
        text = victim.read_text(encoding="utf-8")
        victim.write_text(text.replace("async speech(", "async removedSpeech(", 1))
        failures = check(root=fake_root)
        if not any("/v1/audio/speech" in f and "js" in f for f in failures):
            problems.append("deleting a real JS endpoint helper did not fail the check")
        victim.write_text(text)

        victim.write_text(
            text.replace(
                "this.send('POST', path, body, options)",
                "this.send('GET', path, body, options)",
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/audio/transcriptions" in f and "js" in f for f in failures):
            problems.append("miswiring the JS audio-upload method did not fail the check")
        victim.write_text(text)

        # The inherited route proof is route-specific and type-checked by each
        # SDK's native lane,
        # not one generic "extends OpenAI" waiver for the whole SDK.
        victim = fake_root / "sdks/js/src/client.ts"
        text = victim.read_text(encoding="utf-8")
        victim.write_text(
            text.replace(
                'OpenAI["completions"]["create"]',
                'OpenAI["completions"]["removed"]',
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/completions" in f and "js" in f for f in failures):
            problems.append("deleting JS delegated-route evidence did not fail the check")
        victim.write_text(text)

        # The public chat helper crosses client.ts and chat.ts. Losing the
        # concrete POST construction must invalidate the route even while the
        # correct path constant and runChat wrapper remain.
        victim.write_text(
            text.replace(
                "? { method: 'POST', path: pathOrReq,",
                "? { method: 'GET', path: pathOrReq,",
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/chat/completions" in f and "js" in f for f in failures):
            problems.append("miswiring the JS chat transport method did not fail the check")
        victim.write_text(text)

        victim = fake_root / "sdks/js/src/chat.ts"
        text = victim.read_text(encoding="utf-8")
        victim.write_text(
            text.replace(
                "messagesWire ? MESSAGES_PATH : CHAT_PATH,",
                "messagesWire ? MESSAGES_PATH : MESSAGES_PATH,",
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/chat/completions" in f and "js" in f for f in failures):
            problems.append("miswiring JS chat path selection did not fail the check")
        victim.write_text(text)

        # Python's video helpers are native additions to the inherited OpenAI
        # client. A deleted helper must not hide behind that inheritance seam.
        victim = fake_root / "sdks/python/nroutersdk/client.py"
        text = victim.read_text(encoding="utf-8")
        victim.write_text(
            text.replace("def download_content(", "def removed_download_content(", 1)
        )
        failures = check(root=fake_root)
        if not any(
            "/v1/videos/{id}/content" in f and "python" in f for f in failures
        ):
            problems.append("deleting a real Python endpoint helper did not fail the check")
        victim.write_text(text)

        # Python exposes parallel sync and async native collections. A route
        # cell is complete only when BOTH implementations remain wired.
        victim.write_text(
            text.replace(
                "async def download_content(",
                "async def removed_download_content(",
                1,
            )
        )
        failures = check(root=fake_root)
        if not any(
            "/v1/videos/{id}/content" in f and "python" in f for f in failures
        ):
            problems.append("deleting a Python async endpoint helper did not fail the check")
        victim.write_text(text)

        victim.write_text(
            text.replace("sync.audio.speech.create", "sync.audio.speech.removed", 1)
        )
        failures = check(root=fake_root)
        if not any("/v1/audio/speech" in f and "python" in f for f in failures):
            problems.append("deleting Python delegated-route evidence did not fail the check")
        victim.write_text(text)

        victim.write_text(
            text.replace(
                "asynchronous.audio.speech.create",
                "asynchronous.audio.speech.removed",
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/audio/speech" in f and "python" in f for f in failures):
            problems.append("deleting Python async delegation evidence did not fail the check")
        victim.write_text(text)

        # Bind the path to the helper's own body. Leaving the correct string in
        # a streaming helper or generic transport elsewhere must not satisfy
        # the buffered route cell.
        victim = fake_root / "sdks/go/client.go"
        text = victim.read_text(encoding="utf-8")
        victim.write_text(
            text.replace(
                'return c.Post(ctx, "/chat/completions", body)',
                'return c.Post(ctx, "/removed", body)',
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/chat/completions" in f and "go" in f for f in failures):
            problems.append("miswiring a native helper path did not fail the check")
        victim.write_text(text)

        # The path can remain exactly right while the verb becomes wrong.
        # Prove method evidence is independently load-bearing.
        victim.write_text(
            text.replace(
                'return c.Post(ctx, "/chat/completions", body)',
                'return c.Get(ctx, "/chat/completions")',
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/chat/completions" in f and "go" in f for f in failures):
            problems.append("miswiring a native helper HTTP method did not fail the check")
        victim.write_text(text)

        # The expected verb elsewhere in the same helper cannot combine with
        # the expected path on a different call. They must be one route call.
        victim.write_text(
            text.replace(
                'return c.Post(ctx, "/chat/completions", body)',
                'c.Post(ctx, "/unrelated", body)\n\treturn c.Get(ctx, "/chat/completions")',
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/chat/completions" in f and "go" in f for f in failures):
            problems.append("split path and verb markers did not fail the check")
        victim.write_text(text)

        victim.write_text(
            text.replace(
                'return c.Post(ctx, "/chat/completions", body)',
                'c.Post(ctx, "/chat/completions", body)\n\treturn c.Get(ctx, "/wrong")',
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/chat/completions" in f and "go" in f for f in failures):
            problems.append("a decoy correct route call did not fail the check")
        victim.write_text(text)

        victim.write_text(
            text.replace(
                'return c.Get(ctx, "/videos/"+url.PathEscape(id))',
                'return c.Get(ctx, "/videos/static")',
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/videos/{id}" in f and "go" in f for f in failures):
            problems.append("removing a dynamic route parameter did not fail the check")
        victim.write_text(text)

        victim.write_text(
            text.replace(
                'parts := strings.Split(id, "/")',
                'parts := strings.Split("fixed", "/")',
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/models/{model_id}" in f and "go" in f for f in failures):
            problems.append("disconnecting the Go model id did not fail the check")
        victim.write_text(text)

        victim.write_text(
            text.replace(
                "parts[i] = url.PathEscape(parts[i])",
                "parts[i] = parts[i]",
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/models/{model_id}" in f and "go" in f for f in failures):
            problems.append("removing Go model-id encoding did not fail the check")
        victim.write_text(text)

        victim = fake_root / "sdks/r/R/client.R"
        text = victim.read_text(encoding="utf-8")
        victim.write_text(
            text.replace(
                'retrieve_video = paste0("/videos/", segment(id))',
                'retrieve_video = "/videos/static"',
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/videos/{id}" in f and "r" in f for f in failures):
            problems.append("miswiring the R endpoint map did not fail the check")
        victim.write_text(text)

        victim = fake_root / "sdks/js/src/multimodal.ts"
        text = victim.read_text(encoding="utf-8")
        victim.write_text(
            text.replace(
                "`/videos/${encodePathSegment(id, 'video id')}`",
                "'/videos/static'",
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/videos/{id}" in f and "js" in f for f in failures):
            problems.append("miswiring a JS dynamic helper did not fail the check")
        victim.write_text(text)

        # Android intentionally delegates every wire to Kotlin. Removing the
        # delegation seam must invalidate all route-cell evidence, not merely
        # the base-URL check.
        victim = fake_root / "sdks/android/src/main/kotlin/ai/nrouter/sdk/android/NRouterAndroid.kt"
        text = victim.read_text(encoding="utf-8")
        victim.write_text(text.replace("ai.nrouter.sdk.NRouter", "removed.sdk.NRouter"))
        failures = check(root=fake_root)
        if not any("/v1/chat/completions" in f and "android" in f for f in failures):
            problems.append("breaking Android route delegation did not fail the check")
        victim.write_text(text)

        # Delegation is endpoint-specific: Android returns the Kotlin client,
        # so one owner route drifting must invalidate the matching Android cell
        # rather than leaving all 15 green behind one shared class symbol.
        victim = fake_root / "sdks/kotlin/src/main/kotlin/ai/nrouter/sdk/NRouter.kt"
        text = victim.read_text(encoding="utf-8")
        victim.write_text(
            text.replace(
                'post("/images/generations", body)',
                'post("/removed", body)',
                1,
            )
        )
        failures = check(root=fake_root)
        if not any("/v1/images/generations" in f and "android" in f for f in failures):
            problems.append("a delegated Android endpoint drift did not fail its route cell")
        victim.write_text(text)

        # Delete an error code this SDK really maps.
        victim = fake_root / "sdks/dart/lib/src/errors.dart"
        text = victim.read_text(encoding="utf-8")
        victim.write_text(text.replace("'guardrail_blocked'", "'REMOVED'"))
        stream_victim = fake_root / "sdks/dart/lib/src/client.dart"
        stream_text = stream_victim.read_text(encoding="utf-8")
        stream_victim.write_text(
            stream_text.replace("'guardrail_blocked'", "'REMOVED'")
        )
        failures = check(root=fake_root)
        if not any("guardrail_blocked" in f and "dart" in f for f in failures):
            problems.append(
                "deleting a real error code from a real SDK did not fail the check"
            )
        victim.write_text(text)
        stream_victim.write_text(stream_text)

        # Plant a retired spelling.
        victim = fake_root / "sdks/swift/Sources/NRouter/NRouter.swift"
        text = victim.read_text(encoding="utf-8")
        victim.write_text(text + f"\n// {RETIRED[0]}\n")
        if not any("retired spelling" in f for f in check(root=fake_root)):
            problems.append("a retired spelling in a real SDK did not fail the check")
        victim.write_text(text)

        # The two Swift manifests must be held together: only the root one
        # ships, so a floor changed in the nested one alone is invisible.
        victim = fake_root / "sdks/swift/Package.swift"
        if victim.exists():
            text = victim.read_text(encoding="utf-8")
            victim.write_text(text.replace(".macOS(.v12)", ".macOS(.v13)"))
            if not any("platform floors differ" in f for f in check(root=fake_root)):
                problems.append(
                    "a Swift manifest platform drift did not fail the check"
                )
            victim.write_text(text)

        # A missing root manifest must ERROR: without it SwiftPM cannot resolve
        # the package at all.
        shipping = fake_root / "Package.swift"
        if shipping.exists():
            text = shipping.read_text(encoding="utf-8")
            shipping.unlink()
            if not any(
                "reads the manifest from the repository root" in f
                for f in check(root=fake_root)
            ):
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
        "real SDK losing an endpoint helper, a header, a code, a file, drifting "
        "a release version, or gaining a retired spelling"
    )
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    if "--feature-report" in sys.argv:
        from check_features import main as feature_report

        return feature_report()

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
    _, verified_routes, total_routes = route_coverage(ROOT, spec)
    print(f"    route ownership evidence {verified_routes}/{total_routes}")
    for sdk, why in WRAPPER_ONLY.items():
        print(f"    note: {sdk} checked for the connection contract only — {why}")
    for sdk, why in NO_ENV_RESOLUTION.items():
        print(f"    note: {sdk} does NOT resolve {spec['env_var']} — {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
