// nRouter Kotlin Example
//
// Demonstrates:
// 1. Basic chat completion with Coroutines
// 2. Response metadata inspection (cost, tokens, request ID, cache)
// 3. Typed error handling (NRouterError)
// 4. Prompt variables and custom configuration
//
// Maven: ai.nrouter:nrouter-sdk-kotlin:2.1.0

package ai.nrouter.examples

import ai.nrouter.sdk.NRouter
import ai.nrouter.sdk.NRouterError
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject

fun main() = runBlocking {
    val apiKey = System.getenv("NROUTER_API_KEY")
    if (apiKey == null) {
        println("Please set NROUTER_API_KEY environment variable.")
        return@runBlocking
    }

    try {
        // ━━━ 1. Client Initialization ━━━━━━━━━━━━━━━━━━━━━━━━
        val client = NRouter(apiKey = apiKey)

        // ━━━ 2. Chat Completion ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        println("--- Sending Chat Request ---")
        val requestBody = JSONObject()
            .put("model", "claude-sonnet-4-5-20250929")
            .put("messages", JSONArray().apply {
                put(JSONObject().put("role", "system").put("content", "You are a helpful assistant."))
                put(JSONObject().put("role", "user").put("content", "Explain what an LLM Gateway is in two sentences."))
            })
            .put("max_tokens", 100)

        val response = client.chatCompletions(requestBody)

        val content = response.body
            .getJSONArray("choices")
            .getJSONObject(0)
            .getJSONObject("message")
            .getString("content")

        println("\nResponse:\n$content")

        // ━━━ 3. Response Metadata Inspection ━━━━━━━━━━━━━━━━
        val meta = response.meta
        println("\n--- Response Metadata ---")
        println("Request ID:    ${meta.requestID ?: "n/a"}")
        println("Model Served:  ${meta.model ?: "n/a"}")
        println("Tokens:        Input: ${meta.inputTokens ?: 0}, Output: ${meta.outputTokens ?: 0}, Total: ${meta.totalTokens ?: 0}")

        if (meta.isPriced && meta.cost != null) {
            println("Exact Cost:    $${meta.cost}")
        } else {
            println("Cost Status:   ${meta.costStatus ?: "unpriced"}")
        }

        meta.limitSource?.let { println("Limit Source:  $it") }

    } catch (e: NRouterError.GuardrailBlocked) {
        println("\nBlocked by Guardrail: ${e.body.message}")
    } catch (e: NRouterError.Credit) {
        println("\nCredit Shortfall: ${e.body.message}")
    } catch (e: NRouterError.RateLimit) {
        println("\nRate Limit Hit from ${e.body.limitSource ?: "gateway"}: ${e.body.message}")
        if (e.isRetryable) println("Retryable with exponential backoff.")
    } catch (e: NRouterError.Authentication) {
        println("\nInvalid API Key: ${e.body.message}")
    } catch (e: NRouterError.Transport) {
        println("\nTransport / Network failure: ${e.message}")
    } catch (e: NRouterError) {
        println("\nGateway error [${e.code ?: "code"}]: ${e.body.message}")
    } catch (e: Exception) {
        println("\nUnexpected error: ${e.message}")
    }
}
