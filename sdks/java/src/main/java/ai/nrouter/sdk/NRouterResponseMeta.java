package ai.nrouter.sdk;

import java.net.http.HttpHeaders;
import java.util.List;

/** The fifteen customer-visible x-nr-* response headers. */
public final class NRouterResponseMeta {
    /** Every customer-visible response header this SDK parses. */
    public static final List<String> HEADER_NAMES = List.of(
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
            "x-nr-budget-warning",
            "x-nr-guardrails",
            "x-nr-auth-reason",
            "x-nr-response-cache",
            "x-nr-response-cache-age");

    private final String requestId;
    private final Double cost;
    private final String costStatus;
    private final String model;
    private final Long inputTokens;
    private final Long outputTokens;
    private final Long totalTokens;
    private final Long cacheReadTokens;
    private final Long cacheWriteTokens;
    private final String limitSource;
    private final String budgetWarning;
    private final String guardrails;
    private final String authReason;
    private final String responseCache;
    private final Long responseCacheAge;

    private NRouterResponseMeta(HttpHeaders headers) {
        requestId = value(headers, "x-nr-request-id");
        cost = decimal(headers, "x-nr-request-cost");
        costStatus = value(headers, "x-nr-cost-status");
        model = value(headers, "x-nr-model");
        inputTokens = integer(headers, "x-nr-input-tokens");
        outputTokens = integer(headers, "x-nr-output-tokens");
        totalTokens = integer(headers, "x-nr-total-tokens");
        cacheReadTokens = integer(headers, "x-nr-cache-read-tokens");
        cacheWriteTokens = integer(headers, "x-nr-cache-write-tokens");
        limitSource = value(headers, "x-nr-limit-source");
        budgetWarning = value(headers, "x-nr-budget-warning");
        guardrails = value(headers, "x-nr-guardrails");
        authReason = value(headers, "x-nr-auth-reason");
        responseCache = value(headers, "x-nr-response-cache");
        responseCacheAge = integer(headers, "x-nr-response-cache-age");
    }

    public static NRouterResponseMeta fromHeaders(HttpHeaders headers) {
        return new NRouterResponseMeta(headers);
    }

    private static String value(HttpHeaders headers, String name) {
        return headers.firstValue(name).orElse(null);
    }

    private static Double decimal(HttpHeaders headers, String name) {
        try { return Double.valueOf(value(headers, name)); } catch (RuntimeException ignored) { return null; }
    }

    private static Long integer(HttpHeaders headers, String name) {
        try { return Long.valueOf(value(headers, name)); } catch (RuntimeException ignored) { return null; }
    }

    public String requestId() { return requestId; }
    public Double cost() { return cost; }
    public String costStatus() { return costStatus; }
    public String model() { return model; }
    public Long inputTokens() { return inputTokens; }
    public Long outputTokens() { return outputTokens; }
    public Long totalTokens() { return totalTokens; }
    public Long cacheReadTokens() { return cacheReadTokens; }
    public Long cacheWriteTokens() { return cacheWriteTokens; }
    public String limitSource() { return limitSource; }
    /** Set when this request crossed a soft budget you configured (it still served): {@code <scope> soft_budget <spend>/<ceiling>}. */
    public String budgetWarning() { return budgetWarning; }
    /**
     * Posture of the PRE-CALL guardrail chain: {@code none}, {@code monitor},
     * {@code pass}, {@code partial} or {@code blocked}, matched exactly and
     * case-sensitively.
     *
     * <p>{@code null} means the gateway made NO guardrail claim about this
     * response, never "no guardrail applied" — that is the explicit
     * {@code none}. Posture only by design: policy name, policy id, detector
     * family, rule count and (for {@code partial}) which channel went
     * uninspected are all deliberately withheld.
     */
    public String guardrails() { return guardrails; }
    public String authReason() { return authReason; }
    public String responseCache() { return responseCache; }
    public Long responseCacheAge() { return responseCacheAge; }
    public boolean isPriced() { return cost != null && "exact".equals(costStatus); }
    public boolean isCacheHit() { return "hit".equals(responseCache); }
    public boolean isCacheMiss() { return "miss".equals(responseCache); }
    public long cacheAgeSeconds() { return responseCacheAge != null ? responseCacheAge : 0L; }

    public static final class BudgetWarningInfo {
        private final String scope;
        private final double spend;
        private final double ceiling;

        public BudgetWarningInfo(String scope, double spend, double ceiling) {
            this.scope = scope;
            this.spend = spend;
            this.ceiling = ceiling;
        }

        public String scope() { return scope; }
        public double spend() { return spend; }
        public double ceiling() { return ceiling; }
    }

    public BudgetWarningInfo parseBudgetWarning() {
        if (budgetWarning == null || budgetWarning.trim().isEmpty()) {
            return null;
        }
        String[] parts = budgetWarning.trim().split("\\s+");
        if (parts.length != 3 || !"soft_budget".equals(parts[1])) {
            return null;
        }
        String scope = parts[0];
        String[] amounts = parts[2].split("/");
        if (amounts.length != 2) {
            return null;
        }
        try {
            double spend = Double.parseDouble(amounts[0]);
            double ceiling = Double.parseDouble(amounts[1]);
            if (Double.isNaN(spend) || Double.isInfinite(spend) || spend < 0 ||
                Double.isNaN(ceiling) || Double.isInfinite(ceiling) || ceiling <= 0) {
                return null;
            }
            return new BudgetWarningInfo(scope, spend, ceiling);
        } catch (NumberFormatException e) {
            return null;
        }
    }

    /** Extract trace routing headers from response metadata. */
    public static java.util.Map<String, String> extractTraceHeaders(NRouterResponseMeta meta) {
        java.util.Map<String, String> out = new java.util.LinkedHashMap<>();
        if (meta != null && meta.requestId() != null && !meta.requestId().isEmpty()) {
            out.put("x-nr-request-id", meta.requestId());
        }
        return out;
    }

    /** Extract trace routing headers from a header map. */
    public static java.util.Map<String, String> extractTraceHeaders(java.util.Map<String, String> headers) {
        java.util.Map<String, String> out = new java.util.LinkedHashMap<>();
        if (headers == null) {
            return out;
        }
        for (java.util.Map.Entry<String, String> entry : headers.entrySet()) {
            String kl = entry.getKey().toLowerCase(java.util.Locale.ROOT);
            if ("x-nr-request-id".equals(kl) || "x-nr-trace-id".equals(kl) || "x-nr-session-id".equals(kl)) {
                out.put(kl, entry.getValue());
            }
        }
        return out;
    }

    /** Inject trace context headers, rejecting CRLF characters. */
    public static java.util.Map<String, String> withTraceContext(
            java.util.Map<String, String> headers, String traceId, String sessionId) {
        if (traceId != null && (traceId.contains("\r") || traceId.contains("\n"))) {
            throw new IllegalArgumentException("traceId must not contain CRLF characters");
        }
        if (sessionId != null && (sessionId.contains("\r") || sessionId.contains("\n"))) {
            throw new IllegalArgumentException("sessionId must not contain CRLF characters");
        }
        java.util.Map<String, String> out = new java.util.LinkedHashMap<>();
        if (headers != null) {
            for (java.util.Map.Entry<String, String> entry : headers.entrySet()) {
                if (!entry.getValue().contains("\r") && !entry.getValue().contains("\n")) {
                    out.put(entry.getKey(), entry.getValue());
                }
            }
        }
        if (traceId != null && !traceId.isEmpty()) {
            out.put("x-nr-trace-id", traceId);
        }
        if (sessionId != null && !sessionId.isEmpty()) {
            out.put("x-nr-session-id", sessionId);
        }
        return out;
    }
}

