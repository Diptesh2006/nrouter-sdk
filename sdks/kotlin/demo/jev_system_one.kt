package ai.nrouter.examples

import ai.nrouter.sdk.NRouter
import kotlinx.coroutines.runBlocking
import org.json.JSONArray
import org.json.JSONObject

/** TypeSafe Jev is a normal chat-completions model, not a separate SDK mode. */
fun main() = runBlocking {
    val apiKey = System.getenv("NROUTER_API_KEY") ?: error("Set NROUTER_API_KEY before running.")
    val client = NRouter(apiKey = apiKey)
    val response = client.chatCompletions(
            JSONObject()
                .put("model", "typesafe/jev")
                .put("temperature", 0)
                .put("max_tokens", 128)
                .put("messages", JSONArray()
                    .put(JSONObject().put("role", "system").put("content",
                        "Classify the incident. Return JSON only with priority, queue, and summary."))
                    .put(JSONObject().put("role", "user").put("content",
                        "Production payment requests return HTTP 500 in two regions.")))
    )
    println("Decision: ${response.body.getJSONArray("choices").getJSONObject(0).getJSONObject("message").getString("content")}")
    println("Request ID: ${response.meta.requestId}")
    println("Served model: ${response.meta.model}")
    println(if (response.meta.isPriced) "Exact cost: $${response.meta.cost}" else "Cost status: ${response.meta.costStatus}")
}
