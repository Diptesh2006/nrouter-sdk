import Foundation
import NRouter

@main
struct JevSystemOneExample {
    static func main() async {
        guard let apiKey = ProcessInfo.processInfo.environment["NROUTER_API_KEY"] else {
            print("Set NROUTER_API_KEY before running.")
            return
        }

        do {
            let client = try NRouter(apiKey: apiKey)
            let response = try await client.chatCompletions([
                "model": "typesafe/jev",
                "temperature": 0,
                "max_tokens": 128,
                "messages": [
                    ["role": "system", "content": "Classify the incident. Return JSON only with priority, queue, and summary."],
                    ["role": "user", "content": "Production payment requests return HTTP 500 in two regions."]
                ]
            ])
            let choices = response.body["choices"] as? [[String: Any]]
            let message = choices?.first?["message"] as? [String: Any]
            print("Decision: \(message?["content"] as? String ?? "missing")")
            print("Request ID: \(response.meta.requestID ?? "n/a")")
            print("Served model: \(response.meta.model ?? "n/a")")
        } catch {
            print("nRouter request failed: \(error)")
        }
    }
}
