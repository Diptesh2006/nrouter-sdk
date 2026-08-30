package ai.nrouter.sdk

import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import kotlin.test.Test
import kotlin.test.assertTrue

class LiveTest {
    @Test
    fun `live Claude stream reaches the configured gateway`() = runBlocking {
        if (System.getenv("NROUTER_LIVE") != "1") return@runBlocking
        val baseURL = System.getenv("NROUTER_BASE_URL") ?: NRouter.DEFAULT_BASE_URL
        val client = NRouter(baseURL = baseURL)
        val chunks = withTimeout(60_000) {
            client.messagesStream(
                JSONObject()
                    .put("model", "claude-haiku-4-5-20251001")
                    .put("max_tokens", 2)
                    .put(
                        "messages",
                        listOf(mapOf("role" to "user", "content" to "Reply OK")),
                    )
            ).toList()
        }
        assertTrue(chunks.any { it.delta.isNotEmpty() })
        assertTrue(!chunks.first().meta.requestId.isNullOrEmpty())
    }
}
