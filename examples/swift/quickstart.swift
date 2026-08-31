// nRouter Swift Example
//
// Demonstrates:
// 1. Basic chat completion with Claude Sonnet
// 2. Response metadata inspection (cost, tokens, request ID, cache)
// 3. Error handling with typed NRouterError
// 4. Custom base URL & configuration
//
// Swift Package Manager:
// .package(url: "https://github.com/nRouterAI/nrouter-sdk.git", from: "2.1.0")

import Foundation
import NRouter

@main
struct NRouterExample {
    static func main() async {
        guard let apiKey = ProcessInfo.processInfo.environment["NROUTER_API_KEY"] else {
            print("Please set NROUTER_API_KEY environment variable.")
            return
        }

        do {
            // ━━━ 1. Client Initialization ━━━━━━━━━━━━━━━━━━━━━━━━
            let client = try NRouter(apiKey: apiKey)

            // ━━━ 2. Chat Completion ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            print("--- Sending Chat Request ---")
            let requestBody: [String: Any] = [
                "model": "claude-sonnet-4-5-20250929",
                "messages": [
                    ["role": "system", "content": "You are a concise AI assistant."],
                    ["role": "user", "content": "Explain what an LLM Gateway is in two sentences."]
                ],
                "max_tokens": 100
            ]

            let response = try await client.chatCompletions(requestBody)

            if let choices = response.body["choices"] as? [[String: Any]],
               let firstChoice = choices.first,
               let message = firstChoice["message"] as? [String: Any],
               let content = message["content"] as? String {
                print("\nResponse:")
                print(content)
            }

            // ━━━ 3. Response Metadata Inspection ━━━━━━━━━━━━━━━━
            let meta = response.meta
            print("\n--- Response Metadata ---")
            print("Request ID:    \(meta.requestID ?? "n/a")")
            print("Model Served:  \(meta.model ?? "n/a")")
            print("Tokens:        Input: \(meta.inputTokens ?? 0), Output: \(meta.outputTokens ?? 0), Total: \(meta.totalTokens ?? 0)")

            if meta.isPriced, let cost = meta.cost {
                print("Exact Cost:    $\(cost)")
            } else {
                print("Cost Status:   \(meta.costStatus ?? "unpriced")")
            }

            if let limitSource = meta.limitSource {
                print("Limit Source:  \(limitSource)")
            }

        } catch let error as NRouterError {
            // ━━━ 4. Typed Error Handling ━━━━━━━━━━━━━━━━━━━━━━━━
            print("\n[nRouter Error]: \(error.localizedDescription)")
            switch error {
            case .guardrailBlocked(let body):
                print("Blocked by Guardrail: \(body.message)")
            case .credit(let body):
                print("Credit Shortfall: \(body.message)")
            case .rateLimit(let body):
                print("Rate Limit Hit from \(body.limitSource ?? "gateway"): \(body.message)")
                if error.isRetryable {
                    print("This error is retryable with backoff.")
                }
            case .authentication(let body):
                print("Invalid API Key: \(body.message)")
            case .notFound(let body):
                print("Model Not Found: \(body.message)")
            case .transport(let message):
                print("Transport / Network failure: \(message)")
            default:
                print("Gateway error code: \(error.code ?? "unknown")")
            }
        } catch {
            print("Unexpected error: \(error)")
        }
    }
}
