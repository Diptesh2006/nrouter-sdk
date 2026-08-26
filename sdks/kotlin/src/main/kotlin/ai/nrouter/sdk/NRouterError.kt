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

    /** The request never reached the gateway, or the key was refused locally. */
    public class Transport(message: String) : NRouterError(message)

    /**
     * Whether retrying the identical request could plausibly succeed.
     *
     * False for every permanent 4xx: retrying there burns quota and cannot
     * change the answer.
     */
    public val isRetryable: Boolean
        get() = this is RateLimit || this is Service || this is Transport

    public companion object {
        /** Build the subclass the gateway's `code` names. */
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
                400 -> Request(body)
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
