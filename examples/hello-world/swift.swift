// nRouter Swift hello world
//
// Swift Package Manager:
// .package(url: "https://github.com/nRouterAI/nrouter-sdk.git", from: "2.1.0")
//
// set NROUTER_API_KEY before running.

import Foundation
import NRouter

@main
struct HelloNRouter {
    static func main() async throws {
        let client = try NRouter() // reads NROUTER_API_KEY from environment
        // A Smart Router alias activates its strategy/fallback chain; a
        // concrete model id pins the request to that model.
        let model = ProcessInfo.processInfo.environment["NROUTER_MODEL"]
            ?? "claude-sonnet-4-5-20250929"

        let result = try await client.chatCompletions([
            "model": model,
            "messages": [
                ["role": "user", "content": "Reply with one short sentence saying hello from nRouter."]
            ],
            "max_tokens": 32
        ])

        if let choices = result.body["choices"] as? [[String: Any]],
           let firstChoice = choices.first,
           let message = firstChoice["message"] as? [String: Any],
           let content = message["content"] as? String {
            print(content)
        }

        let meta = result.meta
        print("Request ID: \(meta.requestID ?? "-")")
        print("Model: \(meta.model ?? "-")")
        if let cost = meta.cost {
            print("Cost: $\(cost)")
        } else {
            print("Cost: unpriced (\(meta.costStatus ?? "unknown"))")
        }
    }
}
