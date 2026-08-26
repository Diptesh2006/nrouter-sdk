/// Why the gateway refused a request.
///
/// Subclasses map one-to-one to the `errors` block of
/// `spec/nrouter-sdk-spec.json`. The gateway's stable [NRouterErrorBody.code]
/// decides the type — not the HTTP status, which cannot separate
/// `invalid_request` from `guardrail_blocked` (both 400) nor
/// `rate_limit_exceeded` from `tpm_limit_exceeded` (both 429).
sealed class NRouterError implements Exception {
  const NRouterError(this.message, [this.body]);

  final String message;

  /// The gateway payload, or `null` when the request never reached it.
  final NRouterErrorBody? body;

  /// Build the subclass the gateway's `code` names.
  factory NRouterError.fromCode(NRouterErrorBody body) {
    switch (body.code) {
      case 'invalid_request':
        return NRouterRequestError(body);
      case 'guardrail_blocked':
        return NRouterGuardrailBlockedError(body);
      case 'invalid_api_key':
        return NRouterAuthenticationError(body);
      case 'insufficient_credits':
        return NRouterCreditError(body);
      case 'model_not_found':
        return NRouterNotFoundError(body);
      case 'rate_limit_exceeded':
      case 'tpm_limit_exceeded':
        return NRouterRateLimitError(body);
      case 'credit_check_failed':
      case 'service_unavailable':
        return NRouterServiceError(body);
      case null:
        switch (body.status) {
          case 400:
            return NRouterRequestError(body);
          case 401:
            return NRouterAuthenticationError(body);
          case 402:
            return NRouterCreditError(body);
          case 404:
            return NRouterNotFoundError(body);
          case 429:
            return NRouterRateLimitError(body);
          case 503:
            return NRouterServiceError(body);
          default:
            return NRouterOtherError(body);
        }
      default:
        // An unrecognised code is preserved, never forced into a neighbouring
        // type — guessing here tells a caller to retry something permanent.
        return NRouterOtherError(body);
    }
  }

  /// Whether retrying the identical request could plausibly succeed.
  ///
  /// False for every permanent 4xx: a retry there burns quota and cannot
  /// change the answer.
  bool get isRetryable =>
      this is NRouterRateLimitError ||
      this is NRouterServiceError ||
      this is NRouterTransportError;

  @override
  String toString() {
    final code = body?.code;
    return code != null ? '$message ($code)' : message;
  }
}

String _describe(NRouterErrorBody body) => body.message;

/// `invalid_request` (400) — invalid JSON or request shape.
final class NRouterRequestError extends NRouterError {
  NRouterRequestError(NRouterErrorBody body) : super(_describe(body), body);
}

/// `guardrail_blocked` (400) — a guardrail rule denied the request.
final class NRouterGuardrailBlockedError extends NRouterError {
  NRouterGuardrailBlockedError(NRouterErrorBody body) : super(_describe(body), body);
}

/// `invalid_api_key` (401) — virtual-key authentication refused.
final class NRouterAuthenticationError extends NRouterError {
  NRouterAuthenticationError(NRouterErrorBody body) : super(_describe(body), body);
}

/// `insufficient_credits` (402) — the credit reserve failed.
final class NRouterCreditError extends NRouterError {
  NRouterCreditError(NRouterErrorBody body) : super(_describe(body), body);
}

/// `model_not_found` (404) — alias absent or invisible to this tenant.
final class NRouterNotFoundError extends NRouterError {
  NRouterNotFoundError(NRouterErrorBody body) : super(_describe(body), body);
}

/// `rate_limit_exceeded` / `tpm_limit_exceeded` (429).
final class NRouterRateLimitError extends NRouterError {
  NRouterRateLimitError(NRouterErrorBody body) : super(_describe(body), body);
}

/// `credit_check_failed` / `service_unavailable` (503).
final class NRouterServiceError extends NRouterError {
  NRouterServiceError(NRouterErrorBody body) : super(_describe(body), body);
}

/// A code this SDK version does not know. Deliberately not re-classified.
final class NRouterOtherError extends NRouterError {
  NRouterOtherError(NRouterErrorBody body) : super(_describe(body), body);
}

/// The request never reached the gateway, or the key was refused locally.
final class NRouterTransportError extends NRouterError {
  const NRouterTransportError(super.message);
}

/// The parsed gateway error payload plus the metadata worth acting on.
class NRouterErrorBody {
  const NRouterErrorBody({
    required this.message,
    this.code,
    this.status,
    this.requestId,
    this.limitSource,
    this.authReason,
  });

  final String message;
  final String? code;
  final int? status;
  final String? requestId;

  /// On a 429: which limit measured the refusal. Never guessed — absent means
  /// the gateway did not say, and a guess sends a customer to raise the wrong
  /// limit.
  final String? limitSource;

  /// On a 401: the gateway's stable reason, e.g. `key_route_not_allowed`.
  final String? authReason;
}
