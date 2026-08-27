package ai.nrouter.sdk

/**
 * Why the gateway refused a request.
 *
 * Subclasses map one-to-one to the `errors` block of
 * `spec/nrouter-sdk-spec.json`. The gateway's stable [NRouterErrorBody.code]
 * decides the type — not the HTTP status, which cannot separate
 * `invalid_request` from `guardrail_blocked` (both 400) nor
 * `rate_limit_exceeded` from `tpm_limit_exceeded` (both 429).
 */
public sealed class NRouterError(
    message: String,
    /** The gateway payload, or `null` when the request never reached it. */
    public val body: NRouterErrorBody? = null,
) : Exception(message) {

    /** `invalid_request` (400) — invalid JSON or request shape. */
    public class Request(body: NRouterErrorBody) : NRouterError(body.describe(), body)

    /** `guardrail_blocked` (400) — a guardrail rule denied the request. */
    public class GuardrailBlocked(body: NRouterErrorBody) : NRouterError(body.describe(), body)

    /** `invalid_api_key` (401) — virtual-key authentication refused. */
    public class Authentication(body: NRouterErrorBody) : NRouterError(body.describe(), body)

    /** `insufficient_credits` (402) — the credit reserve failed. */
    public class Credit(body: NRouterErrorBody) : NRouterError(body.describe(), body)

    /** `model_not_found` (404) — alias absent or invisible to this tenant. */
    public class NotFound(body: NRouterErrorBody) : NRouterError(body.describe(), body)

    /** `rate_limit_exceeded` / `tpm_limit_exceeded` (429). */
    public class RateLimit(body: NRouterErrorBody) : NRouterError(body.describe(), body)

    /** `credit_check_failed` / `service_unavailable` (503). */
    public class Service(body: NRouterErrorBody) : NRouterError(body.describe(), body)

    /** A code this SDK version does not know. Deliberately not re-classified. */
    public class Other(body: NRouterErrorBody) : NRouterError(body.describe(), body)

    /**
     * The request left this process and got no answer — DNS, TLS, a dropped
     * connection, a timeout. Retryable.
     */
    public class Transport(message: String) : NRouterError(message)

    /**
     * The SDK refused before sending anything: no key, or a key that is not
     * shaped like an nRouter key.
     *
     * Separate from [Transport] on purpose. Both are raised locally, but this
     * one is PERMANENT — a caller retrying on [isRetryable] would spin forever
     * without ever making a request.
     */
    public class Configuration(message: String) : NRouterError(message)

    /**
     * Whether retrying the identical request could plausibly succeed.
     *
     * False for every permanent 4xx: retrying there burns quota and cannot
     * change the answer.
     */
    public val isRetryable: Boolean
        get() = this is RateLimit || this is Service || this is Transport

    public companion object {
        /**
         * Classify a gateway refusal.
         *
         * Three signals, in order, because no single one is sufficient:
         *
         * 1. **`code`**, when present — the only thing separating
         *    `rate_limit_exceeded` from `tpm_limit_exceeded`. The gateway's WAF
         *    and its upstream passthrough send one.
         * 2. **status**, otherwise. The gateway's main error path emits
         *    `{"error":{"type","message"}}` with **no code at all**, so this is
         *    the ordinary case, not the fallback it looks like.
         * 3. **the message**, to split the two 400s. With no code the message is
         *    the only signal present; calling every 400 a request error makes
         *    [GuardrailBlocked] unreachable and tells a caller to fix a body
         *    that was never the problem.
         */
        @JvmStatic
        public fun fromCode(body: NRouterErrorBody): NRouterError = when (body.code) {
            "invalid_request" -> Request(body)
            "guardrail_blocked" -> GuardrailBlocked(body)
            "invalid_api_key" -> Authentication(body)
            "insufficient_credits" -> Credit(body)
            "model_not_found" -> NotFound(body)
            "rate_limit_exceeded", "tpm_limit_exceeded" -> RateLimit(body)
            "credit_check_failed", "service_unavailable" -> Service(body)
            null -> when (body.status) {
                400 -> if (body.message.contains("guardrail", ignoreCase = true)) {
                    GuardrailBlocked(body)
                } else {
                    Request(body)
                }
                401 -> Authentication(body)
                402 -> Credit(body)
                404 -> NotFound(body)
                429 -> RateLimit(body)
                503 -> Service(body)
                else -> Other(body)
            }
            else -> Other(body)
        }
    }
}

/** The parsed gateway error payload plus the metadata worth acting on. */
public data class NRouterErrorBody(
    val message: String,
    val code: String? = null,
    val status: Int? = null,
    val requestId: String? = null,
    /**
     * On a 429: which limit measured the refusal. Never guessed — absent means
     * the gateway did not say, and a guess sends a customer to raise the wrong
     * limit.
     */
    val limitSource: String? = null,
    /** On a 401: the gateway's stable reason, e.g. `key_route_not_allowed`. */
    val authReason: String? = null,
) {
    internal fun describe(): String = if (code != null) "$message ($code)" else message
}
