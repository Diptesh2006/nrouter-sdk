import json
import os
import re
import sys
import unittest
from pathlib import Path

# OpenAI 3.x and this SDK use the separately distributed `httpx2` package;
# keep the familiar local alias so request/response fixtures mirror client.py.
import httpx2 as httpx


# The SDK is this repo now, not a subdirectory of nrouter-ent-ai-hub. It moved
# out on 2026-08-26, so ROOT and SDK_ROOT are the same place.
ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = ROOT
PYTHON_SDK = SDK_ROOT / "sdks" / "python"
sys.path.insert(0, str(PYTHON_SDK))

from nroutersdk import (  # noqa: E402
    AsyncnRouter,
    nRouter,
    nRouterCreditError,
    nRouterGuardrailBlockedError,
    nRouterRateLimitError,
    nRouterResponseMeta,
    nRouterServiceError,
)


class SpecContractTests(unittest.TestCase):
    def test_spec_does_not_advertise_unmounted_control_plane(self) -> None:
        spec = json.loads((SDK_ROOT / "spec" / "nrouter-sdk-spec.json").read_text())
        mounted_paths = {endpoint["path"] for endpoint in spec["supported_endpoints"]}
        self.assertIn("/v1/models", mounted_paths)
        self.assertIn("control_plane", spec["unsupported_endpoints"])
        self.assertNotIn(
            "nrouter_apis",
            spec,
            "control-plane/dashboard APIs are not part of the gateway SDK contract",
        )

    def test_spec_uses_only_canonical_public_contract(self) -> None:
        spec_path = SDK_ROOT / "spec" / "nrouter-sdk-spec.json"
        spec = json.loads(spec_path.read_text())

        self.assertEqual(spec["$schema"], "https://nrouter.ai/sdk-spec/v1")
        # DERIVED, not hardcoded. This literal was a FIFTH coupled version site
        # that the "version lives in four places" test did not know about, so a
        # release bump failed here with a message about the spec rather than
        # about the bump. Comparing to the package is the invariant that was
        # meant all along.
        self.assertEqual(spec["version"], __import__("nroutersdk").__version__)
        self.assertEqual(spec["base_url"], "https://api.nrouter.ai/v1")
        self.assertEqual(spec["env_var"], "NROUTER_API_KEY")
        response_headers = set(spec["response_headers"])
        generated_contract = json.loads(
            (SDK_ROOT / "spec" / "gateway-response-headers.json").read_text()
        )
        self.assertEqual(response_headers, set(generated_contract["headers"]))

        gateway_contract = (
            ROOT.parent / "nrouter-rust-gateway" / "src" / "http" / "nr_headers.rs"
        )
        try:
            if gateway_contract.exists():
                gateway_text = re.sub(
                    r"/\*.*?\*/", "", gateway_contract.read_text(), flags=re.DOTALL
                )
                emitted_body = re.search(
                    r"pub fn all_emitted_names\(\).*?\{\s*&\[(.*?)\]\s*\}",
                    gateway_text,
                    flags=re.DOTALL,
                )
                self.assertIsNotNone(emitted_body, "gateway all_emitted_names() is missing")
                cache_contract = gateway_contract.parents[1] / "proxy" / "cache.rs"
                cache_text = re.sub(
                    r"/\*.*?\*/",
                    "",
                    cache_contract.read_text() if cache_contract.exists() else "",
                    flags=re.DOTALL,
                )
                definition_pattern = r'^pub const ([A-Z_]+): &str = "(x-nr-[^"]+)";'
                all_gateway_definitions = dict(
                    re.findall(definition_pattern, gateway_text, flags=re.MULTILINE)
                )
                internal_body = re.search(
                    r"pub const INTERNAL_WEBHOOK_HEADERS:.*?=\s*&\[(.*?)\];",
                    gateway_text,
                    flags=re.DOTALL,
                )
                self.assertIsNotNone(
                    internal_body, "gateway internal-header registry is missing"
                )
                internal_names = {
                    entry.strip()
                    for entry in re.sub(
                        r"//.*$", "", internal_body.group(1), flags=re.MULTILINE
                    ).split(",")
                    if entry.strip()
                }
                self.assertTrue(internal_names, "gateway internal-header registry is empty")
                self.assertEqual(
                    internal_names - all_gateway_definitions.keys(),
                    set(),
                )
                # REQUEST headers the gateway accepts (`x-nr-compress`, …) are
                # defined in the same module but are never emitted, so they are
                # not response-header contract. Derived from the accepted
                # registry, never listed here.
                accepted_body = re.search(
                    r"pub fn all_accepted_request_names\(\).*?\{\s*&\[(.*?)\]\s*\}",
                    gateway_text,
                    flags=re.DOTALL,
                )
                self.assertIsNotNone(
                    accepted_body, "gateway accepted-request-header registry is missing"
                )
                accepted_names = {
                    entry.strip().rsplit("::", 1)[-1]
                    for entry in re.sub(
                        r"//.*$", "", accepted_body.group(1), flags=re.MULTILINE
                    ).split(",")
                    if entry.strip()
                }
                self.assertTrue(accepted_names, "gateway accepted-request registry is empty")
                gateway_definitions = {
                    name: value
                    for name, value in all_gateway_definitions.items()
                    if name not in internal_names and name not in accepted_names
                }
                cache_pairs = re.findall(
                    definition_pattern,
                    cache_text,
                    flags=re.MULTILINE,
                )
                cache_definitions = {
                    f"crate::proxy::cache::{name}": value
                    for name, value in cache_pairs
                }
                definitions = gateway_definitions | cache_definitions
                definitions.update(
                    {
                        name: value
                        for name, value in cache_pairs
                        if name not in gateway_definitions
                    }
                )
                uncommented_body = re.sub(
                    r"//.*$", "", emitted_body.group(1), flags=re.MULTILINE
                )
                entries = [
                    entry.strip() for entry in uncommented_body.split(",") if entry.strip()
                ]
                referenced = []
                invalid_entries = []
                for entry in entries:
                    match = re.fullmatch(
                        r"(?:crate::proxy::cache::)?[A-Z][A-Z0-9_]*", entry
                    )
                    if match:
                        referenced.append(match.group(0))
                    else:
                        invalid_entries.append(entry)
                self.assertFalse(
                    invalid_entries,
                    f"gateway emitted-header registry has unparseable entries: {invalid_entries}",
                )
                self.assertTrue(referenced, "gateway all_emitted_names() is empty")
                self.assertEqual(set(referenced) - definitions.keys(), set())
                emitted_headers = {definitions[name] for name in referenced}
                declared_public_headers = set(gateway_definitions.values()) | {
                    value for _, value in cache_pairs
                }
                self.assertEqual(declared_public_headers, emitted_headers)
                self.assertEqual(response_headers, emitted_headers)
        except (OSError, PermissionError):
            pass

        self.assertEqual(spec["version"], __import__("nroutersdk").__version__)

        # DERIVED from the package, not a hand-listed set. The old literal held
        # four names; the spec advertising a fifth would have failed here with
        # "sets differ" while the real invariant — every class the spec names is
        # importable by a customer — went unstated. A name in the spec with no
        # class behind it is what makes `except nRouterNotFoundError` an
        # ImportError.
        import nroutersdk

        exported_error_names = {
            name for name in nroutersdk.__all__ if name.endswith("Error")
        }
        spec_error_names = {entry["class"] for entry in spec["errors"].values()}
        self.assertTrue(
            spec_error_names <= exported_error_names,
            f"spec names classes the package does not export: "
            f"{sorted(spec_error_names - exported_error_names)}",
        )

    def test_spec_advertises_cache_only_on_executable_buffered_text_routes(
        self,
    ) -> None:
        spec = json.loads((SDK_ROOT / "spec" / "nrouter-sdk-spec.json").read_text())
        cached = {
            "/v1/chat/completions",
            "/v1/completions",
            "/v1/messages",
            "/v1/responses",
        }
        for endpoint in spec["supported_endpoints"]:
            self.assertEqual(
                "cache" in endpoint["features"], endpoint["path"] in cached
            )
        self.assertIn(
            "nrouter_cache",
            spec["extra_body_fields"],
        )
        # `bypass` is the third outcome the gateway emits: the request opted out
        # (`nrouter_cache: false`), the call streamed, or the org disabled the
        # cache. A contract listing only hit/miss taught SDKs to classify it as
        # unknown.
        self.assertEqual(
            set(spec["response_headers"]["x-nr-response-cache"]["values"]),
            {"hit", "miss", "bypass"},
        )
        self.assertIn("x-nr-response-cache-age", spec["response_headers"])


class ClientContractTests(unittest.TestCase):
    def test_every_advertised_python_sdk_method_is_callable(self) -> None:
        spec = json.loads((SDK_ROOT / "spec" / "nrouter-sdk-spec.json").read_text())
        client = nRouter(api_key="sk-nrouter-contract-test")
        self.addCleanup(client.close)
        for endpoint in spec["supported_endpoints"]:
            cursor = client
            sdk_path = endpoint["sdk"].removesuffix("()")
            for part in sdk_path.split("."):
                cursor = getattr(cursor, part)
            self.assertTrue(
                callable(cursor),
                f"{endpoint['method']} {endpoint['path']} advertises non-callable {endpoint['sdk']}",
            )

    def test_client_rejects_non_nrouter_keys_before_request(self) -> None:
        with self.assertRaisesRegex(ValueError, "sk-nrouter-"):
            nRouter(api_key="sk-retired-example")

    def test_client_accepts_nrouter_key_and_uses_canonical_base_url(self) -> None:
        client = nRouter(api_key="sk-nrouter-contract-test")
        self.addCleanup(client.close)
        self.assertEqual(str(client.base_url), "https://api.nrouter.ai/v1/")

    def test_client_reads_key_from_canonical_environment_variable(self) -> None:
        original = os.environ.get("NROUTER_API_KEY")
        os.environ["NROUTER_API_KEY"] = "sk-nrouter-env-contract"
        try:
            client = nRouter()
            self.addCleanup(client.close)
            self.assertEqual(client.api_key, "sk-nrouter-env-contract")
        finally:
            if original is None:
                os.environ.pop("NROUTER_API_KEY", None)
            else:
                os.environ["NROUTER_API_KEY"] = original

    def test_public_response_headers_are_parsed(self) -> None:
        metadata = nRouterResponseMeta.from_headers(
            {
                "x-nr-request-id": "req_contract",
                "x-nr-request-cost": "0.0123",
                "x-nr-cost-status": "exact",
                "x-nr-model": "gpt-4o",
                "x-nr-input-tokens": "11",
                "x-nr-output-tokens": "13",
                "x-nr-total-tokens": "24",
                "x-nr-cache-read-tokens": "5",
                "x-nr-cache-write-tokens": "7",
                "x-nr-limit-source": "key",
                "x-nr-response-cache": "hit",
                "x-nr-response-cache-age": "3",
                "x-nr-budget-warning": "org soft_budget 80.00/100.00",
                # Posture only, and one of the five exact tokens. The
                # header carries no policy name, id, detector family or
                # rule count by design (gateway §4f gate 9).
                "x-nr-guardrails": "pass",
            }
        )
        self.assertEqual(metadata.request_id, "req_contract")
        self.assertEqual(metadata.cost, 0.0123)
        self.assertEqual(metadata.cost_status, "exact")
        self.assertEqual(metadata.model, "gpt-4o")
        self.assertEqual(metadata.input_tokens, 11)
        self.assertEqual(metadata.output_tokens, 13)
        self.assertEqual(metadata.total_tokens, 24)
        self.assertEqual(metadata.cache_read_tokens, 5)
        self.assertEqual(metadata.cache_write_tokens, 7)
        self.assertEqual(metadata.limit_source, "key")
        self.assertEqual(metadata.response_cache, "hit")
        self.assertEqual(metadata.response_cache_age, 3)
        self.assertEqual(metadata.budget_warning, "org soft_budget 80.00/100.00")
        self.assertEqual(metadata.guardrails, "pass")

    def test_unpriced_response_omits_amount_without_claiming_zero(self) -> None:
        metadata = nRouterResponseMeta.from_headers(
            {"x-nr-request-id": "req_unpriced", "x-nr-cost-status": "unpriced"}
        )
        self.assertIsNone(metadata.cost)
        self.assertEqual(metadata.cost_status, "unpriced")

    def test_anthropic_messages_is_a_real_buffered_sdk_call(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["authorization"] = request.headers.get("authorization")
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                headers={
                    "content-type": "application/json",
                    "x-nr-request-id": "req_messages",
                    "x-nr-request-cost": "0.00042",
                    "x-nr-cost-status": "exact",
                    "x-nr-model": "claude-sonnet-4-5",
                },
                json={
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Hello"}],
                    "usage": {"input_tokens": 2, "output_tokens": 1},
                },
            )

        transport = httpx.MockTransport(handler)
        http_client = httpx.Client(transport=transport)
        client = nRouter(
            api_key="sk-nrouter-contract-test",
            base_url="https://gateway.example/v1",
            http_client=http_client,
        )
        self.addCleanup(client.close)

        response = client.messages.create(
            model="claude-sonnet-4-5",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=16,
        )

        self.assertEqual(seen["url"], "https://gateway.example/v1/messages")
        self.assertEqual(seen["authorization"], "Bearer sk-nrouter-contract-test")
        self.assertEqual(
            seen["body"],
            {
                "model": "claude-sonnet-4-5",
                "messages": [{"role": "user", "content": "Hello"}],
                "max_tokens": 16,
                "stream": False,
            },
        )
        self.assertEqual(response["id"], "msg_1")
        self.assertEqual(client.last_response.request_id, "req_messages")
        self.assertEqual(client.last_response.cost, 0.00042)

    def test_messages_streaming_refuses_until_an_sse_contract_is_tested(self) -> None:
        client = nRouter(api_key="sk-nrouter-contract-test")
        self.addCleanup(client.close)
        with self.assertRaisesRegex(NotImplementedError, "stream"):
            client.messages.create(
                model="claude-sonnet-4-5",
                messages=[{"role": "user", "content": "Hello"}],
                max_tokens=16,
                stream=True,
            )

    def test_messages_count_tokens_is_a_real_sdk_call(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json={"input_tokens": 123})

        client = nRouter(
            api_key="sk-nrouter-contract-test",
            base_url="https://gateway.example/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        self.addCleanup(client.close)
        result = client.messages.count_tokens(
            model="claude-sonnet-4-5",
            messages=[{"role": "user", "content": "Hello"}],
        )
        self.assertEqual(
            seen["url"], "https://gateway.example/v1/messages/count_tokens"
        )
        self.assertEqual(seen["body"]["model"], "claude-sonnet-4-5")
        self.assertEqual(result, {"input_tokens": 123})

    def test_large_message_payload_is_not_truncated_by_the_sdk(self) -> None:
        marker = "large-context-marker-"
        content = marker + ("x" * (1024 * 1024))
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["content"] = json.loads(request.content)["messages"][0]["content"]
            return httpx.Response(200, json={"id": "msg_large", "content": []})

        client = nRouter(
            api_key="sk-nrouter-contract-test",
            base_url="https://gateway.example/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        self.addCleanup(client.close)
        client.messages.create(
            model="claude-sonnet-4-5",
            messages=[{"role": "user", "content": content}],
            max_tokens=16,
        )
        self.assertEqual(seen["content"], content)

    def test_responses_uses_the_inherited_openai_transport(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "id": "resp_1",
                    "object": "response",
                    "created_at": 1,
                    "status": "completed",
                    "model": "gpt-4o-mini",
                    "output": [],
                },
            )

        client = nRouter(
            api_key="sk-nrouter-contract-test",
            base_url="https://gateway.example/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        self.addCleanup(client.close)
        response = client.responses.create(model="gpt-4o-mini", input="Hello")
        self.assertEqual(seen["url"], "https://gateway.example/v1/responses")
        self.assertEqual(seen["body"]["input"], "Hello")
        self.assertEqual(response.id, "resp_1")

    def test_video_collection_has_real_create_retrieve_and_binary_download_methods(
        self,
    ) -> None:
        seen = []
        video_bytes = b"\x00\x00\x00\x18ftypmp42\xff\x00"

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.method, str(request.url)))
            if request.url.path.endswith("/content"):
                return httpx.Response(
                    200, content=video_bytes, headers={"content-type": "video/mp4"}
                )
            return httpx.Response(200, json={"id": "video_1", "status": "queued"})

        client = nRouter(
            api_key="sk-nrouter-contract-test",
            base_url="https://gateway.example/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        self.addCleanup(client.close)
        self.assertEqual(
            client.videos.create(model="sora", prompt="ocean")["id"], "video_1"
        )
        self.assertEqual(client.videos.retrieve("video_1")["status"], "queued")
        self.assertEqual(client.videos.download_content("video_1"), video_bytes)
        self.assertEqual(
            seen,
            [
                ("POST", "https://gateway.example/v1/videos"),
                ("GET", "https://gateway.example/v1/videos/video_1"),
                ("GET", "https://gateway.example/v1/videos/video_1/content"),
            ],
        )

    def test_video_id_is_url_encoded_instead_of_becoming_a_path(self) -> None:
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, json={"id": "safe"})

        client = nRouter(
            api_key="sk-nrouter-contract-test",
            base_url="https://gateway.example/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        self.addCleanup(client.close)
        client.videos.retrieve("../../api/providers")
        self.assertEqual(
            seen["url"],
            "https://gateway.example/v1/videos/..%2F..%2Fapi%2Fproviders",
        )

    def test_openai_compatible_embedding_image_and_audio_namespaces_reach_the_gateway(
        self,
    ) -> None:
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(
                (
                    request.method,
                    request.url.path,
                    request.headers.get("content-type", ""),
                )
            )
            if request.url.path.endswith("/embeddings"):
                return httpx.Response(
                    200,
                    json={
                        "object": "list",
                        "model": "text-embedding-3-small",
                        "data": [
                            {"object": "embedding", "index": 0, "embedding": [0.1]}
                        ],
                        "usage": {"prompt_tokens": 1, "total_tokens": 1},
                    },
                )
            if request.url.path.endswith("/images/generations"):
                return httpx.Response(
                    200, json={"created": 1, "data": [{"b64_json": "aGVsbG8="}]}
                )
            if request.url.path.endswith("/audio/speech"):
                return httpx.Response(
                    200, content=b"audio", headers={"content-type": "audio/mpeg"}
                )
            return httpx.Response(200, json={"text": "transcript"})

        client = nRouter(
            api_key="sk-nrouter-contract-test",
            base_url="https://gateway.example/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        self.addCleanup(client.close)
        embedding = client.embeddings.create(
            model="text-embedding-3-small", input="hello"
        )
        image = client.images.generate(model="gpt-image-1", prompt="ocean")
        speech = client.audio.speech.create(
            model="gpt-4o-mini-tts", voice="alloy", input="hello"
        )
        transcription = client.audio.transcriptions.create(
            model="whisper-1", file=("audio.wav", b"RIFFdata", "audio/wav")
        )
        translation = client.audio.translations.create(
            model="whisper-1", file=("audio.wav", b"RIFFdata", "audio/wav")
        )
        self.assertEqual(embedding.data[0].embedding, [0.1])
        self.assertEqual(image.data[0].b64_json, "aGVsbG8=")
        self.assertEqual(speech.content, b"audio")
        self.assertEqual(transcription.text, "transcript")
        self.assertEqual(translation.text, "transcript")
        self.assertEqual(
            [path for _, path, _ in seen],
            [
                "/v1/embeddings",
                "/v1/images/generations",
                "/v1/audio/speech",
                "/v1/audio/transcriptions",
                "/v1/audio/translations",
            ],
        )
        self.assertTrue(seen[3][2].startswith("multipart/form-data; boundary="))
        self.assertTrue(seen[4][2].startswith("multipart/form-data; boundary="))


class AsyncClientContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_anthropic_messages_uses_the_async_transport(self) -> None:
        seen = {}

        async def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                headers={"x-nr-request-id": "req_async_messages"},
                json={"id": "msg_async", "type": "message", "content": []},
            )

        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client = AsyncnRouter(
            api_key="sk-nrouter-contract-test",
            base_url="https://gateway.example/v1",
            http_client=http_client,
        )
        self.addAsyncCleanup(client.close)

        response = await client.messages.create(
            model="claude-sonnet-4-5",
            messages=[{"role": "user", "content": "Hello"}],
            max_tokens=16,
        )

        self.assertEqual(seen["url"], "https://gateway.example/v1/messages")
        self.assertEqual(seen["body"]["stream"], False)
        self.assertEqual(response["id"], "msg_async")
        self.assertEqual(client.last_response.request_id, "req_async_messages")

    async def test_async_count_tokens_responses_and_video_collection_use_async_transport(
        self,
    ) -> None:
        seen = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.method, request.url.path))
            if request.url.path.endswith("/count_tokens"):
                return httpx.Response(200, json={"input_tokens": 7})
            if request.url.path.endswith("/content"):
                return httpx.Response(
                    200, content=b"video", headers={"content-type": "video/mp4"}
                )
            if request.url.path.endswith("/responses"):
                return httpx.Response(
                    200,
                    json={
                        "id": "resp_async",
                        "object": "response",
                        "created_at": 1,
                        "status": "completed",
                        "model": "gpt-4o-mini",
                        "output": [],
                    },
                )
            return httpx.Response(200, json={"id": "video_async", "status": "queued"})

        client = AsyncnRouter(
            api_key="sk-nrouter-contract-test",
            base_url="https://gateway.example/v1",
            http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        )
        self.addAsyncCleanup(client.close)
        count = await client.messages.count_tokens(model="claude", messages=[])
        response = await client.responses.create(model="gpt-4o-mini", input="Hello")
        created = await client.videos.create(model="sora", prompt="ocean")
        retrieved = await client.videos.retrieve("video_async")
        content = await client.videos.download_content("video_async")
        self.assertEqual(count["input_tokens"], 7)
        self.assertEqual(response.id, "resp_async")
        self.assertEqual(created["id"], "video_async")
        self.assertEqual(retrieved["status"], "queued")
        self.assertEqual(content, b"video")
        self.assertEqual(len(seen), 5)


class PackagingContractTests(unittest.TestCase):
    """pyproject.toml is not parsed by any other test, so a syntax error in it
    ships silently — it did, in d4222486, and reached PyPI's public repo before
    a build caught it. These assertions are the parse."""

    def _pyproject(self) -> dict:
        # `tomllib` is 3.11+, and pyproject declares a 3.10 floor that CI pins
        # — so a bare `import tomllib` makes this whole file raise
        # ModuleNotFoundError on the interpreter the project claims to support,
        # before a single assertion runs. `tomli` is the same parser under its
        # old name; publish-pypi.yml already installs it for the same reason in
        # its version check.
        try:
            import tomllib  # type: ignore[import-not-found]
        except ModuleNotFoundError:  # Python 3.10
            import tomli as tomllib  # type: ignore[no-redef]

        path = SDK_ROOT / "sdks" / "python" / "pyproject.toml"
        with path.open("rb") as fh:
            return tomllib.load(fh)

    def test_pyproject_parses_and_declares_the_published_name(self) -> None:
        project = self._pyproject()["project"]
        self.assertEqual(project["name"], "nrouter-sdk")

    def test_version_agrees_across_every_coupled_site(self) -> None:
        """Version lives in four places. Any one drifting is a broken release."""
        project = self._pyproject()["project"]
        spec = json.loads((SDK_ROOT / "spec" / "nrouter-sdk-spec.json").read_text())
        self.assertEqual(project["version"], __import__("nroutersdk").__version__)
        self.assertEqual(project["version"], spec["version"])

    def test_openai_floor_supplies_the_responses_namespace(self) -> None:
        """The client exposes inherited `responses`; it landed in openai 1.66.0
        (ABSENT in 1.65.5, measured). A lower floor resolves to a client without it."""
        deps = self._pyproject()["project"]["dependencies"]
        openai_req = next(d for d in deps if d.startswith("openai"))
        # PEP 508: a requirement carries MANY specifiers. `openai>=3.3.1,<4` is
        # valid and correct — the upper bound is deliberate, because this client
        # reaches into OpenAI-SDK internals. Splitting the raw string on "."
        # parsed "1,<4" as a version part and raised ValueError, so adding a
        # bound broke the verifier rather than the contract.
        floor = next(
            spec.split(">=")[1].strip()
            for spec in openai_req.split(",")
            if ">=" in spec
        )
        self.assertGreaterEqual(
            tuple(int(part) for part in floor.split(".")), (1, 66, 0), openai_req
        )


class ShellExampleContractTests(unittest.TestCase):
    """A comment inside a line continuation is VALID shell that runs the wrong
    thing, so `bash -n` passes and the example is still broken.

    Measured 2026-08-25: a note inserted between `-H ... \\` and its `-d`
    payload terminated the curl invocation, leaving the payload line to execute
    as a standalone command. `bash -n` returned 0 on it. Caught by review, not
    by a linter — hence this assertion.
    """

    def test_no_comment_interrupts_a_line_continuation(self) -> None:
        scripts = sorted((SDK_ROOT / "sdks").glob("*/demo/**/*.sh"))
        for script in scripts:
            lines = script.read_text().split("\n")
            for index, line in enumerate(lines[:-1]):
                if not line.rstrip().endswith("\\"):
                    continue
                following = lines[index + 1].lstrip()
                self.assertFalse(
                    following.startswith("#"),
                    f"{script.name}:{index + 2} a comment follows a line "
                    f"continuation, which silently ends the command above it",
                )


class ExampleBodyFieldContractTests(unittest.TestCase):
    """`sdks/*/demo/` is the Rule #14 canonical copy-paste starter for every
    language, and it is world-readable — so an `nrouter_*` field that no
    gateway reads is not a doc typo, it is a starter that guarantees a failed
    request in twelve languages at once.

    This is the test that would have caught the real one. Measured 2026-08-28:
    every example shipped `nrouter_guardrail_ids`, which appeared NOWHERE in
    the gateway (0 hits against 608 `guardrail` references) and in none of the
    three `extra_body_fields` the gateway's own OpenAPI advertises. No provider
    transformation strips it either — they each remove only the fields the
    gateway owns — so it reached the provider verbatim and came back as an
    opaque upstream rejection. Guardrails are real, but they are ASSIGNED per
    key/team/org in the dashboard and resolved by specificity; there is no
    per-request override to send.

    The pin has to run over EVERY example, not just the ones a language test
    happens to parse: the field bypassed the JS SDK entirely (raw extra body →
    gateway → provider), so no SDK-level assertion could see it.
    """

    # A body field always appears quoted or as a bare key introducing a value
    # (`x:` in JS/Python/Ruby, `x =>` in PHP). Anchoring on that keeps local
    # identifiers that merely start with `nrouter_` — `nrouter_get(path)` in
    # ruby.rb, `nrouter_key <- ...` in hello-world/r.R — out of the result,
    # without an allowlist that would rot.
    FIELD_IN_VALUE_POSITION = re.compile(
        r"""["']?(nrouter_[a-z0-9_]+)["']?\s*(?::|=>)"""
    )

    # The spend-row envelope the dashboard returns:
    # GET /api/nrouter-proxy/spend/by-key -> {"log": {... "metadata": {...}}, "total": n}
    # Both openers are anchored on a key introducing an object so that
    # `console.log(`, `logPath:` and `metadata_keys` cannot open a span.
    SPEND_ROW_ENVELOPE_OPENS = re.compile(
        r"""(?<![A-Za-z0-9_])["']?log["']?\s*(?::|=>)\s*\{"""
    )
    METADATA_OBJECT_OPENS = re.compile(
        r"""(?<![A-Za-z0-9_])["']?metadata["']?\s*(?::|=>)\s*\{"""
    )

    @staticmethod
    def _mask_braces_in_literals(text: str) -> str:
        """Return `text` with every `{`/`}` that sits inside a string literal or
        a comment replaced by a space, CHARACTER FOR CHARACTER so that every
        offset still lines up with the original.

        Without this the brace walker below counts a brace in `"use { and }"` or
        in a `${...}` template placeholder, which silently collapses or extends
        an object span and misclassifies the fields in it. Only braces are
        masked, never the quotes or the key names, so a quoted key such as
        `"nrouter_units":` is still matched exactly where it really is.
        """
        out = list(text)
        index, length = 0, len(text)
        quote = None  # the delimiter we are inside, or None
        comment = None  # "line" or "block", or None
        while index < length:
            char = text[index]
            if comment == "line":
                if char == "\n":
                    comment = None
                elif char in "{}":
                    out[index] = " "
            elif comment == "block":
                if char == "*" and text[index + 1 : index + 2] == "/":
                    comment = None
                    index += 1
                elif char in "{}":
                    out[index] = " "
            elif quote is not None:
                if char == "\\":
                    index += 2
                    continue
                if char == quote:
                    quote = None
                elif char in "{}":
                    out[index] = " "
            elif char in "\"'`":
                quote = char
            elif char == "/" and text[index + 1 : index + 2] == "/":
                comment = "line"
                index += 1
            elif char == "/" and text[index + 1 : index + 2] == "*":
                comment = "block"
                index += 1
            index += 1
        return "".join(out)

    @classmethod
    def _object_spans(cls, text: str, opener: "re.Pattern") -> list:
        """Half-open (start, end) offsets of every brace-balanced object literal
        introduced by `opener`. Nesting is walked, so an inner `metadata` object
        keeps the outer `log` span around it. Braces inside string literals and
        comments are masked first, so they cannot skew the depth."""
        spans = []
        masked = cls._mask_braces_in_literals(text)
        for match in opener.finditer(text):
            depth = 0
            index = match.end() - 1  # the `{` itself
            while index < len(masked):
                char = masked[index]
                if char == "{":
                    depth += 1
                elif char == "}":
                    depth -= 1
                    if depth == 0:
                        spans.append((match.end(), index))
                        break
                index += 1
        return spans

    @classmethod
    def _classify(cls, text: str) -> dict:
        """field -> position, for every nRouter field in a value position.

        A field is in `spend-row-metadata` position only when it sits inside a
        `metadata` object that is itself inside a spend-row `log` envelope.
        Everything else — including a bare request-level `metadata` object,
        which the OpenAI-compatible request bodies really do accept — is a
        `request-body` position and stays bound to `extra_body_fields`.
        """
        envelopes = cls._object_spans(text, cls.SPEND_ROW_ENVELOPE_OPENS)
        spend_row_metadata = [
            (lo, hi)
            for lo, hi in cls._object_spans(text, cls.METADATA_OBJECT_OPENS)
            if any(elo <= lo and hi <= ehi for elo, ehi in envelopes)
        ]
        positions = {}
        for match in cls.FIELD_IN_VALUE_POSITION.finditer(text):
            at = match.start(1)
            inside = any(lo <= at < hi for lo, hi in spend_row_metadata)
            # EVERY occurrence is recorded, never just the last one: the same
            # field can legitimately appear as a response key and illegitimately
            # as a request field in one file, and collapsing the two hides the
            # second behind the first.
            positions.setdefault(match.group(1), set()).add(
                "spend-row-metadata" if inside else "request-body"
            )
        return positions

    @classmethod
    def _offenders(cls, text: str, request_allowed: set, metadata_allowed: set) -> dict:
        """field -> sorted positions that refused it. An allowlist per position,
        so a spend-row key is NOT a licence to send that key in a request body,
        and the `metadata` context is NOT an escape hatch for an unlisted key."""
        offenders = {}
        for field, found in cls._classify(text).items():
            refused = sorted(
                position
                for position in found
                if field
                not in (
                    metadata_allowed
                    if position == "spend-row-metadata"
                    else request_allowed
                )
            )
            if refused:
                offenders[field] = refused
        return offenders

    @staticmethod
    def _spec() -> dict:
        return json.loads((SDK_ROOT / "spec" / "nrouter-sdk-spec.json").read_text())

    def _spec_fields(self) -> set:
        fields = set(self._spec()["extra_body_fields"])
        self.assertTrue(fields, "the spec declares no extra_body_fields")
        return fields

    def _spec_metadata_fields(self) -> set:
        """The customer-visible spend-row `metadata` keys, derived in
        nrouter-app's `src/lib/logs/sanitize-log-metadata.ts` allowlist and
        published in the spec. `$`-prefixed entries are annotations.

        The section documents the whole surface; this scanner only ENFORCES the
        `nrouter_` namespace, because `FIELD_IN_VALUE_POSITION` is anchored on
        that prefix. `tags` is therefore published and unenforced — it is the
        caller's own key, so there is nothing to refuse.
        """
        section = self._spec()["spend_row_metadata_fields"]
        fields = {key for key in section if not key.startswith("$")}
        self.assertTrue(fields, "the spec declares no spend_row_metadata_fields")
        return fields

    def test_no_example_sends_a_field_the_gateway_does_not_read(self) -> None:
        request_allowed = self._spec_fields()
        metadata_allowed = self._spec_metadata_fields()
        offenders = {}
        paths = sorted((SDK_ROOT / "sdks").glob("*/demo/**/*"))
        for path in paths:
            if not path.is_file():
                continue
            found = self._offenders(
                path.read_text(encoding="utf-8", errors="ignore"),
                request_allowed,
                metadata_allowed,
            )
            for field, positions in sorted(found.items()):
                offenders.setdefault(
                    f"{field} ({', '.join(positions)})", []
                ).append(str(path.relative_to(SDK_ROOT)))
        self.assertEqual(
            offenders,
            {},
            "examples carry nRouter fields absent from the spec allowlist for "
            "the position they appear in: a request-body field must be in "
            "extra_body_fields (the gateway does not read anything else and "
            "forwards it to the provider verbatim), and a spend-row "
            "`log.metadata` key must be in spend_row_metadata_fields",
        )

    def test_the_chat_agent_spend_row_mock_is_accepted(self) -> None:
        """Positive control. The suite mocks the dashboard's own response —
        `{"log": {..., "metadata": {"nrouter_units": ..., "nrouter_cost": ...}}}`
        — which is a RESPONSE surface, not a request body, and must not be read
        as an example teaching customers to send those fields."""
        suite = SDK_ROOT / "sdks" / "js" / "demo" / "chat_agent_suite.js"
        self.assertTrue(suite.is_file(), f"{suite} is missing")
        body = suite.read_text(encoding="utf-8")

        # Assert the ACCEPT PATH was actually exercised before asserting the
        # absence of offenders. Without this the test is green either because
        # the mock is correctly classified, or because the mock no longer has a
        # `log.metadata` shape at all — and only the first is what it claims.
        classified = self._classify(body)
        for field in ("nrouter_units", "nrouter_cost"):
            self.assertIn(
                "spend-row-metadata",
                classified.get(field, set()),
                f"{field} is no longer recognised inside the suite's spend-row "
                f"`log.metadata` envelope, so this positive control proves "
                f"nothing",
            )
        self.assertEqual(
            self._offenders(
                body, self._spec_fields(), self._spec_metadata_fields()
            ),
            {},
        )

    def test_a_brace_in_a_string_or_comment_cannot_skew_a_span(self) -> None:
        """A `{` inside a JS string, a template placeholder or a comment is not
        structure. Counting it splits or extends an object span, which silently
        moves fields between the two allowlists — so the masking is pinned here
        rather than left to the file walk to notice years later."""
        # The stray braces sit INSIDE the `log` envelope and are unbalanced, so
        # an unmasked walker closes that span early, the `metadata` object falls
        # outside it, and the key is misread as a request field.
        fixture = """
        const payload = {
          log: {
            note: 'an unbalanced } brace inside a string',
            // and a lone } inside a comment
            metadata: { nrouter_secret_thing: 1 },
          },
          total: 1,
        };
        """
        self.assertEqual(
            self._offenders(
                fixture, self._spec_fields(), self._spec_metadata_fields()
            ),
            {"nrouter_secret_thing": ["spend-row-metadata"]},
        )

    def test_metadata_context_is_an_allowlist_not_an_escape_hatch(self) -> None:
        """Negative control. `metadata` is a POSITION, not a pass — an unlisted
        nRouter key inside a real spend-row envelope is still refused, so a
        future gateway-internal key cannot be taught to customers by wrapping it
        in the shape this test learned to accept."""
        fixture = """
        res.end(JSON.stringify({
          log: {
            request_id: 'req_1',
            metadata: { nrouter_cost: 0.01, nrouter_secret_thing: 'internal' },
          },
          total: 1,
        }));
        """
        self.assertEqual(
            self._offenders(
                fixture, self._spec_fields(), self._spec_metadata_fields()
            ),
            {"nrouter_secret_thing": ["spend-row-metadata"]},
        )

    def test_a_spend_row_key_is_still_refused_as_a_request_field(self) -> None:
        """The two allowlists do not leak into each other. `nrouter_units` is a
        real RESPONSE key, and sending it is still the exact defect this class
        exists to prevent. `nrouter_cache` beside it is the positive control."""
        fixture = """
        const body = { model: 'gpt-4o-mini', nrouter_cache: true, nrouter_units: 'tokens' };
        """
        self.assertEqual(
            self._offenders(
                fixture, self._spec_fields(), self._spec_metadata_fields()
            ),
            {"nrouter_units": ["request-body"]},
        )

    def test_a_request_level_metadata_object_is_not_a_spend_row(self) -> None:
        """The OpenAI-compatible request bodies really do accept a `metadata`
        object, so `metadata` ALONE cannot mean "response". Only a `metadata`
        nested in the dashboard's `log` envelope is a spend row; without it the
        field is a request field and stays bound to `extra_body_fields`."""
        fixture = """
        const body = { model: 'gpt-4o-mini', metadata: { nrouter_units: 'tokens' } };
        """
        self.assertEqual(
            self._offenders(
                fixture, self._spec_fields(), self._spec_metadata_fields()
            ),
            {"nrouter_units": ["request-body"]},
        )

    def test_the_guardrail_override_is_refused_in_every_position(self) -> None:
        """The field that motivated this class is on NEITHER allowlist, so the
        new response-metadata position must not have quietly readmitted it."""
        fixture = """
        const body = { nrouter_guardrail_ids: ['a'] };
        const row = { log: { metadata: { nrouter_guardrail_ids: ['a'] } } };
        """
        self.assertEqual(
            self._offenders(
                fixture, self._spec_fields(), self._spec_metadata_fields()
            ),
            {"nrouter_guardrail_ids": ["request-body", "spend-row-metadata"]},
        )

    def test_the_retired_guardrail_override_is_gone_everywhere(self) -> None:
        """Named explicitly, because a regex pin can be loosened by accident
        and this particular field was shipped publicly in twelve languages."""
        paths = sorted((SDK_ROOT / "sdks").glob("*/demo/**/*"))
        for path in paths:
            if not path.is_file():
                continue
            self.assertNotIn(
                "nrouter_guardrail_ids",
                path.read_text(encoding="utf-8", errors="ignore"),
                f"{path.relative_to(SDK_ROOT)} still teaches a field the "
                f"gateway does not read",
            )

    def test_base_url_env_resolution(self) -> None:
        """NROUTER_BASE_URL environment variable is respected when base_url is omitted."""
        custom_base = "https://api-stage.nrouter.ai/v1"
        try:
            os.environ["NROUTER_BASE_URL"] = custom_base
            client = nRouter(api_key="sk-nrouter-test-key")
            self.assertEqual(str(client.base_url).rstrip("/"), custom_base)
            self.assertEqual(client._nrouter_base, "https://api-stage.nrouter.ai")

            # Explicit base_url overrides environment variable
            override_base = "https://custom.nrouter.ai/v1"
            client_override = nRouter(
                api_key="sk-nrouter-test-key", base_url=override_base
            )
            self.assertEqual(str(client_override.base_url).rstrip("/"), override_base)
            self.assertEqual(client_override._nrouter_base, "https://custom.nrouter.ai")
        finally:
            os.environ.pop("NROUTER_BASE_URL", None)

    def test_context_manager_lifecycle(self) -> None:
        """Client implements context manager protocol cleanly."""
        with nRouter(api_key="sk-nrouter-test-key") as client:
            self.assertIsNotNone(client)
            self.assertFalse(client.is_closed())
        self.assertTrue(client.is_closed())


# AT THE BOTTOM, and that is the whole point. This block used to sit at line
# 492 with THREE test classes defined after it, so `unittest.main()` ran
# before they existed: `python3 tests/test_sdk_contract.py` printed "OK" with
# no "Ran N tests" line and executed none of them. CI uses `-m unittest`,
# which imports the module first and does collect them, so the gate was live
# in CI and silently empty for anyone verifying the obvious way.
if __name__ == "__main__":
    unittest.main()
