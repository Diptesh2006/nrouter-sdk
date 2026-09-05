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

  /// On a 429: duration in whole seconds to wait before retrying.
  int? get retryAfter => body?.retryAfter;

  /// Classify a gateway refusal.
  ///
  /// Three signals, in order, because no single one is sufficient:
  ///
  /// 1. `code`, when present — the only thing separating `rate_limit_exceeded`
  ///    from `tpm_limit_exceeded`. The gateway's WAF and its upstream
  ///    passthrough send one.
  /// 2. status, otherwise. The gateway's main error path emits
  ///    `{"error":{"type","message"}}` with **no code at all**, so this is the
  ///    ordinary case, not the fallback it looks like.
  /// 3. the message, to split the two 400s. With no code the message is the
  ///    only signal present; calling every 400 a request error makes
  ///    [NRouterGuardrailBlockedError] unreachable and tells a caller to fix a
  ///    body that was never the problem.
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
            return body.message.toLowerCase().contains('guardrail')
                ? NRouterGuardrailBlockedError(body)
                : NRouterRequestError(body);
          case 401:
            return NRouterAuthenticationError(body);
          case 402:
            // The gateway's own wording is the only discriminator, and it is
            // stable: GatewayError::{BudgetExceeded, ScopedBudgetExceeded}
            // both start their Display with "budget". Their fix is the
            // OPPOSITE of a shortfall's — raise the budget, not top up.
            return body.message.trimLeft().toLowerCase().startsWith('budget')
                ? NRouterBudgetExceededError(body)
                : NRouterCreditError(body);
          case 404:
            // Scoped to MODELS. A 404 is also a missing video job, an unknown
            // MCP server or an unknown agent run; calling those
            // `model_not_found` is a wrong answer with a confident code.
            return body.message.toLowerCase().contains('model')
                ? NRouterNotFoundError(body)
                : NRouterOtherError(body);
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
      body?.status == 408 ||
      body?.status == 425 ||
      this is NRouterRateLimitError ||
      this is NRouterServiceError ||
      this is NRouterTransportError;

  @override
  String toString() {
    final code = body?.code;
    final raw = code != null ? '$message ($code)' : message;
    return redactKeys(raw);
  }
}

String _describe(NRouterErrorBody body) => body.message;

/// `invalid_request` (400) — invalid JSON or request shape.
final class NRouterRequestError extends NRouterError {
  NRouterRequestError(NRouterErrorBody body) : super(_describe(body), body);
}

/// `guardrail_blocked` (400) — a guardrail rule denied the request.
final class NRouterGuardrailBlockedError extends NRouterError {
  NRouterGuardrailBlockedError(NRouterErrorBody body)
      : super(_describe(body), body);
}

/// `invalid_api_key` (401) — virtual-key authentication refused.
final class NRouterAuthenticationError extends NRouterError {
  NRouterAuthenticationError(NRouterErrorBody body)
      : super(_describe(body), body);
}

/// `insufficient_credits` (402) — the credit reserve failed.
final class NRouterCreditError extends NRouterError {
  NRouterCreditError(NRouterErrorBody body) : super(_describe(body), body);
}

/// A BUDGET ceiling (402), not a shortfall.
///
/// Three conditions share 402 and two are budget ceilings, whose fix is the
/// OPPOSITE of a shortfall's: raise the budget, not top up.
final class NRouterBudgetExceededError extends NRouterError {
  NRouterBudgetExceededError(NRouterErrorBody body)
      : super(_describe(body), body);
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

/// The request left this process and got no answer — DNS, TLS, a dropped
/// connection, a timeout. Retryable.
final class NRouterTransportError extends NRouterError {
  const NRouterTransportError(super.message);
}

/// The SDK refused before sending anything: no key, or a key that is not shaped
/// like an nRouter key.
///
/// Separate from [NRouterTransportError] on purpose. Both are raised locally,
/// but this one is PERMANENT — a caller retrying on [NRouterError.isRetryable]
/// would spin forever without ever making a request.
final class NRouterConfigurationError extends NRouterError {
  const NRouterConfigurationError(super.message);
}

/// The parsed gateway error payload plus the metadata worth acting on.
class NRouterErrorBody {
  const NRouterErrorBody({
    required this.message,
    this.code,
    this.param,
    this.type,
    this.status,
    this.requestId,
    this.limitSource,
    this.authReason,
    this.retryAfter,
  });

  final String message;
  final String? code;
  final String? param;
  final String? type;
  final int? status;
  final String? requestId;

  /// On a 429: which limit measured the refusal. Never guessed — absent means
  /// the gateway did not say, and a guess sends a customer to raise the wrong
  /// limit.
  final String? limitSource;

  /// On a 401: the gateway's stable reason, e.g. `key_route_not_allowed`.
  final String? authReason;

  /// On a 429: duration in whole seconds to wait before retrying.
  final int? retryAfter;
}

final _nrouterKeyRegex = RegExp(r'\bsk-nrouter-[A-Za-z0-9._-]{4,}');
final _genericKeyRegex = RegExp(r'\bsk-[A-Za-z0-9._-]{6,}\b');

/// Redacts nRouter and upstream provider API keys to prevent credential leaks.
String redactKeys(String s) {
  final masked = s.replaceAll(_nrouterKeyRegex, 'sk-nrouter-***');
  return masked.replaceAllMapped(_genericKeyRegex, (m) {
    final token = m.group(0)!;
    if (token.startsWith('sk-nrouter')) return token;
    return 'sk-***';
  });
}

/// Structured gateway error envelope.
class NRouterErrorEnvelope {
  const NRouterErrorEnvelope({
    this.code,
    this.message,
    this.param,
    this.type,
  });

  final String? code;
  final String? message;
  final String? param;
  final String? type;
}

/// Parses a gateway error JSON payload into a structured NRouterErrorEnvelope.
NRouterErrorEnvelope parseGatewayErrorEnvelope(Map<String, dynamic> raw) {
  final nested = raw['error'];
  final node = nested is Map<String, dynamic> ? nested : raw;
  final msg = node['message'] as String? ?? raw['message'] as String?;
  return NRouterErrorEnvelope(
    code: node['code'] as String? ?? raw['code'] as String?,
    message: msg != null ? redactKeys(msg) : null,
    param: node['param'] as String? ?? raw['param'] as String?,
    type: node['type'] as String? ?? raw['type'] as String?,
  );
}

String _toSnakeCase(String s) {
  final sb = StringBuffer();
  for (var i = 0; i < s.length; i++) {
    final c = s[i];
    if (i > 0 && c.toUpperCase() == c && c.toLowerCase() != c) {
      final prev = s[i - 1];
      if (prev.toLowerCase() == prev && prev.toUpperCase() != prev) {
        sb.write('_');
      }
    }
    sb.write(c.toLowerCase());
  }
  return sb.toString();
}

/// Formats an NRouterError into a human-readable, log-safe diagnostic string,
/// masking all API keys.
String formatNRouterError(NRouterError error) {
  final parts = <String>[];
  final rawName = error.runtimeType.toString();
  final kind = rawName.startsWith('NRouter') && rawName.endsWith('Error')
      ? rawName.substring(7, rawName.length - 5)
      : rawName;
  parts.add('[${_toSnakeCase(kind)}]');

  final b = error.body;
  if (b != null) {
    if (b.status != null) parts.add('HTTP ${b.status}');
    if (b.code != null) parts.add('code=${b.code}');
    if (b.param != null) parts.add('param=${b.param}');
    if (b.requestId != null) parts.add('requestId=${b.requestId}');
    if (b.limitSource != null) parts.add('limitSource=${b.limitSource}');
    if (b.retryAfter != null) parts.add('retryAfter=${b.retryAfter}s');
    parts.add(': ${redactKeys(b.message)}');
  } else {
    parts.add(': ${redactKeys(error.message)}');
  }
  return parts.join(' ');
}

/// Max Retry-After ceiling (24 hours).
const int maxRetryAfterSeconds = 86400;

/// Parses an RFC 9110 Retry-After header value (delta-seconds or HTTP-date).
int? parseRetryAfter(String? raw, [DateTime? now]) {
  if (raw == null) return null;
  final trimmed = raw.trim();
  if (trimmed.isEmpty) return null;

  final delta = int.tryParse(trimmed);
  if (delta != null) {
    if (delta < 0) return null;
    return delta > maxRetryAfterSeconds ? maxRetryAfterSeconds : delta;
  }

  final dt = _parseHttpDate(trimmed);
  if (dt != null) {
    final current = now ?? DateTime.now().toUtc();
    final diff = dt.difference(current).inSeconds;
    if (diff <= 0) return 0;
    return diff > maxRetryAfterSeconds ? maxRetryAfterSeconds : diff;
  }
  return null;
}

DateTime? _parseHttpDate(String raw) {
  final parts = raw.split(RegExp(r'\s+'));
  if (parts.length != 6) return null;
  final day = int.tryParse(parts[1]);
  final year = int.tryParse(parts[3]);
  if (day == null || year == null) return null;
  const months = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12
  };
  final month = months[parts[2].toLowerCase()];
  if (month == null) return null;
  final timeParts = parts[4].split(':');
  if (timeParts.length != 3) return null;
  final hour = int.tryParse(timeParts[0]);
  final min = int.tryParse(timeParts[1]);
  final sec = int.tryParse(timeParts[2]);
  if (hour == null || min == null || sec == null) return null;
  return DateTime.utc(year, month, day, hour, min, sec);
}

/// Computes a bounded jittered exponential backoff duration.
Duration computeJitteredBackoff({
  required int attempt,
  Duration baseDelay = const Duration(milliseconds: 500),
  Duration maxDelay = const Duration(seconds: 30),
  int? retryAfterSeconds,
  double jitterFactor = 0.5,
}) {
  final safeAttempt = attempt.clamp(0, 30);
  final safeJitter = jitterFactor.clamp(0.0, 1.0);

  if (retryAfterSeconds != null && retryAfterSeconds > 0) {
    final retryDelay = Duration(seconds: retryAfterSeconds);
    final effectiveDelay = retryDelay > maxDelay ? maxDelay : retryDelay;
    final mult = (1.0 - safeJitter) + (DateTime.now().microsecond % 1000) / 1000.0 * safeJitter;
    return Duration(milliseconds: (effectiveDelay.inMilliseconds * mult).round());
  }

  final exponentialMs = baseDelay.inMilliseconds * (1 << safeAttempt);
  final boundedMs = exponentialMs > maxDelay.inMilliseconds ? maxDelay.inMilliseconds : exponentialMs;
  final mult = (1.0 - safeJitter) + (DateTime.now().microsecond % 1000) / 1000.0 * safeJitter;
  return Duration(milliseconds: (boundedMs * mult).round());
}

