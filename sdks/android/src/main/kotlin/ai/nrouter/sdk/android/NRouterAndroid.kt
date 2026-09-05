package ai.nrouter.sdk.android

import android.content.Context
import android.content.pm.PackageManager
import ai.nrouter.sdk.NRouter
import ai.nrouter.sdk.NRouterError
import okhttp3.OkHttpClient

/**
 * Android entry point for the nRouter SDK.
 *
 * The wire behaviour lives in `ai.nrouter.sdk.NRouter` and is shared with the
 * JVM. This object exists for one reason that is not cosmetic:
 *
 * **`System.getenv` does not work on Android.** It returns `null` for anything
 * an app did not inherit from a shell, so the core's `NROUTER_API_KEY` fallback
 * silently resolves to nothing on-device. Code that works in a unit test then
 * throws on a handset. [create] takes the key from somewhere Android actually
 * has it, and says so when it cannot.
 *
 * ```kotlin
 * // In your Application or a ViewModel:
 * val client = NRouterAndroid.create(context)
 *
 * viewModelScope.launch {
 *     val result = client.chatCompletions(
 *         JSONObject()
 *             .put("model", "claude-sonnet-4-5")
 *             .put("messages", listOf(mapOf("role" to "user", "content" to "Hello!")))
 *     )
 *     // The SDK already hops to Dispatchers.IO, so this is main-thread safe.
 * }
 * ```
 *
 * ### Do not ship a customer key inside the APK
 *
 * Anything compiled into an app — `BuildConfig`, a manifest `meta-data` entry,
 * a string resource — is readable by anyone who downloads it. A shipped key is
 * a published key. For a production app, mint a short-lived key on your own
 * backend and pass it to [create]; the manifest path is for internal builds and
 * prototypes, and [create] is deliberately explicit about that.
 *
 * ### Timeouts
 *
 * [create] never falls back to a bare `OkHttpClient()`. OkHttp's default read
 * timeout is 10 seconds, which is far below a normal LLM completion and far
 * below an image, video or TTS response — so on a handset the app would abort
 * requests the gateway completes, settles and BILLS, and the user would pay for
 * an answer they were shown as a failure. [defaultHttpClient] supplies the
 * bounds instead, and a caller can replace it wholesale.
 */
public object NRouterAndroid {

    /** The `meta-data` name read from `AndroidManifest.xml`. */
    public const val MANIFEST_KEY: String = "ai.nrouter.sdk.API_KEY"

    /**
     * The transport [create] builds when the caller injects none.
     *
     * Deliberately the SHARED core factory, not a second set of numbers. Two
     * clients disagreeing about how long an inference may take is how one
     * platform starts cutting completions the other tolerates, and the wire
     * behaviour is already shared for exactly this reason.
     *
     * It carries no retry policy. The gateway reserves credit once per customer
     * request and owns retry and failover; a client retry of a billed POST is a
     * second call and a second bill, which on a flaky mobile network is the
     * easiest possible way to charge a user twice.
     */
    @JvmStatic
    public fun defaultHttpClient(): OkHttpClient = NRouter.defaultHttpClient()

    /**
     * Build a client for Android.
     *
     * Resolution order, first hit wins:
     *  1. [apiKey], when you fetched one from your backend — the production path.
     *  2. `<meta-data android:name="ai.nrouter.sdk.API_KEY" .../>` in the
     *     manifest — convenient for internal builds, and readable by anyone
     *     holding the APK.
     *
     * @param http the transport. Defaults to [defaultHttpClient]; pass your own
     *   to control proxy, TLS, connection pool or timeouts, and it is used
     *   verbatim — the SDK layers nothing back on top of it.
     * @throws NRouterError.Configuration when neither supplies a usable key.
     *   Configuration, not Transport: nothing left the process, so it is
     *   permanent — a caller retrying on `isRetryable` would loop forever. The
     *   message names the Android situation rather than repeating the core's
     *   environment-variable advice, which cannot apply here.
     */
    @JvmStatic
    @JvmOverloads
    public fun create(
        context: Context,
        apiKey: String? = null,
        baseURL: String = NRouter.DEFAULT_BASE_URL,
        http: OkHttpClient = defaultHttpClient(),
        bufferedCallTimeoutMillis: Long = NRouter.BUFFERED_CALL_TIMEOUT_MILLIS,
        traceId: String? = null,
        sessionId: String? = null,
    ): NRouter {
        val resolved = apiKey?.takeIf { it.isNotEmpty() } ?: manifestKey(context)
        if (resolved.isNullOrEmpty()) {
            throw NRouterError.Configuration(
                "No nRouter API key on Android. System.getenv() is not available here, " +
                    "so pass the key to NRouterAndroid.create() — ideally one your backend " +
                    "minted — or declare <meta-data android:name=\"$MANIFEST_KEY\" " +
                    "android:value=\"sk-nrouter-...\"/> for an internal build."
            )
        }
        return NRouter(
            apiKey = resolved,
            baseURL = baseURL,
            http = http,
            bufferedCallTimeoutMillis = bufferedCallTimeoutMillis,
            traceId = traceId,
            sessionId = sessionId,
            clientPlatform = "android",
        )
    }

    /**
     * Read the key from the application's manifest `meta-data`, or `null`.
     *
     * A missing entry is an ordinary outcome, not an error: it just means the
     * caller is expected to supply the key. A `meta-data` value that Android
     * parsed as a non-string is also `null` — an `android:value` that looks
     * numeric is coerced by the toolchain, which is a real way to "set" a key
     * and still get nothing.
     */
    @JvmStatic
    public fun manifestKey(context: Context): String? = try {
        val app = context.packageManager.getApplicationInfo(
            context.packageName,
            PackageManager.GET_META_DATA,
        )
        app.metaData?.getString(MANIFEST_KEY)
    } catch (_: PackageManager.NameNotFoundException) {
        null
    }

    /** Maximum acceptable Retry-After value in seconds (24 hours). */
    public const val MAX_RETRY_AFTER_SECONDS: Long = NRouterError.MAX_RETRY_AFTER_SECONDS

    /**
     * Parse an RFC 9110 / RFC 7231 Retry-After header.
     * Delegates to [NRouterError.parseRetryAfter].
     */
    @JvmStatic
    @JvmOverloads
    public fun parseRetryAfter(
        header: String?,
        nowEpochSeconds: Long = System.currentTimeMillis() / 1000,
    ): Long? = NRouterError.parseRetryAfter(header, nowEpochSeconds)

    /**
     * Compute full-jitter exponential backoff with ceiling and optional Retry-After override.
     * Delegates to [NRouterError.computeJitteredBackoff].
     */
    @JvmStatic
    @JvmOverloads
    public fun computeJitteredBackoff(
        attempt: Int,
        baseDelayMs: Long = 500L,
        maxDelayMs: Long = 30000L,
        retryAfterSeconds: Long? = null,
        jitterFactor: Double = 0.5,
    ): Long = NRouterError.computeJitteredBackoff(
        attempt = attempt,
        baseDelayMs = baseDelayMs,
        maxDelayMs = maxDelayMs,
        retryAfterSeconds = retryAfterSeconds,
        jitterFactor = jitterFactor,
    )

    /**
     * Format a user-friendly, UI-safe message for mobile presentation.
     * Never exposes API keys, tokens, or internal tracebacks.
     */
    @JvmStatic
    public fun formatUserMessage(error: NRouterError): String = when (error) {
        is NRouterError.Authentication -> "Authentication failed. Please verify your API key."
        is NRouterError.RateLimit -> "Rate limit reached. Please wait and try again."
        is NRouterError.Credit, is NRouterError.BudgetExceeded -> "Credit balance or budget limit reached."
        is NRouterError.GuardrailBlocked -> "Request blocked by safety guardrails."
        is NRouterError.Service -> "Service temporarily unavailable. Please retry shortly."
        is NRouterError.Transport -> "Network connection error. Please check your connection."
        is NRouterError.NotFound -> "Requested resource or model was not found."
        else -> "Request failed. Please try again."
    }

    /**
     * Format a diagnostic message suitable for developer logging, with sanitized tokens.
     */
    @JvmStatic
    public fun formatDiagnosticMessage(error: NRouterError): String =
        ai.nrouter.sdk.formatError(error)

    /**
     * Redact API keys and sensitive tokens from strings.
     */
    @JvmStatic
    public fun redactKeys(input: String): String =
        ai.nrouter.sdk.redactKeys(input)

    /**
     * Parses a gateway error JSON payload into an error envelope.
     */
    @JvmStatic
    public fun parseGatewayErrorEnvelope(jsonString: String): ai.nrouter.sdk.NRouterErrorEnvelope =
        ai.nrouter.sdk.parseGatewayErrorEnvelope(jsonString)

    /** Extracts trace routing headers from response metadata into a map. */
    @JvmStatic
    public fun extractTraceHeaders(meta: ai.nrouter.sdk.NRouterResponseMeta?): Map<String, String> =
        ai.nrouter.sdk.extractTraceHeaders(meta)

    /** Extracts trace routing headers from an existing headers map. */
    @JvmStatic
    public fun extractTraceHeaders(headers: Map<String, String>?): Map<String, String> =
        ai.nrouter.sdk.extractTraceHeaders(headers)

    /** Injects trace and session context into an existing headers map, rejecting CRLF characters. */
    @JvmStatic
    public fun withTraceContext(headers: Map<String, String>?, traceId: String?, sessionId: String?): Map<String, String> =
        ai.nrouter.sdk.withTraceContext(headers, traceId, sessionId)
}
