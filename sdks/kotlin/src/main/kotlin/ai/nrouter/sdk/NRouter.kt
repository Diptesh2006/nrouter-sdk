package ai.nrouter.sdk

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
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
 * The suspending calls move to [Dispatchers.IO] themselves, so calling one from
 * a UI coroutine will not block the main thread.
 */
public class NRouter @JvmOverloads constructor(
    apiKey: String? = null,
    baseURL: String = DEFAULT_BASE_URL,
    private val http: OkHttpClient = OkHttpClient(),
) {
    private val apiKey: String = resolveApiKey(apiKey)

    /** The gateway this client talks to, with any trailing slash removed. */
    public val baseURL: String = baseURL.trimEnd('/')

    /** A body paired with the metadata the gateway reported for it. */
    public data class Response(
        val body: JSONObject,
        val meta: NRouterResponseMeta,
        val statusCode: Int,
    )

    /** `POST /chat/completions` */
    public suspend fun chatCompletions(body: JSONObject): Response = post("/chat/completions", body)

    /** `POST /embeddings` */
    public suspend fun embeddings(body: JSONObject): Response = post("/embeddings", body)

    /** `POST /messages` — the Anthropic wire format the gateway also serves. */
    public suspend fun messages(body: JSONObject): Response = post("/messages", body)

    /** `POST /responses` */
    public suspend fun responses(body: JSONObject): Response = post("/responses", body)

    /** `GET /models` — what this key is allowed to route to. */
    public suspend fun models(): Response = get("/models")

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

    private fun url(path: String): String = "$baseURL/${path.trimStart('/')}"

    private suspend fun send(request: Request): Response = withContext(Dispatchers.IO) {
        val authed = request.newBuilder()
            .header("Authorization", "Bearer $apiKey")
            .build()

        val response = try {
            http.newCall(authed).execute()
        } catch (e: Exception) {
            throw NRouterError.Transport(e.message ?: "the request never reached nRouter")
        }

        response.use {
            val status = it.code
            val meta = NRouterResponseMeta.fromLookup { name -> it.header(name) }
            val text = it.body?.string().orEmpty()
            val parsed = runCatching { JSONObject(text) }.getOrElse { JSONObject() }

            if (status in 200..299) {
                Response(parsed, meta, status)
            } else {
                throw NRouterError.fromCode(errorBody(status, parsed, meta))
            }
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
                throw NRouterError.Transport(
                    "No nRouter API key: pass one explicitly or set $ENV_KEY."
                )
            }
            if (!key.startsWith(KEY_PREFIX)) {
                throw NRouterError.Transport(
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
