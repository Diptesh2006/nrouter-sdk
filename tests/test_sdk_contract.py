import json
import os
import re
import sys
import unittest
from pathlib import Path

import httpx


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

        gateway_contract = ROOT.parent / "nrouter-rust-gateway" / "src" / "http" / "nr_headers.rs"
        if gateway_contract.exists():
            emitted_headers = set(
                re.findall(
                    r'^pub const [A-Z_]+: &str = "(x-nr-[^"]+)";',
                    gateway_contract.read_text(),
                    flags=re.MULTILINE,
                )
            )
            cache_contract = gateway_contract.parents[1] / "proxy" / "cache.rs"
            if cache_contract.exists():
                emitted_headers.update(
                    re.findall(
                        r'^pub const [A-Z_]+: &str = "(x-nr-[^"]+)";',
                        cache_contract.read_text(),
                        flags=re.MULTILINE,
                    )
                )
            self.assertEqual(response_headers, emitted_headers)

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

    def test_spec_advertises_cache_only_on_executable_buffered_text_routes(self) -> None:
        spec = json.loads((SDK_ROOT / "spec" / "nrouter-sdk-spec.json").read_text())
        cached = {
            "/v1/chat/completions",
            "/v1/completions",
            "/v1/messages",
            "/v1/responses",
        }
        for endpoint in spec["supported_endpoints"]:
            self.assertEqual("cache" in endpoint["features"], endpoint["path"] in cached)
        self.assertIn(
            "nrouter_cache",
            spec["extra_body_fields"],
        )
        self.assertEqual(
            set(spec["response_headers"]["x-nr-response-cache"]["values"]),
            {"hit", "miss"},
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
        self.assertEqual(seen["url"], "https://gateway.example/v1/messages/count_tokens")
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

    def test_video_collection_has_real_create_retrieve_and_binary_download_methods(self) -> None:
        seen = []
        video_bytes = b"\x00\x00\x00\x18ftypmp42\xff\x00"

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.method, str(request.url)))
            if request.url.path.endswith("/content"):
                return httpx.Response(200, content=video_bytes, headers={"content-type": "video/mp4"})
            return httpx.Response(200, json={"id": "video_1", "status": "queued"})

        client = nRouter(
            api_key="sk-nrouter-contract-test",
            base_url="https://gateway.example/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        self.addCleanup(client.close)
        self.assertEqual(client.videos.create(model="sora", prompt="ocean")["id"], "video_1")
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

    def test_openai_compatible_embedding_image_and_audio_namespaces_reach_the_gateway(self) -> None:
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.method, request.url.path, request.headers.get("content-type", "")))
            if request.url.path.endswith("/embeddings"):
                return httpx.Response(
                    200,
                    json={
                        "object": "list",
                        "model": "text-embedding-3-small",
                        "data": [{"object": "embedding", "index": 0, "embedding": [0.1]}],
                        "usage": {"prompt_tokens": 1, "total_tokens": 1},
                    },
                )
            if request.url.path.endswith("/images/generations"):
                return httpx.Response(200, json={"created": 1, "data": [{"b64_json": "aGVsbG8="}]})
            if request.url.path.endswith("/audio/speech"):
                return httpx.Response(200, content=b"audio", headers={"content-type": "audio/mpeg"})
            return httpx.Response(200, json={"text": "transcript"})

        client = nRouter(
            api_key="sk-nrouter-contract-test",
            base_url="https://gateway.example/v1",
            http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        )
        self.addCleanup(client.close)
        embedding = client.embeddings.create(model="text-embedding-3-small", input="hello")
        image = client.images.generate(model="gpt-image-1", prompt="ocean")
        speech = client.audio.speech.create(model="gpt-4o-mini-tts", voice="alloy", input="hello")
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

    async def test_async_count_tokens_responses_and_video_collection_use_async_transport(self) -> None:
        seen = []

        async def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.method, request.url.path))
            if request.url.path.endswith("/count_tokens"):
                return httpx.Response(200, json={"input_tokens": 7})
            if request.url.path.endswith("/content"):
                return httpx.Response(200, content=b"video", headers={"content-type": "video/mp4"})
            if request.url.path.endswith("/responses"):
                return httpx.Response(
                    200,
                    json={"id": "resp_async", "object": "response", "created_at": 1, "status": "completed", "model": "gpt-4o-mini", "output": []},
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


if __name__ == "__main__":
    unittest.main()


class PackagingContractTests(unittest.TestCase):
    """pyproject.toml is not parsed by any other test, so a syntax error in it
    ships silently — it did, in d4222486, and reached PyPI's public repo before
    a build caught it. These assertions are the parse."""

    def _pyproject(self) -> dict:
        import tomllib

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
        for script in sorted((SDK_ROOT / "examples").rglob("*.sh")):
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

