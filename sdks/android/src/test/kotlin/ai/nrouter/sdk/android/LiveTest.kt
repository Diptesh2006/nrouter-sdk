package ai.nrouter.sdk.android

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.withTimeout
import org.json.JSONObject
import org.junit.Assume.assumeTrue
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import kotlin.test.assertTrue

@RunWith(RobolectricTestRunner::class)
class LiveTest {
    @Test
    fun `Android facade streams Claude through the configured gateway`() = runBlocking {
        assumeTrue(System.getenv("NROUTER_LIVE") == "1")
        val context = ApplicationProvider.getApplicationContext<Context>()
        val client = NRouterAndroid.create(
            context,
            apiKey = System.getenv("NROUTER_API_KEY"),
            baseURL = System.getenv("NROUTER_BASE_URL") ?: "http://127.0.0.1:4000/v1",
        )

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
