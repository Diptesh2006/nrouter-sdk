package ai.nrouter.sdk

import java.net.URLEncoder
import java.nio.charset.StandardCharsets
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
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
 *
 * ### Timeouts
 *
 * The default transport is [defaultHttpClient], NOT `OkHttpClient()`: OkHttp's
 * own 10-second read timeout is far below a normal completion and far below an
 * image, video or TTS response, so the library defaults abort requests the
 * gateway completes, settles and BILLS. Pass your own [OkHttpClient] to replace
 * them entirely — nothing here is layered back on top of yours.
 */
public class NRouter @JvmOverloads constructor(
    apiKey: String? = null,
    baseURL: String = DEFAULT_BASE_URL,
    http: OkHttpClient = defaultHttpClient(),
    bufferedCallTimeoutMillis: Long = BUFFERED_CALL_TIMEOUT_MILLIS,
    traceId: String? = null,
    sessionId: String? = null,
    clientPlatform: String? = null,
) {
    private val apiKey: String = resolveApiKey(apiKey)

    /**
     * The transport for STREAMING and BINARY paths — no whole-call ceiling.
     *
     * Exposed so a caller can read the timeouts actually in force rather than
     * inferring them from the builder they passed.
     */
    public val httpClient: OkHttpClient = http

    /**
     * The transport for BUFFERED JSON paths — [httpClient] plus a whole-call
     * ceiling, sharing its connection pool and dispatcher.
     *
     * A buffered call is one where "the server went quiet" and "this response
     * is legitimately long" are the same observation, so a total ceiling is the
     * only thing standing between a stalled peer and a caller that never
     * returns. Streaming and binary downloads are the opposite case: being long
     * is NORMAL there, and a ceiling that fires kills a response the gateway
     * has already completed, settled and BILLED.
     *
     * An injected client that already carries its own `callTimeout` is used
     * VERBATIM — the caller stated a ceiling and it is not ours to widen or
     * narrow. OkHttp cannot distinguish "unset" from "deliberately unbounded"
     * (both are 0), so 0 is read as unset and takes the SDK default.
     */
    public val bufferedHttpClient: OkHttpClient =
        if (http.callTimeoutMillis == 0 && bufferedCallTimeoutMillis > 0) {
            http.newBuilder().callTimeout(bufferedCallTimeoutMillis, TimeUnit.MILLISECONDS).build()
        } else {
            http
        }

    /** The gateway this client talks to, with any trailing slash removed. */
    public val baseURL: String = run {
        val trimmed = baseURL.trim()
        if (trimmed.contains('\r') || trimmed.contains('\n') || trimmed.contains('\t')) {
            throw NRouterError.Configuration("baseURL contains invalid whitespace or control characters")
        }
        val uri = try {
            java.net.URI(trimmed)
        } catch (e: Exception) {
            throw NRouterError.Configuration("invalid nRouter gateway URL: ${e.message}")
        }
        val scheme = uri.scheme?.lowercase(java.util.Locale.ROOT)
        if (scheme != "http" && scheme != "https") {
            throw NRouterError.Configuration("invalid nRouter gateway URL scheme '$scheme'")
        }
        if (uri.userInfo != null) {
            throw NRouterError.Configuration("nRouter gateway URL must not contain credentials")
        }
        val host = uri.host?.trim('[', ']')?.lowercase(java.util.Locale.ROOT)
            ?: throw NRouterError.Configuration("nRouter gateway URL must include a host")
        val isLoopback = host == "localhost" || host == "127.0.0.1" || host == "::1" || host == "0.0.0.0" || host.endsWith(".local")
        if (scheme == "http" && !isLoopback) {
            throw NRouterError.Configuration("nRouter gateway URL must use HTTPS; HTTP is allowed only for loopback development")
        }
        trimmed.trimEnd('/')
    }

    /** Configured trace identifier propagated as x-nr-trace-id, or null. */
    public val traceId: String? = traceId?.also {
        if (it.contains('\r') || it.contains('\n')) {
            throw IllegalArgumentException("traceId must not contain CRLF characters")
        }
    }

    /** Configured session identifier propagated as x-nr-session-id, or null. */
    public val sessionId: String? = sessionId?.also {
        if (it.contains('\r') || it.contains('\n')) {
            throw IllegalArgumentException("sessionId must not contain CRLF characters")
        }
    }

    /** Client platform identifier propagated as x-nr-client-platform, or null. */
    public val clientPlatform: String? = clientPlatform

    /** Returns a copy of this client with the specified trace identifier. */
    public fun withTraceId(traceId: String?): NRouter =
        NRouter(apiKey, baseURL, httpClient, bufferedHttpClient.callTimeoutMillis.toLong(), traceId, sessionId, clientPlatform)

    /** Returns a copy of this client with the specified session identifier. */
    public fun withSessionId(sessionId: String?): NRouter =
        NRouter(apiKey, baseURL, httpClient, bufferedHttpClient.callTimeoutMillis.toLong(), traceId, sessionId, clientPlatform)

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

    /** One provider-native SSE frame plus portable incremental text. */
    public data class StreamChunk(
        val event: String?,
        val delta: String,
        val raw: JSONObject,
        val meta: NRouterResponseMeta,
    )

    /** `POST /chat/completions` */
    public suspend fun chatCompletions(body: JSONObject): Response = post("/chat/completions", body)

    /** `POST /completions` — the legacy text-completions wire. */
    public suspend fun completions(body: JSONObject): Response = post("/completions", body)

    /** `POST /embeddings` */
    public suspend fun embeddings(body: JSONObject): Response = post("/embeddings", body)

    /** `POST /messages` — the Anthropic wire format the gateway also serves. */
    public suspend fun messages(body: JSONObject): Response = post("/messages", normalizeAnthropicMessages(body))

    /** `POST /responses` */
    public suspend fun responses(body: JSONObject): Response = post("/responses", body)

    /** Incremental `POST /chat/completions`; forces `stream: true` in a copy. */
    public fun chatCompletionsStream(body: JSONObject): Flow<StreamChunk> =
        stream("/chat/completions", body)

    /** Incremental legacy `POST /completions`. */
    public fun completionsStream(body: JSONObject): Flow<StreamChunk> =
        stream("/completions", body)

    /** Incremental native Anthropic `POST /messages`. */
    public fun messagesStream(body: JSONObject): Flow<StreamChunk> =
        stream("/messages", normalizeAnthropicMessages(body))

    /** Incremental `POST /responses`. */
    public fun responsesStream(body: JSONObject): Flow<StreamChunk> =
        stream("/responses", body)

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
            .post(encodeJson(body).toRequestBody(JSON))
            .build()
        return send(request)
    }

    /**
     * Stream any JSON `POST` under the gateway's `/v1` root as SSE.
     *
     * The returned Flow is cold: collection starts the request. Cancelling the
     * collector calls OkHttp's `Call.cancel()` immediately, which is
     * load-bearing for billed streams that may otherwise continue unseen.
     */
    public fun stream(path: String, body: JSONObject): Flow<StreamChunk> = callbackFlow {
        val streamed = normalizedObject(body).put("stream", true)
        val reqBuilder = Request.Builder()
            .url(url(path))
            .header("Authorization", "Bearer $apiKey")
            .header("Accept", "text/event-stream")
            .header("x-nr-client-language", "kotlin")
        if (!clientPlatform.isNullOrEmpty()) {
            reqBuilder.header("x-nr-client-platform", clientPlatform)
        }
        if (!traceId.isNullOrEmpty()) {
            reqBuilder.header("x-nr-trace-id", traceId)
        }
        if (!sessionId.isNullOrEmpty()) {
            reqBuilder.header("x-nr-session-id", sessionId)
        }
        val request = reqBuilder
            .post(streamed.toString().toRequestBody(JSON))
            .build()
        // httpClient, never bufferedHttpClient: an SSE stream is long BY
        // DESIGN, and a whole-call ceiling would fire mid-completion on a
        // request the gateway has already billed.
        val call = httpClient.newCall(request)
        call.enqueue(object : okhttp3.Callback {
            override fun onFailure(call: okhttp3.Call, e: java.io.IOException) {
                close(NRouterError.Transport(e.message ?: "the stream never reached nRouter"))
            }

            override fun onResponse(call: okhttp3.Call, response: okhttp3.Response) {
                val meta = NRouterResponseMeta.fromLookup { name -> response.header(name) }
                if (response.code !in 200..299) {
                    response.use {
                        val parsed = runCatching { JSONObject(it.body?.string().orEmpty()) }
                            .getOrElse { JSONObject() }
                        close(NRouterError.fromCode(errorBody(it.code, parsed, meta)))
                    }
                    return
                }
                val contentType = response.header("content-type").orEmpty().lowercase()
                if (!contentType.contains("text/event-stream")) {
                    response.close()
                    close(
                        NRouterError.Transport(
                            "nRouter returned ${response.code} with content-type '$contentType', " +
                                "which is not an SSE stream."
                        )
                    )
                    return
                }

                launch(Dispatchers.IO) {
                    response.use {
                        val source = it.body?.source()
                        if (source == null) {
                            close(NRouterError.Transport("nRouter returned an empty stream body"))
                            return@use
                        }
                        var event: String? = null
                        val data = mutableListOf<String>()
                        var terminated = false
                        while (true) {
                            val line = source.readUtf8Line() ?: break
                            if (line.isEmpty()) {
                                if (data.isEmpty()) {
                                    event = null
                                    continue
                                }
                                when (val frame = parseStreamFrame(event, data.joinToString("\n"), meta)) {
                                    is ParsedStreamFrame.Chunk -> {
                                        if (!trySend(frame.value).isSuccess) return@use
                                    }
                                    is ParsedStreamFrame.Error -> {
                                        close(frame.value)
                                        return@use
                                    }
                                    ParsedStreamFrame.Done -> {
                                        terminated = true
                                        close()
                                        return@use
                                    }
                                    ParsedStreamFrame.Skip -> Unit
                                }
                                event = null
                                data.clear()
                                continue
                            }
                            if (line.startsWith(":")) continue
                            val name = line.substringBefore(':')
                            val value = line.substringAfter(':', "").removePrefix(" ")
                            when (name) {
                                "event" -> event = value
                                "data" -> data += value
                            }
                        }
                        if (!terminated && data.isNotEmpty()) {
                            when (val frame = parseStreamFrame(event, data.joinToString("\n"), meta)) {
                                is ParsedStreamFrame.Chunk -> {
                                    trySend(frame.value)
                                }
                                is ParsedStreamFrame.Error -> {
                                    close(frame.value)
                                    return@use
                                }
                                ParsedStreamFrame.Done -> {
                                    terminated = true
                                    close()
                                    return@use
                                }
                                ParsedStreamFrame.Skip -> Unit
                            }
                        }
                        if (terminated) {
                            close()
                        } else {
                            close(NRouterError.Transport("the stream ended before its terminal event"))
                        }
                    }
                }
            }
        })
        awaitClose { call.cancel() }
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
            builder.post(encodeJson(body).toRequestBody(JSON)).build()
        }

        // httpClient, never bufferedHttpClient: generated audio and a rendered
        // video are large and slow by nature, and already paid for.
        return runCall(httpClient, request) {
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
        client: OkHttpClient,
        request: Request,
        read: (okhttp3.Response) -> T,
    ): T {
        val reqBuilder = request.newBuilder()
            .header("Authorization", "Bearer $apiKey")
            .header("x-nr-client-language", "kotlin")
        if (!clientPlatform.isNullOrEmpty()) {
            reqBuilder.header("x-nr-client-platform", clientPlatform)
        }
        if (!traceId.isNullOrEmpty()) {
            reqBuilder.header("x-nr-trace-id", traceId)
        }
        if (!sessionId.isNullOrEmpty()) {
            reqBuilder.header("x-nr-session-id", sessionId)
        }
        val authed = reqBuilder.build()

        return suspendCancellableCoroutine { continuation ->
            val call = client.newCall(authed)
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
                        // A read that dies MID-BODY — a reset socket, or the
                        // buffered ceiling firing — surfaces as a raw
                        // IOException. Unwrapped it escapes this SDK's error
                        // contract: a caller matching on NRouterError gets a
                        // java.io exception instead, for a request that may
                        // already have been billed. `read` raises NRouterError
                        // deliberately (a non-JSON 2xx, a typed gateway
                        // failure); those pass straight through.
                        continuation.resumeWithException(
                            if (e is java.io.IOException) {
                                NRouterError.Transport(
                                    e.message ?: "the response body could not be read"
                                )
                            } else {
                                e
                            }
                        )
                    }
                }
            })
        }
    }

    private suspend fun send(request: Request): Response = runCall(bufferedHttpClient, request) {
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

        /** Extracts trace routing headers from response metadata. */
        @JvmStatic
        public fun extractTraceHeaders(meta: NRouterResponseMeta?): Map<String, String> =
            ai.nrouter.sdk.extractTraceHeaders(meta)

        /** Extracts trace routing headers from a headers map. */
        @JvmStatic
        public fun extractTraceHeaders(headers: Map<String, String>?): Map<String, String> =
            ai.nrouter.sdk.extractTraceHeaders(headers)

        /** Injects trace and session context into an existing headers map. */
        @JvmStatic
        public fun withTraceContext(headers: Map<String, String>?, traceId: String?, sessionId: String?): Map<String, String> =
            ai.nrouter.sdk.withTraceContext(headers, traceId, sessionId)

        /** True when a model family is served on /v1/messages rather than /v1/chat/completions. */
        @JvmStatic
        @JvmOverloads
        public fun usesMessagesWire(model: String, provider: String? = null): Boolean {
            val m = model.lowercase()
            if (m.contains("claude") || m.contains("anthropic") || m.contains("haiku") || m.contains("sonnet") || m.contains("opus")) {
                return true
            }
            if (provider?.lowercase()?.contains("anthropic") == true) {
                return true
            }
            return false
        }

        /**
         * Normalizes an Anthropic Messages request payload:
         * - Extracts system/developer turns from `messages` into top-level `system`
         * - Maps `max_completion_tokens` to `max_tokens` (with fallback to 4096)
         * - Normalizes `stop` to `stop_sequences` array
         */
        @JvmStatic
        public fun normalizeAnthropicMessages(body: JSONObject): JSONObject {
            val out = normalizedObject(body)
            if (out.has("messages")) {
                val rawMessages = out.optJSONArray("messages")
                if (rawMessages != null) {
                    val cleaned = JSONArray()
                    val systemChunks = mutableListOf<String>()

                    val existingSys = out.optString("system", "")
                    if (existingSys.isNotEmpty()) {
                        systemChunks.add(existingSys)
                    }

                    for (i in 0 until rawMessages.length()) {
                        val turn = rawMessages.optJSONObject(i)
                        if (turn != null) {
                            val role = turn.optString("role", "").lowercase()
                            if (role == "system" || role == "developer") {
                                val content = turn.opt("content")
                                if (content is String && content.isNotEmpty()) {
                                    systemChunks.add(content)
                                } else if (content is JSONArray) {
                                    for (j in 0 until content.length()) {
                                        val part = content.optJSONObject(j)
                                        if (part != null && part.optString("type") == "text") {
                                            val txt = part.optString("text", "")
                                            if (txt.isNotEmpty()) {
                                                systemChunks.add(txt)
                                            }
                                        }
                                    }
                                }
                                continue
                            }
                            cleaned.put(turn)
                        } else {
                            cleaned.put(rawMessages.get(i))
                        }
                    }

                    out.put("messages", cleaned)
                    if (systemChunks.isNotEmpty()) {
                        out.put("system", systemChunks.joinToString("\n\n"))
                    }
                }
            }

            if (out.has("max_completion_tokens")) {
                val maxComp = out.remove("max_completion_tokens")
                if (!out.has("max_tokens")) {
                    out.put("max_tokens", maxComp)
                }
            }
            if (!out.has("max_tokens")) {
                out.put("max_tokens", 4096)
            }

            if (out.has("stop")) {
                val stopVal = out.remove("stop")
                if (!out.has("stop_sequences")) {
                    if (stopVal is String && stopVal.isNotEmpty()) {
                        out.put("stop_sequences", JSONArray().put(stopVal))
                    } else if (stopVal is JSONArray) {
                        val valid = JSONArray()
                        for (i in 0 until stopVal.length()) {
                            val s = stopVal.optString(i, "")
                            if (s.isNotEmpty()) valid.put(s)
                        }
                        if (valid.length() > 0) {
                            out.put("stop_sequences", valid)
                        }
                    }
                }
            }

            return out
        }

        /**
         * TCP and TLS handshake with the gateway.
         *
         * The gateway allows itself 10s to connect to a PROVIDER; reaching our
         * own edge is cheaper, so 15s is headroom for a bad mobile or corporate
         * network while staying finite.
         */
        public const val CONNECT_TIMEOUT_MILLIS: Long = 15_000

        /**
         * Gap between bytes, on EVERY path — and the reason OkHttp needs no
         * whole-call ceiling to cut a dead peer. It bounds time-to-headers and
         * the pause between two reads, never the total, so it cuts a server
         * that went silent without ever cutting a completion that is merely
         * long.
         *
         * OkHttp's default is 10s. That is far below a normal LLM completion
         * and far below an image, a video or a TTS response, so the client was
         * aborting requests the gateway completes, settles and BILLS —
         * indistinguishable from us being broken, and it costs the customer
         * money. 120s matches the gateway's own between-bytes budget toward a
         * provider.
         */
        public const val READ_TIMEOUT_MILLIS: Long = 120_000

        /** How long a request BODY may take to push — an audio file for transcription. */
        public const val WRITE_TIMEOUT_MILLIS: Long = 60_000

        /**
         * Whole-call ceiling for BUFFERED JSON requests only. 0 means unbounded.
         *
         * Sized against the gateway's worst honest case rather than a
         * comfortable average: up to three provider attempts, up to 20s of
         * cumulative backoff between them, a 120s between-bytes budget on each.
         * Ten minutes sits comfortably above that and comfortably below
         * infinity. Erring high is deliberate — a client that gives up early
         * aborts a billed call and the customer pays for nothing.
         */
        public const val BUFFERED_CALL_TIMEOUT_MILLIS: Long = 600_000

        /**
         * The transport this SDK builds when the caller injects none.
         *
         * `OkHttpClient()` was the defect being fixed: its defaults are a 10s
         * read timeout, which cuts ordinary completions.
         *
         * `retryOnConnectionFailure(false)` is not a detail. OkHttp will
         * otherwise re-send a request that failed after it was written, which
         * for a billed POST is a SECOND CALL AND A SECOND BILL with nothing to
         * deduplicate on. The gateway reserves credit once per customer request
         * and owns retry and failover across providers; this SDK adds no retry
         * loop of its own.
         *
         * `java.time.Duration` overloads are avoided on purpose: they need API
         * 26 on Android, and the Android SDK's floor is API 21.
         */
        @JvmStatic
        public fun defaultHttpClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(CONNECT_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS)
            .readTimeout(READ_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS)
            .writeTimeout(WRITE_TIMEOUT_MILLIS, TimeUnit.MILLISECONDS)
            .callTimeout(0, TimeUnit.MILLISECONDS)
            .retryOnConnectionFailure(false)
            .build()

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
                param = node.optString("param").ifEmpty { null },
                type = node.optString("type").ifEmpty { null },
                status = status,
                requestId = meta.requestId,
                limitSource = meta.limitSource,
                authReason = meta.authReason,
            )
        }
    }
}

private sealed interface ParsedStreamFrame {
    data class Chunk(val value: NRouter.StreamChunk) : ParsedStreamFrame
    data class Error(val value: NRouterError) : ParsedStreamFrame
    data object Done : ParsedStreamFrame
    data object Skip : ParsedStreamFrame
}

private fun parseStreamFrame(
    event: String?,
    data: String,
    meta: NRouterResponseMeta,
): ParsedStreamFrame {
    val trimmed = data.trim()
    if (trimmed.isEmpty()) return ParsedStreamFrame.Skip
    if (trimmed == "[DONE]") return ParsedStreamFrame.Done
    val raw = runCatching { JSONObject(trimmed) }.getOrElse {
        return if (event == "error") {
            val code = trimmed.takeIf(::isKnownStreamErrorCode)
            ParsedStreamFrame.Error(
                NRouterError.fromCode(
                    NRouterErrorBody(
                        message = trimmed,
                        code = code,
                        status = 200,
                        requestId = meta.requestId,
                        limitSource = meta.limitSource,
                        authReason = meta.authReason,
                    )
                )
            )
        } else {
            ParsedStreamFrame.Skip
        }
    }
    if (event == "error" || raw.has("error")) {
        val node = raw.optJSONObject("error") ?: raw
        val type = node.optString("code").ifEmpty {
            node.optString("type").takeIf(::isKnownStreamErrorCode).orEmpty()
        }
        val body = NRouterErrorBody(
            message = node.optString("message").ifEmpty { trimmed },
            code = type.ifEmpty { null },
            param = node.optString("param").ifEmpty { null },
            type = node.optString("type").ifEmpty { null },
            status = 200,
            requestId = meta.requestId,
            limitSource = meta.limitSource,
            authReason = meta.authReason,
        )
        return ParsedStreamFrame.Error(NRouterError.fromCode(body))
    }
    when (raw.optString("type")) {
        "message_stop", "response.completed" -> return ParsedStreamFrame.Done
    }
    return ParsedStreamFrame.Chunk(
        NRouter.StreamChunk(event, streamDelta(raw), raw, meta)
    )
}

private fun streamDelta(raw: JSONObject): String {
    val direct = raw.opt("delta")
    if (direct is String) return direct
    if (direct is JSONObject) return direct.optString("text")
    val choices = raw.optJSONArray("choices") ?: return ""
    if (choices.length() == 0) return ""
    val choice = choices.optJSONObject(0) ?: return ""
    if (choice.opt("text") is String) return choice.optString("text")
    return choice.optJSONObject("delta")?.optString("content").orEmpty()
}

private fun isKnownStreamErrorCode(code: String): Boolean = code in setOf(
    "invalid_request",
    "guardrail_blocked",
    "invalid_api_key",
    "insufficient_credits",
    "model_not_found",
    "rate_limit_exceeded",
    "tpm_limit_exceeded",
    "credit_check_failed",
    "service_unavailable",
)

// Android's platform org.json does not normalize Kotlin collections the same
// way as the JVM artifact: JSONObject.put("messages", listOf(...)) can encode
// `messages` as a string instead of a JSON array. Normalize recursively at the
// transport boundary so the documented idiomatic Kotlin body is portable.
private fun encodeJson(body: JSONObject): String = normalizedObject(body).toString()

private fun normalizedObject(body: JSONObject): JSONObject = JSONObject().also { result ->
    val keys = body.keys()
    while (keys.hasNext()) {
        val key = keys.next()
        result.put(key, normalizedValue(body.opt(key)))
    }
}

private fun normalizedValue(value: Any?): Any? = when {
    value == null || value === JSONObject.NULL -> JSONObject.NULL
    value is JSONObject -> normalizedObject(value)
    value is JSONArray -> JSONArray().also { result ->
        for (index in 0 until value.length()) result.put(normalizedValue(value.opt(index)))
    }
    value is Map<*, *> -> JSONObject().also { result ->
        value.forEach { (key, nested) ->
            if (key !is String) {
                throw NRouterError.Configuration("JSON object keys must be strings.")
            }
            result.put(key, normalizedValue(nested))
        }
    }
    value is Iterable<*> -> JSONArray().also { result ->
        value.forEach { result.put(normalizedValue(it)) }
    }
    value.javaClass.isArray -> JSONArray().also { result ->
        for (index in 0 until java.lang.reflect.Array.getLength(value)) {
            result.put(normalizedValue(java.lang.reflect.Array.get(value, index)))
        }
    }
    else -> value
}
