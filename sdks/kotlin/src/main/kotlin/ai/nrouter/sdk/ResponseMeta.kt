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
     * Milliseconds the gateway measured from edge arrival to response headers
     * ready.
     *
     * TIME TO HEADERS, not time to the last byte: on a streamed response the
     * headers are ready before the first token, so this is never a
     * total-generation figure.
     */
    val latencyMs: Long? = null,
    /**
     * The gateway's OpenTelemetry trace id, `null` when no valid trace exists.
     *
     * A caller may SEND `x-nr-trace-id` (and `x-nr-session-id`) to correlate
     * its own spans; the gateway overwrites the response value with its own,
     * so join on this rather than assuming it echoes what was sent.
     */
    val traceId: String? = null,
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
    /**
     * Set when this request crossed a soft budget you configured; it still
     * served. `<scope> soft_budget <spend>/<ceiling>`, e.g.
     * `org soft_budget 80.00/100.00`.
     */
    val budgetWarning: String? = null,
    /**
     * Posture of the PRE-CALL guardrail chain: `none`, `monitor`, `redacted`,
     * `pass`, `partial`, `blocked` or `unavailable`, matched exactly and
     * case-sensitively. `redacted` means an enforcing chain REWROTE part of the
     * prompt before the provider saw it and the request then served; `partial`
     * means only that some content went uninspected, never that anything was
     * rewritten.
     *
     * `null` means the gateway made NO guardrail claim about this response —
     * never "no guardrail applied", which is the explicit `none`. Posture only
     * by design: policy name, policy id, detector family, rule count and (for
     * `partial`) which channel went uninspected are deliberately withheld.
     */
    val guardrails: String? = null,
    /** On a 401, the gateway's stable reason. */
    val authReason: String? = null,
    /** `hit` or `miss`; absent when the response cache did not participate. */
    val responseCache: String? = null,
    /** Age in seconds of a response-cache hit. */
    val responseCacheAge: Long? = null,
    /** Prompt compression outcome: applied, not_requested, off, skipped. */
    val compression: String? = null,
    /** Which chain entry answered: direct or fallback:<n>. */
    val routing: String? = null,
    /** Provider calls made for this request (>= 1). */
    val attempts: Long? = null,
    /** How this response was funded. */
    val fundingSource: String? = null,
    /** When the current usage allowance resets. */
    val allowanceReset: Long? = null,
) {
    /** True when the gateway priced this request exactly. */
    val isPriced: Boolean get() = costStatus == "exact" && cost != null

    /** True when the response was served from the response cache. */
    val isCacheHit: Boolean get() = responseCache == "hit"

    /** True when the response was a cache miss. */
    val isCacheMiss: Boolean get() = responseCache == "miss"

    /** Parses structured budget warning information if present. */
    public fun parseBudgetWarning(): BudgetWarningInfo? {
        val warning = budgetWarning?.trim() ?: return null
        val parts = warning.split(Regex("\\s+"))
        if (parts.size != 3 || parts[1] != "soft_budget") return null
        val amounts = parts[2].split("/")
        if (amounts.size != 2) return null
        val spend = amounts[0].toDoubleOrNull() ?: return null
        val ceiling = amounts[1].toDoubleOrNull() ?: return null
        if (spend < 0.0 || ceiling <= 0.0 || spend.isNaN() || spend.isInfinite() || ceiling.isNaN() || ceiling.isInfinite()) {
            return null
        }
        return BudgetWarningInfo(scope = parts[0], spend = spend, ceiling = ceiling)
    }

    public companion object {
        /** Every header this SDK reads, exactly as the spec names them. */
        @JvmField
        public val HEADER_NAMES: List<String> = listOf(
            "x-nr-request-id",
            "x-nr-latency-ms",
            "x-nr-trace-id",
            "x-nr-request-cost",
            "x-nr-cost-status",
            "x-nr-model",
            "x-nr-input-tokens",
            "x-nr-output-tokens",
            "x-nr-total-tokens",
            "x-nr-cache-read-tokens",
            "x-nr-cache-write-tokens",
            "x-nr-limit-source",
            "x-nr-budget-warning",
            "x-nr-guardrails",
            "x-nr-auth-reason",
            "x-nr-response-cache",
            "x-nr-response-cache-age",
            "x-nr-compression",
            "x-nr-routing",
            "x-nr-attempts",
            "x-nr-funding-source",
            "x-nr-allowance-reset",
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
                // num(), not a raw read: the gateway sends whole milliseconds,
                // so a fractional or garbage value is a mangled header rather
                // than a latency a caller should chart.
                latencyMs = num("x-nr-latency-ms"),
                traceId = lookup("x-nr-trace-id"),
                cost = lookup("x-nr-request-cost")?.toDoubleOrNull(),
                costStatus = lookup("x-nr-cost-status"),
                model = lookup("x-nr-model"),
                inputTokens = num("x-nr-input-tokens"),
                outputTokens = num("x-nr-output-tokens"),
                totalTokens = num("x-nr-total-tokens"),
                cacheReadTokens = num("x-nr-cache-read-tokens"),
                cacheWriteTokens = num("x-nr-cache-write-tokens"),
                limitSource = lookup("x-nr-limit-source"),
                budgetWarning = lookup("x-nr-budget-warning"),
                guardrails = lookup("x-nr-guardrails"),
                authReason = lookup("x-nr-auth-reason"),
                responseCache = lookup("x-nr-response-cache"),
                responseCacheAge = num("x-nr-response-cache-age"),
                compression = lookup("x-nr-compression"),
                routing = lookup("x-nr-routing"),
                attempts = num("x-nr-attempts"),
                fundingSource = lookup("x-nr-funding-source"),
                allowanceReset = num("x-nr-allowance-reset"),
            )
        }
    }
}

/**
 * Structured details parsed from an `x-nr-budget-warning` response header.
 */
public data class BudgetWarningInfo(
    val scope: String,
    val spend: Double,
    val ceiling: Double,
)

/** Extracts trace routing headers from response metadata into a map. */
public fun extractTraceHeaders(meta: NRouterResponseMeta?): Map<String, String> {
    val out = LinkedHashMap<String, String>()
    if (!meta?.requestId.isNullOrEmpty()) {
        out["x-nr-request-id"] = meta!!.requestId!!
    }
    return out
}

/** Extracts trace routing headers from an existing header map. */
public fun extractTraceHeaders(headers: Map<String, String>?): Map<String, String> {
    val out = LinkedHashMap<String, String>()
    if (headers == null) return out
    for ((k, v) in headers) {
        val kl = k.lowercase(java.util.Locale.ROOT)
        if (kl == "x-nr-request-id" || kl == "x-nr-trace-id" || kl == "x-nr-session-id") {
            out[kl] = v
        }
    }
    return out
}

/** Injects trace and session context into an existing headers map, rejecting CRLF characters. */
public fun withTraceContext(headers: Map<String, String>?, traceId: String?, sessionId: String?): Map<String, String> {
    if (traceId != null && (traceId.contains('\r') || traceId.contains('\n'))) {
        throw IllegalArgumentException("traceId must not contain CRLF characters")
    }
    if (sessionId != null && (sessionId.contains('\r') || sessionId.contains('\n'))) {
        throw IllegalArgumentException("sessionId must not contain CRLF characters")
    }
    val out = LinkedHashMap<String, String>()
    if (headers != null) {
        for ((k, v) in headers) {
            if (!v.contains('\r') && !v.contains('\n')) {
                out[k] = v
            }
        }
    }
    if (!traceId.isNullOrEmpty()) {
        out["x-nr-trace-id"] = traceId
    }
    if (!sessionId.isNullOrEmpty()) {
        out["x-nr-session-id"] = sessionId
    }
    return out
}

