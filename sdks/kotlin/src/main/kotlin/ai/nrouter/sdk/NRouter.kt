package ai.nrouter.sdk

import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject

/**
 * nRouter client — one API key for models across six provider clouds.
 *
 * The gateway speaks the OpenAI wire format, so request and response bodies are
 * the shapes you already know. This client adds the two things a raw HTTP call
 * does not: key validation before egress, and the `x-nr-*` metadata (cost,
 * tokens, cache outcome) handed back beside every body.
 *
 * ```kotlin
 * val client = NRouter()                       // reads NROUTER_API_KEY
 * val result = client.chatCompletions(
 *     JSONObject()
 *         .put("model", "claude-sonnet-4-5")
 *         .put("messages", listOf(mapOf("role" to "user", "content" to "Hello!")))
 * )
 * // Unpriced is unknown, not free. Never render a null cost as 0.
 * println(result.meta.cost?.let { "cost $$it" } ?: "unpriced")
 * ```
 *
 * The suspending calls are non-blocking and CANCELLABLE: they use OkHttp's
 * async API, so calling one from a UI coroutine never blocks the main thread,
 * and cancelling that coroutine actually cancels the in-flight request rather
 * than leaving a billed inference running.
 */
public class NRouter @JvmOverloads constructor(
    apiKey: String? = null,
    baseURL: String = DEFAULT_BASE_URL,
    private val http: OkHttpClient = OkHttpClient(),
) {
    private val apiKey: String = resolveApiKey(apiKey)

    /** The gateway this client talks to, with any trailing slash removed. */
    public val baseURL: String = baseURL.trimEnd('/')

    /**
     * Never the key. A plain `class` already has an identity `toString`, but
     * this is stated rather than relied upon: turning it into a `data class`
     * later would silently start printing `apiKey` into every log (Rule #5).
     */
    override fun toString(): String =
        "NRouter(baseURL=$baseURL, apiKey=$KEY_PREFIX...${apiKey.takeLast(4)})"

    /** A body paired with the metadata the gateway reported for it. */
    public data class Response(
        val body: JSONObject,
        val meta: NRouterResponseMeta,
        val statusCode: Int,
    )

    /** `POST /chat/completions` */
    public suspend fun chatCompletions(body: JSONObject): Response = post("/chat/completions", body)

    /** `POST /completions` — the legacy text-completions wire. */
    public suspend fun completions(body: JSONObject): Response = post("/completions", body)

    /** `POST /embeddings` */
    public suspend fun embeddings(body: JSONObject): Response = post("/embeddings", body)

    /** `POST /messages` — the Anthropic wire format the gateway also serves. */
    public suspend fun messages(body: JSONObject): Response = post("/messages", body)

    /** `POST /responses` */
    public suspend fun responses(body: JSONObject): Response = post("/responses", body)

    /** `POST /images/generations` */
    public suspend fun imagesGenerations(body: JSONObject): Response = post("/images/generations", body)

    /** `POST /messages/count_tokens` — counts input without generating. */
    public suspend fun countTokens(body: JSONObject): Response = post("/messages/count_tokens", body)

    /**
     * `POST /audio/transcriptions` — Whisper-style speech to text.
     *
     * multipart/form-data, not JSON: the gateway requires a binary `file` part
     * here, so the JSON helpers cannot reach this endpoint at all.
     *
     * @param file the audio bytes.
     * @param fileName a name carrying the real extension — the upstream
     *   providers select their decoder from it, so "audio" with no extension is
     *   rejected where "speech.mp3" is not.
     * @param fields the remaining form fields, e.g. `"model"`.
     */
    public suspend fun audioTranscriptions(
        file: ByteArray,
        fileName: String,
        fields: Map<String, String> = emptyMap(),
    ): Response = multipart("/audio/transcriptions", file, fileName, fields)

    /** `POST /audio/translations` — speech in any language to English text. */
    public suspend fun audioTranslations(
        file: ByteArray,
        fileName: String,
        fields: Map<String, String> = emptyMap(),
    ): Response = multipart("/audio/translations", file, fileName, fields)

    /** `POST /audio/speech` — generated audio bytes plus response metadata. */
    public suspend fun audioSpeech(body: JSONObject): RawResponse = bytes("/audio/speech", body)

    /** Any multipart `POST` under the gateway's `/v1` root. */
    public suspend fun multipart(
        path: String,
        file: ByteArray,
        fileName: String,
        fields: Map<String, String> = emptyMap(),
        filePartName: String = "file",
    ): Response {
        val builder = MultipartBody.Builder().setType(MultipartBody.FORM)
        fields.forEach { (key, value) -> builder.addFormDataPart(key, value) }
        builder.addFormDataPart(
            filePartName,
            fileName,
            file.toRequestBody(OCTET_STREAM),
        )
        return send(Request.Builder().url(url(path)).post(builder.build()).build())
    }

    /** `GET /models` — what this key is allowed to route to. */
    public suspend fun models(): Response = get("/models")

    /** `GET /models/{model_id}` — one model visible to this key. */
    public suspend fun model(modelID: String): Response = get("/models/${modelPath(modelID)}")

    /** `POST /videos` — starts a video generation job. */
    public suspend fun createVideo(body: JSONObject): Response = post("/videos", body)

    /** `GET /videos/{id}` — polls one video generation job. */
    public suspend fun retrieveVideo(videoID: String): Response = get("/videos/${pathSegment(videoID)}")

    /** `GET /videos/{id}/content` — generated video bytes. */
    public suspend fun downloadVideoContent(videoID: String): RawResponse =
        bytes("/videos/${pathSegment(videoID)}/content")

    /** Any `POST` path under the gateway's `/v1` root. */
    public suspend fun post(path: String, body: JSONObject): Response {
        val request = Request.Builder()
            .url(url(path))
            .post(body.toString().toRequestBody(JSON))
            .build()
        return send(request)
    }

    /** Any `GET` path under the gateway's `/v1` root. */
    public suspend fun get(path: String): Response =
        send(Request.Builder().url(url(path)).get().build())

    /** Raw bytes plus metadata, for the endpoints that do not return JSON. */
    public data class RawResponse(
        val bytes: ByteArray,
        val meta: NRouterResponseMeta,
        val statusCode: Int,
    ) {
        // ByteArray uses identity equals; data-class equality would be a lie.
        override fun equals(other: Any?): Boolean = this === other
        override fun hashCode(): Int = System.identityHashCode(this)
    }

    /**
     * Raw bytes plus metadata, for the endpoints that do not return JSON.
     *
     * `/v1/audio/speech` returns audio, `/v1/videos/{id}/content` returns a
     * video, and `stream: true` returns SSE. The JSON helpers refuse those
     * rather than handing back an empty body for a request you were billed
     * for; this is the method that returns them.
     */
    public suspend fun bytes(
        path: String,
        body: JSONObject? = null,
    ): RawResponse {
        val builder = Request.Builder().url(url(path))
        val request = if (body == null) {
            builder.get().build()
        } else {
            builder.post(body.toString().toRequestBody(JSON)).build()
        }

        return runCall(request) {
            val status = it.code
            val meta = NRouterResponseMeta.fromLookup { name -> it.header(name) }
            val raw = it.body?.bytes() ?: ByteArray(0)
            if (status in 200..299) {
                RawResponse(raw, meta, status)
            } else {
                val parsed = runCatching { JSONObject(String(raw)) }.getOrElse { JSONObject() }
                throw NRouterError.fromCode(errorBody(status, parsed, meta))
            }
        }
    }

    private fun url(path: String): String = "$baseURL/${path.trimStart('/')}"

    private fun pathSegment(value: String): String =
        URLEncoder.encode(value, StandardCharsets.UTF_8.toString()).replace("+", "%20")

    // Model IDs are wildcard paths (for example `provider/model`), not one
    // segment. Preserve their namespace separators while escaping each part.
    private fun modelPath(value: String): String = value.split('/').joinToString("/") { pathSegment(it) }

    /**
     * Run one call and read it, cancelling the call if the caller is cancelled.
     *
     * `withContext(Dispatchers.IO)` alone does NOT do this: a cancelled
     * coroutine does not interrupt a blocking OkHttp read, so on Android a
     * ViewModel that goes away mid-inference leaves the request running — and a
     * running inference is a BILLED one.
     *
     * The body is read INSIDE the callback, on OkHttp's own dispatcher thread,
     * so the continuation stays cancellable for the whole exchange rather than
     * only while waiting for headers. That distinction is the entire point: a
     * server sends headers promptly and streams the body afterwards, so by the
     * time a caller gives up, the wait is over and the read is what is still
     * running. `Call.cancel()` closes the stream and aborts it.
     *
     * `Job.invokeOnCompletion` is deliberately NOT used here — it fires when a
     * job has finished, not when it starts cancelling, so it never runs while
     * the read is still blocked. It was tried, and the request ran to
     * completion anyway.
     */
    private suspend fun <T> runCall(
        request: Request,
        read: (okhttp3.Response) -> T,
    ): T {
        val authed = request.newBuilder()
            .header("Authorization", "Bearer $apiKey")
            .build()

        return suspendCancellableCoroutine { continuation ->
            val call = http.newCall(authed)
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object : okhttp3.Callback {
                override fun onFailure(call: okhttp3.Call, e: java.io.IOException) {
                    if (continuation.isCancelled) return
                    continuation.resumeWithException(
                        NRouterError.Transport(
                            e.message ?: "the request never reached nRouter"
                        )
                    )
                }

                override fun onResponse(call: okhttp3.Call, response: okhttp3.Response) {
                    try {
                        continuation.resume(response.use(read))
                    } catch (e: Throwable) {
                        if (continuation.isCancelled) return
                        continuation.resumeWithException(e)
                    }
                }
            })
        }
    }

    private suspend fun send(request: Request): Response = runCall(request) {
            val status = it.code
            val meta = NRouterResponseMeta.fromLookup { name -> it.header(name) }
            val contentType = it.header("content-type").orEmpty().lowercase()
            val text = it.body?.string().orEmpty()

            if (status in 200..299) {
                // A 2xx that is not JSON is a REAL RESPONSE you were billed for
                // — /v1/audio/speech returns audio, video content returns
                // bytes, stream:true returns SSE. Parsing those as JSON yields
                // an empty object, so the caller pays and receives nothing
                // while the call reports success. Refuse loudly instead.
                if (!contentType.contains("json")) {
                    throw NRouterError.Transport(
                        "nRouter returned $status with content-type '$contentType', which " +
                            "is not JSON. Use bytes() for binary or streaming endpoints " +
                            "(/v1/audio/speech, /v1/videos/{id}/content, or stream: true); " +
                            "the JSON helpers would report success with an empty body."
                    )
                }
                // A 2xx whose JSON does not parse is NOT an empty response —
                // it is a truncated or corrupted one, for a request that was
                // billed. Returning {} here reports success with nothing in it.
                val body = runCatching { JSONObject(text) }.getOrElse { e ->
                    throw NRouterError.Transport(
                        "nRouter returned $status with unparseable JSON (${e.message}); " +
                            "the request was billed but the body did not arrive intact."
                    )
                }
                Response(body, meta, status)
            } else {
                val parsed = runCatching { JSONObject(text) }.getOrElse { JSONObject() }
                throw NRouterError.fromCode(errorBody(status, parsed, meta))
            }
    }

    public companion object {
        /** The gateway's customer surface. A dynamic value: override for stage. */
        public const val DEFAULT_BASE_URL: String = "https://api.nrouter.ai/v1"

        /** The one environment variable this SDK reads. */
        public const val ENV_KEY: String = "NROUTER_API_KEY"

        /** Every customer key carries this prefix. */
        public const val KEY_PREFIX: String = "sk-nrouter-"

        private val JSON = "application/json; charset=utf-8".toMediaType()
        private val OCTET_STREAM = "application/octet-stream".toMediaType()

        /**
         * Resolve and validate a key: explicit argument first, then environment.
         *
         * Validation happens before any request so a malformed key fails here
         * rather than as a 401 that reads like a revoked credential.
         */
        @JvmStatic
        @JvmOverloads
        public fun resolveApiKey(explicit: String? = null): String {
            val key = explicit?.takeIf { it.isNotEmpty() } ?: System.getenv(ENV_KEY).orEmpty()
            if (key.isEmpty()) {
                throw NRouterError.Configuration(
                    "No nRouter API key: pass one explicitly or set $ENV_KEY."
                )
            }
            if (!key.startsWith(KEY_PREFIX)) {
                throw NRouterError.Configuration(
                    "nRouter API keys start with '$KEY_PREFIX'; got one that does not."
                )
            }
            return key
        }

        /**
         * Pull the gateway's stable `code` and message out of an error payload.
         *
         * The gateway nests them under `error`; a bare object is accepted too,
         * so a proxy that reshapes the envelope cannot downgrade a typed error
         * into a generic one.
         */
        @JvmStatic
        public fun errorBody(
            status: Int,
            payload: JSONObject,
            meta: NRouterResponseMeta,
        ): NRouterErrorBody {
            val node = payload.optJSONObject("error") ?: payload
            return NRouterErrorBody(
                message = node.optString("message").ifEmpty { "nRouter request failed" },
                code = node.optString("code").ifEmpty { null },
                status = status,
                requestId = meta.requestId,
                limitSource = meta.limitSource,
                authReason = meta.authReason,
            )
        }
    }
}
