package ai.nrouter.sdk.android.demo

import android.content.Context
import ai.nrouter.sdk.android.NRouterAndroid
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import org.json.JSONArray
import org.json.JSONObject

/** Call from a ViewModel with a short-lived key obtained from your backend. */
class JevSystemOneDemo(private val context: Context) {
    private val scope = CoroutineScope(Dispatchers.Main)

    fun run(apiKey: String) = scope.launch {
        val client = NRouterAndroid.create(context, apiKey)
        val result = client.chatCompletions(JSONObject()
                .put("model", "typesafe/jev")
                .put("temperature", 0)
                .put("max_tokens", 128)
                .put("messages", JSONArray()
                    .put(JSONObject().put("role", "system").put("content",
                        "Classify the incident. Return JSON only with priority, queue, and summary."))
                    .put(JSONObject().put("role", "user").put("content",
                        "Production payment requests return HTTP 500 in two regions."))))
            val text = result.body.getJSONArray("choices").getJSONObject(0)
                .getJSONObject("message").getString("content")
        println("Decision: $text")
        println("Request ID: ${result.meta.requestId}")
        println("Served model: ${result.meta.model}")
    }
}
