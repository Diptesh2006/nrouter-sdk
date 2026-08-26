package ai.nrouter.sdk.android

import android.content.Context
import androidx.test.core.app.ApplicationProvider
import ai.nrouter.sdk.NRouter
import ai.nrouter.sdk.NRouterError
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertNull
import kotlin.test.assertTrue

/**
 * Android-specific behaviour only. The wire contract is proven once, in the
 * shared `sdks/kotlin` module; repeating it here would be two copies of one
 * promise.
 */
@RunWith(RobolectricTestRunner::class)
class NRouterAndroidTest {

    private val context: Context get() = ApplicationProvider.getApplicationContext()

    @Test
    fun `an explicit key builds a client`() {
        val client = NRouterAndroid.create(context, apiKey = "sk-nrouter-test")
        assertEquals(NRouter.DEFAULT_BASE_URL, client.baseURL)
    }

    @Test
    fun `a missing key names the Android situation, not the env var`() {
        val error = assertFailsWith<NRouterError.Transport> { NRouterAndroid.create(context) }
        val message = error.message.orEmpty()
        // The core's advice ("set NROUTER_API_KEY") is unactionable on a
        // handset. If this message ever degrades into that, a developer is sent
        // to do something that cannot work.
        assertTrue(
            message.contains("System.getenv() is not available"),
            "the Android error must explain why the env var cannot help: $message",
        )
        assertTrue(message.contains(NRouterAndroid.MANIFEST_KEY))
    }

    @Test
    fun `an absent manifest entry is null rather than an exception`() {
        assertNull(NRouterAndroid.manifestKey(context))
    }

    @Test
    fun `key validation still applies on Android`() {
        assertFailsWith<NRouterError.Transport> {
            NRouterAndroid.create(context, apiKey = "sk-openai-nope")
        }
    }

    @Test
    fun `a custom base URL reaches the client`() {
        val client = NRouterAndroid.create(
            context,
            apiKey = "sk-nrouter-test",
            baseURL = "https://api-stage.nrouter.ai/v1/",
        )
        assertEquals("https://api-stage.nrouter.ai/v1", client.baseURL)
    }
}
