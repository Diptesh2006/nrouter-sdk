import 'errors.dart';

/// Per-request metadata carried on the `x-nr-*` response headers.
///
/// Every field is nullable on purpose. The gateway omits a header rather than
/// sending a placeholder, and the two omissions that matter most are
/// `x-nr-request-cost` — ABSENT when the model is unpriced, never `0` — and
/// `x-nr-limit-source`, absent when nothing measured a refusal.
class NRouterResponseMeta {
  const NRouterResponseMeta({
    this.requestId,
    this.cost,
    this.costStatus,
    this.model,
    this.inputTokens,
    this.outputTokens,
    this.totalTokens,
    this.cacheReadTokens,
    this.cacheWriteTokens,
    this.limitSource,
    this.budgetWarning,
    this.guardrails,
    this.authReason,
    this.responseCache,
    this.responseCacheAge,
  });

  /// Present on every response; the join key for a spend row or a log line.
  final String? requestId;

  /// Exact USD cost. `null` when unpriced — rendering that as `0` would report
  /// a free request, which no enabled model is.
  final double? cost;

  /// `exact` or `unpriced`.
  final String? costStatus;

  final String? model;
  final int? inputTokens;
  final int? outputTokens;
  final int? totalTokens;
  final int? cacheReadTokens;
  final int? cacheWriteTokens;

  /// On a 429, which limit measured the refusal.
  final String? limitSource;

  /// Set when this request crossed a soft budget you configured; it still
  /// served. `<scope> soft_budget <spend>/<ceiling>`, e.g.
  /// `org soft_budget 80.00/100.00`.
  final String? budgetWarning;

  /// Posture of the PRE-CALL guardrail chain: `none`, `monitor`, `pass`,
  /// `partial` or `blocked`, matched exactly and case-sensitively.
  ///
  /// `null` means the gateway made NO guardrail claim about this response —
  /// never "no guardrail applied", which is the explicit `none`. Posture only
  /// by design: policy name, policy id, detector family, rule count and (for
  /// `partial`) which channel went uninspected are deliberately withheld.
  final String? guardrails;

  /// On a 401, the gateway's stable reason.
  final String? authReason;

  /// `hit` or `miss`; absent when the response cache did not participate.
  final String? responseCache;

  /// Age in seconds of a response-cache hit.
  final int? responseCacheAge;

  /// Every header this SDK reads, exactly as the spec names them.
  static const List<String> headerNames = [
    'x-nr-request-id',
    'x-nr-request-cost',
    'x-nr-cost-status',
    'x-nr-model',
    'x-nr-input-tokens',
    'x-nr-output-tokens',
    'x-nr-total-tokens',
    'x-nr-cache-read-tokens',
    'x-nr-cache-write-tokens',
    'x-nr-limit-source',
    'x-nr-budget-warning',
    'x-nr-guardrails',
    'x-nr-auth-reason',
    'x-nr-response-cache',
    'x-nr-response-cache-age',
  ];

  /// Parse from a header map keyed by lowercase name.
  ///
  /// An unparseable numeric header stays `null` rather than defaulting: a zero
  /// here would be indistinguishable from a real zero.
  factory NRouterResponseMeta.fromHeaders(Map<String, String> headers) {
    String? get(String name) => headers[name];
    int? asInt(String name) => int.tryParse(get(name) ?? '');
    final rawCost = get('x-nr-request-cost');

    return NRouterResponseMeta(
      requestId: get('x-nr-request-id'),
      cost: rawCost == null ? null : double.tryParse(rawCost),
      costStatus: get('x-nr-cost-status'),
      model: get('x-nr-model'),
      inputTokens: asInt('x-nr-input-tokens'),
      outputTokens: asInt('x-nr-output-tokens'),
      totalTokens: asInt('x-nr-total-tokens'),
      cacheReadTokens: asInt('x-nr-cache-read-tokens'),
      cacheWriteTokens: asInt('x-nr-cache-write-tokens'),
      limitSource: get('x-nr-limit-source'),
      budgetWarning: get('x-nr-budget-warning'),
      guardrails: get('x-nr-guardrails'),
      authReason: get('x-nr-auth-reason'),
      responseCache: get('x-nr-response-cache'),
      responseCacheAge: asInt('x-nr-response-cache-age'),
    );
  }

  /// True when the gateway priced this request exactly.
  bool get isPriced => costStatus == 'exact' && cost != null;

  bool get isCacheHit => responseCache == 'hit';
  bool get isCacheMiss => responseCache == 'miss';
  int get cacheAgeSeconds => responseCacheAge ?? 0;

  BudgetWarningInfo? parseBudgetWarning() {
    final raw = budgetWarning?.trim();
    if (raw == null || raw.isEmpty) return null;
    final parts = raw.split(RegExp(r'\s+'));
    if (parts.length != 3 || parts[1] != 'soft_budget') return null;
    final scope = parts[0];
    final amounts = parts[2].split('/');
    if (amounts.length != 2) return null;
    final spend = double.tryParse(amounts[0]);
    final ceiling = double.tryParse(amounts[1]);
    if (spend == null || ceiling == null || spend < 0 || ceiling <= 0 || !spend.isFinite || !ceiling.isFinite) {
      return null;
    }
    return BudgetWarningInfo(scope: scope, spend: spend, ceiling: ceiling);
  }
}

class BudgetWarningInfo {
  final String scope;
  final double spend;
  final double ceiling;

  const BudgetWarningInfo({
    required this.scope,
    required this.spend,
    required this.ceiling,
  });

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is BudgetWarningInfo &&
          runtimeType == other.runtimeType &&
          scope == other.scope &&
          spend == other.spend &&
          ceiling == other.ceiling;

  @override
  int get hashCode => scope.hashCode ^ spend.hashCode ^ ceiling.hashCode;
}

/// Extract trace routing headers (e.g. `x-nr-request-id`) from response metadata.
Map<String, String> extractTraceHeaders(NRouterResponseMeta meta) {
  final out = <String, String>{};
  if (meta.requestId != null && meta.requestId!.isNotEmpty) {
    out['x-nr-request-id'] = meta.requestId!;
  }
  return out;
}

/// Extract trace routing headers from an arbitrary map of HTTP headers.
Map<String, String> extractTraceHeadersFromMap(Map<String, String> headers) {
  final out = <String, String>{};
  for (final entry in headers.entries) {
    final kl = entry.key.toLowerCase();
    if (kl == 'x-nr-request-id' || kl == 'x-nr-trace-id' || kl == 'x-nr-session-id') {
      out[kl] = entry.value;
    }
  }
  return out;
}

/// Inject trace context headers, validating that traceId and sessionId do not contain CRLF characters.
Map<String, String> withTraceContext(
  Map<String, String> headers, {
  String? traceId,
  String? sessionId,
}) {
  if (traceId != null && (traceId.contains('\r') || traceId.contains('\n'))) {
    throw NRouterConfigurationError('traceId must not contain CRLF characters');
  }
  if (sessionId != null && (sessionId.contains('\r') || sessionId.contains('\n'))) {
    throw NRouterConfigurationError('sessionId must not contain CRLF characters');
  }
  final out = <String, String>{};
  for (final entry in headers.entries) {
    if (!entry.value.contains('\r') && !entry.value.contains('\n')) {
      out[entry.key] = entry.value;
    }
  }
  if (traceId != null && traceId.isNotEmpty) {
    out['x-nr-trace-id'] = traceId;
  }
  if (sessionId != null && sessionId.isNotEmpty) {
    out['x-nr-session-id'] = sessionId;
  }
  return out;
}

