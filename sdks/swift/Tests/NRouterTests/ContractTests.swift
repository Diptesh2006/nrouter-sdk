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

    func testBaseURLTrailingSlashIsNormalised() throws {
        let client = try NRouter(apiKey: "sk-nrouter-abc", baseURL: "https://api.nrouter.ai/v1/")
        XCTAssertEqual(client.baseURL, "https://api.nrouter.ai/v1")
    }
}
