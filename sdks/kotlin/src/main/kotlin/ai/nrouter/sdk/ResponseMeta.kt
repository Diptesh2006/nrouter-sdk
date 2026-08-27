package ai.nrouter.sdk

/**
 * Per-request metadata carried on the `x-nr-*` response headers.
 *
 * Every property is nullable on purpose. The gateway omits a header rather than
 * sending a placeholder, and the two omissions that matter most are
 * `x-nr-request-cost` — ABSENT when the model is unpriced, never `0` — and
 * `x-nr-limit-source`, absent when nothing measured a refusal.
 */
public data class NRouterResponseMeta(
    /** Present on every response; the join key for a spend row or a log line. */
    val requestId: String? = null,
    /**
     * Exact USD cost. `null` when unpriced — rendering that as `0` would report
     * a free request, which no enabled model is.
     */
    val cost: Double? = null,
    /** `exact` or `unpriced`. */
    val costStatus: String? = null,
    val model: String? = null,
    val inputTokens: Long? = null,
    val outputTokens: Long? = null,
    val totalTokens: Long? = null,
    val cacheReadTokens: Long? = null,
    val cacheWriteTokens: Long? = null,
    /** On a 429, which limit measured the refusal. */
    val limitSource: String? = null,
    /** On a 401, the gateway's stable reason. */
    val authReason: String? = null,
    /** `hit` or `miss`; absent when the response cache did not participate. */
    val responseCache: String? = null,
    /** Age in seconds of a response-cache hit. */
    val responseCacheAge: Long? = null,
) {
    /** True when the gateway priced this request exactly. */
    val isPriced: Boolean get() = costStatus == "exact" && cost != null

    public companion object {
        /** Every header this SDK reads, exactly as the spec names them. */
        @JvmField
        public val HEADER_NAMES: List<String> = listOf(
            "x-nr-request-id",
            "x-nr-request-cost",
            "x-nr-cost-status",
            "x-nr-model",
            "x-nr-input-tokens",
            "x-nr-output-tokens",
            "x-nr-total-tokens",
            "x-nr-cache-read-tokens",
            "x-nr-cache-write-tokens",
            "x-nr-limit-source",
            "x-nr-auth-reason",
            "x-nr-response-cache",
            "x-nr-response-cache-age",
        )

        /**
         * Parse from anything that looks a header up by lowercase name.
         *
         * An unparseable numeric header stays `null` rather than defaulting: a
         * zero here would be indistinguishable from a real zero.
         */
        @JvmStatic
        public fun fromLookup(lookup: (String) -> String?): NRouterResponseMeta {
            fun num(name: String): Long? = lookup(name)?.toLongOrNull()
            return NRouterResponseMeta(
                requestId = lookup("x-nr-request-id"),
                cost = lookup("x-nr-request-cost")?.toDoubleOrNull(),
                costStatus = lookup("x-nr-cost-status"),
                model = lookup("x-nr-model"),
                inputTokens = num("x-nr-input-tokens"),
                outputTokens = num("x-nr-output-tokens"),
                totalTokens = num("x-nr-total-tokens"),
                cacheReadTokens = num("x-nr-cache-read-tokens"),
                cacheWriteTokens = num("x-nr-cache-write-tokens"),
                limitSource = lookup("x-nr-limit-source"),
                authReason = lookup("x-nr-auth-reason"),
                responseCache = lookup("x-nr-response-cache"),
                responseCacheAge = num("x-nr-response-cache-age"),
            )
        }
    }
}
