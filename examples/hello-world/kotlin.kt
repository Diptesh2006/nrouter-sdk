// nRouter Kotlin hello world
//
// Maven coordinate: ai.nrouter:nrouter-sdk-kotlin:2.1.0
// set NROUTER_API_KEY before running.

package ai.nrouter.examples

import ai.nrouter.sdk.NRouter
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject

fun main() = runBlocking {
    val client = NRouter() // reads NROUTER_API_KEY from environment

    val body = JSONObject()
        .put("model", "claude-sonnet-4-5-20250929")
        .put("messages", JSONArray().put(
            JSONObject()
                .put("role", "user")
                .put("content", "Reply with one short sentence saying hello from nRouter.")
        ))
        .put("max_tokens", 32)

    val response = client.chatCompletions(body)

    val content = response.body
        .getJSONArray("choices")
        .getJSONObject(0)
        .getJSONObject("message")
        .getString("content")

    println(content)
    println("Request ID: ${response.meta.requestID ?: "-"}")
    println("Model: ${response.meta.model ?: "-"}")
    println("Cost: ${response.meta.cost?.let { "$$it" } ?: "unpriced"}")
}
