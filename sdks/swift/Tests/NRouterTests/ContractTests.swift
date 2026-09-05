import XCTest
@testable import NRouter

/// The gateway contract this SDK must keep, asserted against the values in
/// `spec/nrouter-sdk-spec.json`.
final class ContractTests: XCTestCase {

    func testConstantsMatchTheSpec() {
        XCTAssertEqual(NRouter.defaultBaseURL, "https://api.nrouter.ai/v1")
        XCTAssertEqual(NRouter.envKey, "NROUTER_API_KEY")
        XCTAssertEqual(NRouter.keyPrefix, "sk-nrouter-")
    }

    func testUsesMessagesWire() {
        XCTAssertTrue(NRouter.usesMessagesWire("claude-3-5-sonnet-20241022"))
        XCTAssertTrue(NRouter.usesMessagesWire("anthropic/claude-3-haiku"))
        XCTAssertTrue(NRouter.usesMessagesWire("my-model", provider: "anthropic"))
        XCTAssertFalse(NRouter.usesMessagesWire("gpt-4o"))
        XCTAssertFalse(NRouter.usesMessagesWire("meta-llama/llama-3"))
    }

    func testEverySpecHeaderIsRead() {
        let expected = [
            "x-nr-request-id", "x-nr-request-cost", "x-nr-cost-status", "x-nr-model",
            "x-nr-input-tokens", "x-nr-output-tokens", "x-nr-total-tokens",
            "x-nr-cache-read-tokens", "x-nr-cache-write-tokens", "x-nr-limit-source",
            "x-nr-auth-reason", "x-nr-response-cache", "x-nr-response-cache-age",
            "x-nr-budget-warning", "x-nr-guardrails",
        ]
        XCTAssertEqual(NRouterResponseMeta.headerNames.count, 15)
        for name in expected {
            XCTAssertTrue(
                NRouterResponseMeta.headerNames.contains(name),
                "\(name) is not read by this SDK"
            )
        }
    }

    private func caseName(_ error: NRouterError) -> String {
        switch error {
        case .request: return "request"
        case .guardrailBlocked: return "guardrailBlocked"
        case .authentication: return "authentication"
        case .credit: return "credit"
        case .budgetExceeded: return "budgetExceeded"
        case .notFound: return "notFound"
        case .rateLimit: return "rateLimit"
        case .service: return "service"
        case .other: return "other"
        case .transport: return "transport"
        case .configuration: return "configuration"
        }
    }

    func testEachGatewayCodeMapsToItsCase() {
        let expected: [(String, String)] = [
            ("invalid_request", "request"),
            ("guardrail_blocked", "guardrailBlocked"),
            ("invalid_api_key", "authentication"),
            ("insufficient_credits", "credit"),
            ("model_not_found", "notFound"),
            ("rate_limit_exceeded", "rateLimit"),
            ("tpm_limit_exceeded", "rateLimit"),
            ("credit_check_failed", "service"),
            ("service_unavailable", "service"),
        ]
        for (code, want) in expected {
            let error = NRouterError.fromCode(NRouterErrorBody(message: "boom", code: code))
            XCTAssertEqual(caseName(error), want, "code \(code) mapped wrong")
        }
    }

    func testACodelessFourZeroTwoSeparatesBudgetFromShortfall() {
        // Two of the three 402s are budget ceilings, whose fix is the OPPOSITE
        // of a shortfall's.
        let budget = NRouterError.fromCode(
            NRouterErrorBody(message: "budget exceeded: spend 5.00", status: 402)
        )
        XCTAssertEqual(caseName(budget), "budgetExceeded")

        let shortfall = NRouterError.fromCode(
            NRouterErrorBody(message: "insufficient credits: 0.01 available", status: 402)
        )
        XCTAssertEqual(caseName(shortfall), "credit")
    }

    func testACodelessFourZeroFourIsOnlyModelNotFoundWhenItNamesAModel() {
        let model = NRouterError.fromCode(
            NRouterErrorBody(message: "model 'x' not found", status: 404)
        )
        XCTAssertEqual(caseName(model), "notFound")

        // A missing video job or MCP server is also a 404.
        let other = NRouterError.fromCode(
            NRouterErrorBody(message: "unknown video job", status: 404)
        )
        XCTAssertEqual(caseName(other), "other")
    }

    func testAnUnknownCodeIsNeverReclassified() {
        let error = NRouterError.fromCode(
            NRouterErrorBody(message: "boom", code: "some_future_code")
        )
        XCTAssertEqual(caseName(error), "other")
    }

    func testOnlyTransientFailuresAreRetryable() {
        for code in ["rate_limit_exceeded", "service_unavailable", "credit_check_failed"] {
            XCTAssertTrue(
                NRouterError.fromCode(NRouterErrorBody(message: "x", code: code)).isRetryable,
                "\(code) should be retryable"
            )
        }
        for code in [
            "invalid_request", "guardrail_blocked", "invalid_api_key",
            "insufficient_credits", "model_not_found",
        ] {
            XCTAssertFalse(
                NRouterError.fromCode(NRouterErrorBody(message: "x", code: code)).isRetryable,
                "\(code) must not be advertised as retryable"
            )
        }
        XCTAssertTrue(NRouterError.transport("dns").isRetryable)
        // A local configuration failure is PERMANENT. Marking it retryable
        // makes a caller's retry loop spin forever without ever sending.
        XCTAssertFalse(NRouterError.configuration("no key").isRetryable)
    }

    func testAnUnpricedResponseReportsNoCostRatherThanZero() {
        let meta = NRouterResponseMeta { name in
            switch name {
            case "x-nr-cost-status": return "unpriced"
            case "x-nr-request-id": return "req_1"
            default: return nil
            }
        }
        XCTAssertNil(meta.cost, "unpriced must not become a number")
        XCTAssertFalse(meta.isPriced)
        XCTAssertEqual(meta.requestID, "req_1")
    }

    func testAPricedResponseParsesItsNumbers() {
        let meta = NRouterResponseMeta { name in
            switch name {
            case "x-nr-request-cost": return "0.00042"
            case "x-nr-cost-status": return "exact"
            case "x-nr-input-tokens": return "11"
            case "x-nr-output-tokens": return "22"
            case "x-nr-response-cache": return "hit"
            case "x-nr-response-cache-age": return "7"
            default: return nil
            }
        }
        XCTAssertEqual(meta.cost, 0.00042)
        XCTAssertTrue(meta.isPriced)
        XCTAssertEqual(meta.inputTokens, 11)
        XCTAssertEqual(meta.outputTokens, 22)
        XCTAssertEqual(meta.responseCache, "hit")
        XCTAssertEqual(meta.responseCacheAge, 7)
    }

    func testAKeyWithoutThePrefixIsRefusedBeforeAnyRequest() throws {
        XCTAssertThrowsError(try NRouter.resolveAPIKey("sk-openai-nope"))
        XCTAssertEqual(try NRouter.resolveAPIKey("sk-nrouter-abc"), "sk-nrouter-abc")
        XCTAssertThrowsError(try NRouter(apiKey: "bad-key"))
    }

    func testTheErrorEnvelopeIsReadNestedOrBare() {
        let meta = NRouterResponseMeta()
        let nested = NRouter.errorBody(
            status: 429,
            payload: ["error": ["message": "slow down", "code": "tpm_limit_exceeded"]],
            meta: meta
        )
        XCTAssertEqual(nested.code, "tpm_limit_exceeded")
        XCTAssertEqual(nested.message, "slow down")

        // A proxy that unwraps the envelope must not downgrade a typed error.
        let bare = NRouter.errorBody(
            status: 429,
            payload: ["message": "slow down", "code": "tpm_limit_exceeded"],
            meta: meta
        )
        XCTAssertEqual(bare.code, "tpm_limit_exceeded")
    }

    func testACodelessFourHundredIsSplitOnTheMessage() {
        // The gateway's MAIN error path emits {"error":{"type","message"}} with
        // no code, so this is the ordinary shape. Calling every codeless 400 a
        // request error makes .guardrailBlocked unreachable.
        let guardrail = NRouterError.fromCode(
            NRouterErrorBody(message: "blocked by guardrail 'pii'", status: 400)
        )
        XCTAssertEqual(caseName(guardrail), "guardrailBlocked")

        let malformed = NRouterError.fromCode(
            NRouterErrorBody(message: "invalid request: messages must be an array", status: 400)
        )
        XCTAssertEqual(caseName(malformed), "request")
    }

    func testACodeStillWinsOverTheStatus() {
        // The WAF and upstream passthrough DO send a code; it must beat status,
        // which cannot separate the two 429s.
        let error = NRouterError.fromCode(
            NRouterErrorBody(message: "slow down", code: "tpm_limit_exceeded", status: 429)
        )
        XCTAssertEqual(caseName(error), "rateLimit")
        XCTAssertEqual(error.body?.code, "tpm_limit_exceeded")
    }

    func testTheRealGatewayEnvelopeClassifies() {
        // Byte-for-byte what GatewayError::into_response emits.
        let payload: [String: Any] = [
            "error": ["type": "gateway_error", "message": "blocked by guardrail 'pii'"]
        ]
        let body = NRouter.errorBody(status: 400, payload: payload, meta: NRouterResponseMeta())
        XCTAssertNil(body.code, "the gateway sends no code on this path")
        XCTAssertEqual(caseName(NRouterError.fromCode(body)), "guardrailBlocked")
    }

    func testMultipartBodyCarriesTheNamedFilePart() async throws {
        // The gateway requires multipart/form-data with a binary `file` part
        // here; sent as JSON the endpoint is unreachable, which is what the
        // generic post(_:_:) helper would have done. Capture the REAL request
        // the SDK builds — asserting on a body the test rebuilt itself would
        // pass no matter what the SDK sent.
        StubProtocol.captured = nil
        StubProtocol.response = (
            200,
            ["content-type": "application/json"],
            Data(#"{"text":"hello"}"#.utf8)
        )
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        let client = try NRouter(apiKey: "sk-nrouter-test", session: URLSession(configuration: config))

        let result = try await client.audioTranscriptions(
            file: Data("fake-audio".utf8),
            fileName: "speech.mp3",
            fields: ["model": "whisper-1"]
        )

        let request = try XCTUnwrap(StubProtocol.captured)
        let contentType = try XCTUnwrap(request.value(forHTTPHeaderField: "Content-Type"))
        XCTAssertTrue(contentType.hasPrefix("multipart/form-data; boundary="), contentType)

        let body = String(data: try XCTUnwrap(StubProtocol.capturedBody), encoding: .utf8) ?? ""
        XCTAssertTrue(body.contains(#"name="file""#), "no file part: \(body)")
        // The extension is load-bearing: providers pick their decoder from it.
        XCTAssertTrue(body.contains("speech.mp3"), "file name not sent: \(body)")
        XCTAssertTrue(body.contains(#"name="model""#), "no model field: \(body)")
        XCTAssertTrue(body.contains("fake-audio"), "file bytes not sent")
        XCTAssertEqual(result.body["text"] as? String, "hello")
    }

    func testMessagesStreamYieldsAnthropicDeltaAndForcesStreamTrue() async throws {
        StubProtocol.captured = nil
        StubProtocol.response = (
            200,
            ["content-type": "text/event-stream", "x-nr-request-id": "req_stream"],
            Data(
                (
                    "event: content_block_delta\n" +
                    "data: {\"type\":\"content_block_delta\",\"delta\":{\"type\":\"text_delta\",\"text\":\"Claude\"}}\n\n" +
                    "event: message_stop\n" +
                    "data: {\"type\":\"message_stop\"}\n\n"
                ).utf8
            )
        )
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        let client = try NRouter(apiKey: "sk-nrouter-test", session: URLSession(configuration: config))
        let original: [String: Any] = ["model": "claude"]

        let response = try await client.messagesStream(original)
        var chunks: [NRouter.StreamChunk] = []
        for try await chunk in response.chunks { chunks.append(chunk) }

        XCTAssertEqual(chunks.map(\.delta).joined(), "Claude")
        XCTAssertEqual(response.meta.requestID, "req_stream")
        XCTAssertNil(original["stream"], "the helper must not mutate the caller's dictionary")
        let sent = try JSONSerialization.jsonObject(with: XCTUnwrap(StubProtocol.capturedBody))
            as? [String: Any]
        XCTAssertEqual(sent?["stream"] as? Bool, true)
    }

    func testStreamGuardrailEventThrowsTypedFailure() async throws {
        StubProtocol.response = (
            200,
            ["content-type": "text/event-stream", "x-nr-request-id": "req_blocked"],
            Data(
                "event: error\ndata: {\"error\":{\"type\":\"guardrail_blocked\",\"message\":\"the response was withheld by an output guardrail\"}}\n\n".utf8
            )
        )
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        let client = try NRouter(apiKey: "sk-nrouter-test", session: URLSession(configuration: config))
        let response = try await client.messagesStream([:])

        do {
            for try await _ in response.chunks {}
            XCTFail("an in-band guardrail error must not end as a clean stream")
        } catch let NRouterError.guardrailBlocked(body) {
            XCTAssertEqual(body.code, "guardrail_blocked")
            XCTAssertEqual(body.requestID, "req_blocked")
        }
    }

    func testCancellingBufferedCallStopsURLSessionTask() async throws {
        StubProtocol.hangs = true
        StubProtocol.stopped = false
        defer { StubProtocol.hangs = false }
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        let client = try NRouter(apiKey: "sk-nrouter-test", session: URLSession(configuration: config))
        let task = Task { try await client.chatCompletions(["model": "m"]) }
        try await Task.sleep(for: .milliseconds(100))
        task.cancel()
        _ = await task.result
        try await Task.sleep(for: .milliseconds(100))
        XCTAssertTrue(StubProtocol.stopped, "cancellation did not stop the billed URLSession task")
    }

    func testNoRenderingOfTheClientPrintsTheAPIKey() throws {
        // A struct reflects its stored properties, so print(), dump() and the
        // debugger all show `apiKey` unless all three protocols are supplied.
        // That is a credential leak from an ordinary log line (Rule #5).
        let client = try NRouter(apiKey: "sk-nrouter-SECRET123")

        let described = String(describing: client)
        let debugged = String(reflecting: client)
        var dumped = ""
        dump(client, to: &dumped)

        for (label, rendered) in [
            ("description", described), ("debugDescription", debugged), ("dump", dumped),
        ] {
            XCTAssertFalse(
                rendered.contains("SECRET123"),
                "the api key leaked into \(label): \(rendered)"
            )
        }
        XCTAssertTrue(described.contains("sk-nrouter-...T123"), described)
    }

    func testMultipartEscapesHostileFilenames() async throws {
        // A Unix filename may contain a quote, and CR/LF would end the header
        // line early — letting a chosen filename inject extra multipart parts.
        StubProtocol.captured = nil
        StubProtocol.response = (200, ["content-type": "application/json"], Data("{}".utf8))
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        let client = try NRouter(
            apiKey: "sk-nrouter-test",
            session: URLSession(configuration: config)
        )

        _ = try await client.audioTranscriptions(
            file: Data("x".utf8),
            fileName: "eeee\"\r\nContent-Disposition: form-data; name=\"injected\"\r\n\r\nowned\r\n--x.mp3",
            fields: [:]
        )

        let body = String(
            data: try XCTUnwrap(StubProtocol.capturedBody), encoding: .utf8
        ) ?? ""
        XCTAssertFalse(
            body.contains("name=\"injected\""),
            "a filename injected a multipart part: \(body)"
        )
        // The quote survives, escaped, rather than terminating the parameter.
        XCTAssertTrue(body.contains("\\\""), body)
    }

    func testMultipartRejectsHeaderInjectionThroughBoundary() async throws {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        let client = try NRouter(
            apiKey: "sk-nrouter-test",
            session: URLSession(configuration: config)
        )

        do {
            _ = try await client.multipart(
                "/audio/transcriptions",
                file: Data("audio".utf8),
                fileName: "speech.mp3",
                boundary: "safe\r\nX-Injected: true"
            )
            XCTFail("a boundary containing CR/LF reached URLSession")
        } catch let NRouterError.configuration(message) {
            XCTAssertTrue(message.contains("boundary"), message)
        } catch {
            XCTFail("wrong error for hostile multipart boundary: \(error)")
        }
    }

    func testANonJSONOrMalformedTwoHundredIsAFailure() async throws {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        let client = try NRouter(
            apiKey: "sk-nrouter-test",
            session: URLSession(configuration: config)
        )

        // /v1/audio/speech returns audio. Parsed as JSON it becomes [:] — the
        // caller is billed and receives nothing while the call reports 200.
        StubProtocol.response = (200, ["content-type": "audio/mpeg"], Data("ID3binary".utf8))
        do {
            _ = try await client.post("/audio/speech", [:])
            XCTFail("a non-JSON 2xx reported success")
        } catch let error as NRouterError {
            XCTAssertTrue(error.errorDescription?.contains("bytes(_:_:)") == true,
                          error.errorDescription ?? "")
        }

        // Truncated mid-stream, on a request that WAS billed.
        StubProtocol.response = (
            200, ["content-type": "application/json"], Data(#"{"choices":[{"#.utf8)
        )
        do {
            _ = try await client.chatCompletions([:])
            XCTFail("a malformed JSON 2xx reported success")
        } catch let error as NRouterError {
            XCTAssertTrue(error.errorDescription?.contains("billed") == true,
                          error.errorDescription ?? "")
        }
    }

    func testBytesReturnsTheRawBodyANonJSONEndpointSent() async throws {
        StubProtocol.response = (200, ["content-type": "audio/mpeg"], Data("binary-audio".utf8))
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        let client = try NRouter(
            apiKey: "sk-nrouter-test",
            session: URLSession(configuration: config)
        )
        let raw = try await client.bytes("/audio/speech", [:])
        XCTAssertEqual(String(data: raw.data, encoding: .utf8), "binary-audio")
        XCTAssertEqual(raw.statusCode, 200)

        // GET bytes without body
        let rawGet = try await client.bytes("/videos/123/content")
        XCTAssertEqual(rawGet.statusCode, 200)
    }

    func testAllRemainingEndpoints() async throws {
        StubProtocol.response = (200, ["content-type": "application/json"], Data(#"{"status":"ok"}"#.utf8))
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        let client = try NRouter(
            apiKey: "sk-nrouter-test",
            session: URLSession(configuration: config)
        )

        _ = try await client.completions(["model": "legacy"])
        XCTAssertEqual(StubProtocol.captured?.url?.path, "/v1/completions")

        _ = try await client.imagesGenerations(["model": "image-1"])
        XCTAssertEqual(StubProtocol.captured?.url?.path, "/v1/images/generations")

        _ = try await client.countTokens(["model": "claude-sonnet", "messages": []])
        XCTAssertEqual(StubProtocol.captured?.url?.path, "/v1/messages/count_tokens")

        _ = try await client.model("provider/model one")
        XCTAssertEqual(URLComponents(url: StubProtocol.captured!.url!, resolvingAgainstBaseURL: false)?.percentEncodedPath, "/v1/models/provider/model%20one")

        _ = try await client.createVideo(["model": "video-1", "prompt": "ocean"])
        XCTAssertEqual(StubProtocol.captured?.url?.path, "/v1/videos")

        _ = try await client.retrieveVideo("video/one")
        XCTAssertEqual(URLComponents(url: StubProtocol.captured!.url!, resolvingAgainstBaseURL: false)?.percentEncodedPath, "/v1/videos/video%2Fone")

        StubProtocol.response = (200, ["content-type": "audio/mpeg"], Data("audio".utf8))
        _ = try await client.audioSpeech(["model": "tts-1", "input": "hi"])
        XCTAssertEqual(StubProtocol.captured?.url?.path, "/v1/audio/speech")

        StubProtocol.response = (200, ["content-type": "video/mp4"], Data("video".utf8))
        _ = try await client.downloadVideoContent("video/one")
        XCTAssertEqual(URLComponents(url: StubProtocol.captured!.url!, resolvingAgainstBaseURL: false)?.percentEncodedPath, "/v1/videos/video%2Fone/content")

        StubProtocol.response = (200, ["content-type": "application/json"], Data(#"{"status":"ok"}"#.utf8))

        _ = try await client.embeddings(["model": "text-embedding-3", "input": "hi"])
        XCTAssertEqual(StubProtocol.captured?.url?.path, "/v1/embeddings")

        _ = try await client.messages(["model": "claude-sonnet", "messages": []])
        XCTAssertEqual(StubProtocol.captured?.url?.path, "/v1/messages")

        _ = try await client.responses(["model": "gpt-4o", "input": "hi"])
        XCTAssertEqual(StubProtocol.captured?.url?.path, "/v1/responses")

        _ = try await client.models()
        XCTAssertEqual(StubProtocol.captured?.url?.path, "/v1/models")

        _ = try await client.get("/custom-get")
        XCTAssertEqual(StubProtocol.captured?.url?.path, "/v1/custom-get")

        _ = try await client.audioTranslations(file: Data("speech".utf8), fileName: "speech.mp3")
        XCTAssertEqual(StubProtocol.captured?.url?.path, "/v1/audio/translations")
    }

    func testBytesErrorPathThrowsTypedError() async throws {
        StubProtocol.response = (
            402,
            ["content-type": "application/json"],
            Data(#"{"error":{"code":"insufficient_credits","message":"out of credits"}}"#.utf8)
        )
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        let client = try NRouter(
            apiKey: "sk-nrouter-test",
            session: URLSession(configuration: config)
        )

        do {
            _ = try await client.bytes("/audio/speech", [:])
            XCTFail("bytes did not throw on 402")
        } catch let error as NRouterError {
            if case .credit(let body) = error {
                XCTAssertEqual(body.code, "insufficient_credits")
            } else {
                XCTFail("wrong error case: \(error)")
            }
        }
    }

    func testResponseMetaAllFieldsAndDebugDescription() {
        let headers: [String: String] = [
            "x-nr-request-id": "req-123",
            "x-nr-request-cost": "0.005",
            "x-nr-cost-status": "exact",
            "x-nr-model": "gpt-4o",
            "x-nr-input-tokens": "10",
            "x-nr-output-tokens": "20",
            "x-nr-total-tokens": "30",
            "x-nr-cache-read-tokens": "5",
            "x-nr-cache-write-tokens": "2",
            "x-nr-limit-source": "key",
            "x-nr-auth-reason": "active",
            "x-nr-response-cache": "hit",
            "x-nr-response-cache-age": "60",
            "x-nr-budget-warning": "org soft_budget 80.00/100.00",
            "x-nr-guardrails": "pass",
        ]
        let http = HTTPURLResponse(
            url: URL(string: "https://api.nrouter.ai/v1/chat/completions")!,
            statusCode: 200,
            httpVersion: "HTTP/1.1",
            headerFields: headers
        )!
        let meta = NRouterResponseMeta(response: http)
        XCTAssertEqual(meta.requestID, "req-123")
        XCTAssertEqual(meta.cost, 0.005)
        XCTAssertEqual(meta.costStatus, "exact")
        XCTAssertEqual(meta.model, "gpt-4o")
        XCTAssertEqual(meta.inputTokens, 10)
        XCTAssertEqual(meta.outputTokens, 20)
        XCTAssertEqual(meta.totalTokens, 30)
        XCTAssertEqual(meta.cacheReadTokens, 5)
        XCTAssertEqual(meta.cacheWriteTokens, 2)
        XCTAssertEqual(meta.limitSource, "key")
        XCTAssertEqual(meta.authReason, "active")
        XCTAssertEqual(meta.responseCache, "hit")
        XCTAssertEqual(meta.responseCacheAge, 60)
        XCTAssertEqual(meta.budgetWarning, "org soft_budget 80.00/100.00")
        XCTAssertEqual(meta.guardrails, "pass")
        XCTAssertTrue(meta.isPriced)
    }

    func testBaseURLTrailingSlashIsNormalised() throws {
        let client = try NRouter(apiKey: "sk-nrouter-abc", baseURL: "https://api.nrouter.ai/v1/")
        XCTAssertEqual(client.baseURL, "https://api.nrouter.ai/v1")
    }

    // MARK: - Transport deadlines

    func testDefaultTimeoutsAreDeclaredAndWiredIntoTheDefaultSessions() {
        // The VALUES, so a silent change to any of them is a failing test.
        XCTAssertEqual(NRouter.defaultRequestTimeout, 180)
        XCTAssertEqual(NRouter.defaultResourceTimeout, 600)
        XCTAssertEqual(NRouter.defaultStreamingResourceTimeout, 86_400)

        // ...and that they reach the sessions. A constant nobody wires in is
        // decoration, and this SDK shipped `URLSession.shared` for exactly as
        // long as nothing asserted otherwise.
        let buffered = NRouter.makeDefaultSession().configuration
        XCTAssertEqual(buffered.timeoutIntervalForRequest, NRouter.defaultRequestTimeout)
        XCTAssertEqual(buffered.timeoutIntervalForResource, NRouter.defaultResourceTimeout)

        let streaming = NRouter.makeDefaultStreamingSession().configuration
        XCTAssertEqual(streaming.timeoutIntervalForRequest, NRouter.defaultRequestTimeout)
        XCTAssertEqual(
            streaming.timeoutIntervalForResource,
            NRouter.defaultStreamingResourceTimeout
        )

        // The two defaults this SDK deliberately left behind: `URLSession.shared`
        // carries a 60 s request timeout — below the gateway's own worst honest
        // case, so it aborted requests the gateway went on to bill — and a
        // seven-day resource timeout, which is not a bound.
        XCTAssertNotEqual(buffered.timeoutIntervalForRequest, 60)
        XCTAssertNotEqual(buffered.timeoutIntervalForResource, 7 * 24 * 60 * 60)
    }

    func testTheDefaultDeadlineReachesTheOutgoingRequest() async throws {
        // `URLRequest(url:)` starts at Foundation's 60 s and a request-level
        // timeout wins over the session configuration, so a session carrying
        // 180 s proves nothing on its own — the number has to arrive on the
        // request. Injecting a session whose configuration says 180 and reading
        // it back off the captured request is what proves the copy happens.
        StubProtocol.captured = nil
        StubProtocol.response = (200, ["content-type": "application/json"], Data("{}".utf8))
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        config.timeoutIntervalForRequest = NRouter.defaultRequestTimeout
        let client = try NRouter(
            apiKey: "sk-nrouter-test",
            session: URLSession(configuration: config)
        )

        _ = try await client.chatCompletions(["model": "gpt-5.4-mini"])

        let request = try XCTUnwrap(StubProtocol.captured)
        XCTAssertEqual(request.timeoutInterval, NRouter.defaultRequestTimeout)
    }

    func testAnInjectedSessionOverridesTheDefaultDeadline() async throws {
        // The injection point survives the change: a caller who supplies a
        // session gets THEIR deadline on the wire, not the SDK's.
        StubProtocol.captured = nil
        StubProtocol.response = (200, ["content-type": "application/json"], Data("{}".utf8))
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        config.timeoutIntervalForRequest = 7
        config.timeoutIntervalForResource = 11
        let client = try NRouter(
            apiKey: "sk-nrouter-test",
            session: URLSession(configuration: config)
        )

        _ = try await client.chatCompletions(["model": "gpt-5.4-mini"])

        let request = try XCTUnwrap(StubProtocol.captured)
        XCTAssertEqual(request.timeoutInterval, 7)
        XCTAssertNotEqual(request.timeoutInterval, NRouter.defaultRequestTimeout)
    }

    func testOneInjectedSessionAlsoCoversStreamingAndBinary() async throws {
        // A single injected `session:` replaces BOTH defaults, so a caller who
        // sets one deadline does not silently keep the SDK's on the streaming
        // and binary paths — the surface where the two differ most.
        StubProtocol.captured = nil
        StubProtocol.response = (200, ["content-type": "audio/mpeg"], Data([0x49, 0x44]))
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        config.timeoutIntervalForRequest = 9
        let client = try NRouter(
            apiKey: "sk-nrouter-test",
            session: URLSession(configuration: config)
        )

        _ = try await client.audioSpeech(["model": "tts-1", "input": "hi"])

        let request = try XCTUnwrap(StubProtocol.captured)
        XCTAssertEqual(request.timeoutInterval, 9)
    }

    func testStreamingAndBinaryAreNotCappedByTheBufferedCeiling() throws {
        // The property that keeps a paid response intact: a whole-request
        // ceiling severs an SSE stream mid-generation and truncates a long
        // /v1/videos/{id}/content download, both of them already billed. The
        // streaming session's ceiling must therefore be strictly larger, while
        // the stall bound stays identical on both.
        let buffered = NRouter.makeDefaultSession().configuration
        let streaming = NRouter.makeDefaultStreamingSession().configuration
        XCTAssertGreaterThan(
            streaming.timeoutIntervalForResource,
            buffered.timeoutIntervalForResource
        )
        XCTAssertEqual(streaming.timeoutIntervalForRequest, buffered.timeoutIntervalForRequest)
    }

    func testNRouterMemory() async throws {
        let mem = NRouterMemory()
        try await mem.add(["role": "user", "content": "Hello"])
        try await mem.add(["role": "assistant", "content": "Hi!"])
        let msgs = try await mem.messages()
        XCTAssertEqual(msgs.count, 2)

        // Forbidden tenancy keys rejected
        do {
            try await mem.add(["role": "user", "content": "evil", "organization_id": "org_123"])
            XCTFail("expected error on tenancy key")
        } catch {}

        try await mem.clear()
        let cleared = try await mem.messages()
        XCTAssertEqual(cleared.count, 0)
    }

    func testPromptHelpersAndConflicts() throws {
        let sel = try promptTemplate("tpl_123", variables: ["customer": "Acme"])
        XCTAssertEqual(sel.templateID, "tpl_123")
        XCTAssertEqual(sel.variables?["customer"] as? String, "Acme")

        XCTAssertThrowsError(try promptTemplate("  "))

        let merged = sel.withVariables(["customer": "Beta", "user": "Alice"])
        XCTAssertEqual(merged.variables?["customer"] as? String, "Beta")
        XCTAssertEqual(merged.variables?["user"] as? String, "Alice")

        var body: [String: Any] = [:]
        merged.apply(to: &body)
        XCTAssertEqual(body[promptTemplateIDField] as? String, "tpl_123")
        XCTAssertNotNil(body[promptVariablesField])

        let conflicts = systemVariableConflicts([
            "user_id": "u1",
            "custom": "v",
            "org_name": "orgX",
            "timestamp": 123,
        ])
        XCTAssertEqual(conflicts, ["org_name", "timestamp", "user_id"])
    }

    func testResponseMetaHelpers() {
        var meta = NRouterResponseMeta()
        meta.budgetWarning = "org soft_budget 80.50/100.00"
        meta.responseCache = "hit"
        meta.responseCacheAge = 42

        let bw = meta.parseBudgetWarning()
        XCTAssertNotNil(bw)
        XCTAssertEqual(bw?.scope, "org")
        XCTAssertEqual(bw?.spend, 80.50)
        XCTAssertEqual(bw?.ceiling, 100.00)

        XCTAssertTrue(meta.isCacheHit)
        XCTAssertFalse(meta.isCacheMiss)
        XCTAssertEqual(meta.cacheAgeSeconds, 42)
    }

    func testMediaAudioAndVideoHelpers() async throws {
        for fmt in ["mp3", "opus", "aac", "flac", "wav", "pcm"] {
            XCTAssertNoThrow(try validateAudioFormat(fmt))
        }
        XCTAssertThrowsError(try validateAudioFormat("unsupported_fmt"))

        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [StubProtocol.self]
        let client = try NRouter(apiKey: "sk-nrouter-test", session: URLSession(configuration: config))
        StubProtocol.response = (
            200,
            ["content-type": "application/json"],
            """
            {"id": "vid_abc", "status": "completed", "output": "https://example.com/video.mp4"}
            """.data(using: .utf8)!
        )
        let video = try await client.waitForVideo("vid_abc", pollInterval: 0.01, timeout: 1.0)
        XCTAssertEqual(video.body["status"] as? String, "completed")
    }

    func testSamplingPolicy() throws {
        XCTAssertTrue(isClaudeModel("claude-3-opus", provider: nil))
        XCTAssertTrue(isClaudeModel("custom-model", provider: "anthropic"))
        XCTAssertFalse(isClaudeModel("gpt-4o", provider: "openai"))

        let empty = try buildSamplingParams(advanced: false, model: "claude-3", temperature: 0.7, topP: 0.9)
        XCTAssertTrue(empty.isEmpty)

        // Claude model with topP suppresses temperature
        let claude = try buildSamplingParams(advanced: true, model: "claude-3-opus", temperature: 0.7, topP: 0.9)
        XCTAssertNil(claude["temperature"])
        XCTAssertEqual(claude["top_p"], 0.9)

        // GPT model keeps both
        let gpt = try buildSamplingParams(advanced: true, model: "gpt-4o", provider: "openai", temperature: 0.7, topP: 0.9)
        XCTAssertEqual(gpt["temperature"], 0.7)
        XCTAssertEqual(gpt["top_p"], 0.9)

        XCTAssertThrowsError(try buildSamplingParams(advanced: true, model: "gpt-4o", temperature: -1.0))
        XCTAssertThrowsError(try buildSamplingParams(advanced: true, model: "gpt-4o", topP: 1.5))
    }

    func testDiagnoseReasoningExhaustion() {
        let report = diagnoseReasoningExhaustion(finishReason: "length", outputTokens: 1000, reasoningTokens: 1000, content: "")
        XCTAssertTrue(report.exhausted)
        XCTAssertEqual(report.reasoningTokens, 1000)

        let normal = diagnoseReasoningExhaustion(finishReason: "stop", outputTokens: 50, reasoningTokens: 10, content: "ok")
        XCTAssertFalse(normal.exhausted)
    }

    func testParseRetryAfter() {
        let now = Date(timeIntervalSince1970: 1770000000)
        XCTAssertEqual(parseRetryAfter("120", now: now), 120)
        XCTAssertEqual(parseRetryAfter("0", now: now), 0)
        XCTAssertEqual(parseRetryAfter("  45  ", now: now), 45)
        XCTAssertEqual(parseRetryAfter("9999999999", now: now), maxRetryAfterSeconds)
        XCTAssertNil(parseRetryAfter(nil))
        XCTAssertNil(parseRetryAfter(""))
        XCTAssertNil(parseRetryAfter("invalid"))

        // HTTP-date future
        let futureDate = Date(timeIntervalSince1970: 1770000060)
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "EEE, dd MMM yyyy HH:mm:ss 'GMT'"
        let futureString = formatter.string(from: futureDate)
        XCTAssertEqual(parseRetryAfter(futureString, now: now), 60)

        // HTTP-date past
        let pastDate = Date(timeIntervalSince1970: 1769999900)
        let pastString = formatter.string(from: pastDate)
        XCTAssertEqual(parseRetryAfter(pastString, now: now), 0)
    }
}

/// Captures the request the SDK actually builds, so assertions are about the
/// SDK's behaviour rather than the test's own construction.
final class StubProtocol: URLProtocol {
    nonisolated(unsafe) static var captured: URLRequest?
    nonisolated(unsafe) static var capturedBody: Data?
    nonisolated(unsafe) static var response: (Int, [String: String], Data) = (200, [:], Data())
    nonisolated(unsafe) static var hangs = false
    nonisolated(unsafe) static var stopped = false

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.captured = request
        // URLSession moves an httpBody onto a stream; read it back out or the
        // body reads as nil and the assertions below would be vacuous.
        if let body = request.httpBody {
            Self.capturedBody = body
        } else if let stream = request.httpBodyStream {
            stream.open()
            var data = Data()
            let size = 4096
            let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: size)
            while stream.hasBytesAvailable {
                let read = stream.read(buffer, maxLength: size)
                if read <= 0 { break }
                data.append(buffer, count: read)
            }
            buffer.deallocate()
            stream.close()
            Self.capturedBody = data
        }

        let (status, headers, payload) = Self.response
        let http = HTTPURLResponse(
            url: request.url!,
            statusCode: status,
            httpVersion: "HTTP/1.1",
            headerFields: headers
        )!
        client?.urlProtocol(self, didReceive: http, cacheStoragePolicy: .notAllowed)
        if Self.hangs { return }
        client?.urlProtocol(self, didLoad: payload)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() { Self.stopped = true }
}
