import XCTest
@testable import NRouter

final class LiveTests: XCTestCase {
    func testLiveClaudeStream() async throws {
        guard ProcessInfo.processInfo.environment["NROUTER_LIVE"] == "1" else {
            throw XCTSkip("set NROUTER_LIVE=1 to run the billed gateway acceptance")
        }
        let baseURL = ProcessInfo.processInfo.environment["NROUTER_BASE_URL"]
            ?? NRouter.defaultBaseURL
        let client = try NRouter(baseURL: baseURL)
        let response = try await client.messagesStream([
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 2,
            "messages": [["role": "user", "content": "Reply OK"]],
        ])
        var text = ""
        for try await chunk in response.chunks { text += chunk.delta }
        XCTAssertFalse(text.isEmpty)
        XCTAssertFalse(response.meta.requestID?.isEmpty ?? true)
    }
}
