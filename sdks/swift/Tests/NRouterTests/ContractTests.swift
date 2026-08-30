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

    func testEverySpecHeaderIsRead() {
        let expected = [
            "x-nr-request-id", "x-nr-request-cost", "x-nr-cost-status", "x-nr-model",
            "x-nr-input-tokens", "x-nr-output-tokens", "x-nr-total-tokens",
            "x-nr-cache-read-tokens", "x-nr-cache-write-tokens", "x-nr-limit-source",
            "x-nr-auth-reason", "x-nr-response-cache", "x-nr-response-cache-age",
        ]
        XCTAssertEqual(NRouterResponseMeta.headerNames.count, 13)
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
        XCTAssertTrue(meta.isPriced)
    }

    func testBaseURLTrailingSlashIsNormalised() throws {
        let client = try NRouter(apiKey: "sk-nrouter-abc", baseURL: "https://api.nrouter.ai/v1/")
        XCTAssertEqual(client.baseURL, "https://api.nrouter.ai/v1")
    }
}

/// Captures the request the SDK actually builds, so assertions are about the
/// SDK's behaviour rather than the test's own construction.
final class StubProtocol: URLProtocol {
    nonisolated(unsafe) static var captured: URLRequest?
    nonisolated(unsafe) static var capturedBody: Data?
    nonisolated(unsafe) static var response: (Int, [String: String], Data) = (200, [:], Data())

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
        client?.urlProtocol(self, didLoad: payload)
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}
