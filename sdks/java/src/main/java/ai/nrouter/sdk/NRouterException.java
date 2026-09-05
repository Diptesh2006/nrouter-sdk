package ai.nrouter.sdk;

/** Typed gateway refusal for the native Java HTTP surface. */
public final class NRouterException extends RuntimeException {
    public enum Kind {
        REQUEST, GUARDRAIL_BLOCKED, AUTHENTICATION, CREDIT, BUDGET_EXCEEDED,
        NOT_FOUND, RATE_LIMIT, SERVICE, OTHER, TRANSPORT, CONFIGURATION
    }

    private final Kind kind;
    private final String code;
    private final String param;
    private final String type;
    private final int status;
    private final NRouterResponseMeta meta;
    private final Long retryAfter;

    NRouterException(Kind kind, String message, String code, int status, NRouterResponseMeta meta) {
        this(kind, message, code, null, null, status, meta, null);
    }

    NRouterException(Kind kind, String message, String code, int status, NRouterResponseMeta meta, Long retryAfter) {
        this(kind, message, code, null, null, status, meta, retryAfter);
    }

    NRouterException(Kind kind, String message, String code, String param, String type, int status, NRouterResponseMeta meta, Long retryAfter) {
        super(redactKeys(message));
        this.kind = kind;
        this.code = code;
        this.param = param;
        this.type = type;
        this.status = status;
        this.meta = meta;
        this.retryAfter = retryAfter;
    }

    static NRouterException gateway(String message, String code, int status, NRouterResponseMeta meta) {
        return gateway(message, code, null, null, status, meta, null);
    }

    static NRouterException gateway(String message, String code, int status, NRouterResponseMeta meta, Long retryAfter) {
        return gateway(message, code, null, null, status, meta, retryAfter);
    }

    static NRouterException gateway(String message, String code, String param, String type, int status, NRouterResponseMeta meta, Long retryAfter) {
        return new NRouterException(classify(code, message, status), message, code, param, type, status, meta, retryAfter);
    }

    static NRouterException transport(String message) {
        return new NRouterException(Kind.TRANSPORT, message, null, null, null, 0, null, null);
    }

    static NRouterException transport(String message, int status, NRouterResponseMeta meta) {
        return new NRouterException(Kind.TRANSPORT, message, null, null, null, status, meta, null);
    }

    static NRouterException configuration(String message) {
        return new NRouterException(Kind.CONFIGURATION, message, "configuration_error", null, null, 400, null, null);
    }

    private static Kind classify(String code, String message, int status) {
        if (code != null) {
            switch (code) {
                case "invalid_request": return Kind.REQUEST;
                case "guardrail_blocked": return Kind.GUARDRAIL_BLOCKED;
                case "invalid_api_key": return Kind.AUTHENTICATION;
                case "insufficient_credits": return Kind.CREDIT;
                case "model_not_found": return Kind.NOT_FOUND;
                case "rate_limit_exceeded":
                case "tpm_limit_exceeded": return Kind.RATE_LIMIT;
                case "credit_check_failed":
                case "service_unavailable": return Kind.SERVICE;
                default: return Kind.OTHER;
            }
        }
        String lower = message == null ? "" : message.trim().toLowerCase(java.util.Locale.ROOT);
        switch (status) {
            case 400: return lower.contains("guardrail") ? Kind.GUARDRAIL_BLOCKED : Kind.REQUEST;
            case 401: return Kind.AUTHENTICATION;
            case 402: return lower.startsWith("budget") ? Kind.BUDGET_EXCEEDED : Kind.CREDIT;
            case 404: return lower.contains("model") ? Kind.NOT_FOUND : Kind.OTHER;
            case 408: return Kind.TRANSPORT;
            case 425: return Kind.SERVICE;
            case 429: return Kind.RATE_LIMIT;
            case 502:
            case 503:
            case 504: return Kind.SERVICE;
            default: return Kind.OTHER;
        }
    }

    public Kind kind() { return kind; }
    public String code() { return code; }
    public String param() { return param; }
    public String type() { return type; }
    public int status() { return status; }
    public NRouterResponseMeta meta() { return meta; }
    public java.util.Optional<Long> retryAfter() { return java.util.Optional.ofNullable(retryAfter); }
    public boolean isRetryable() {
        if (status == 408 || status == 425) {
            return true;
        }
        return kind == Kind.RATE_LIMIT || kind == Kind.SERVICE || kind == Kind.TRANSPORT;
    }

    public static final long MAX_RETRY_AFTER_SECONDS = 86400L;

    public static Long parseRetryAfter(String raw) {
        return parseRetryAfter(raw, java.time.Instant.now());
    }

    public static Long parseRetryAfter(String raw, java.time.Instant now) {
        if (raw == null) return null;
        String trimmed = raw.trim();
        if (trimmed.isEmpty()) return null;

        try {
            long delta = Long.parseLong(trimmed);
            if (delta < 0) return null;
            return Math.min(delta, MAX_RETRY_AFTER_SECONDS);
        } catch (NumberFormatException ignored) {}

        try {
            java.time.format.DateTimeFormatter formatter = java.time.format.DateTimeFormatter.RFC_1123_DATE_TIME;
            java.time.ZonedDateTime parsed = java.time.ZonedDateTime.parse(trimmed, formatter);
            long diff = parsed.toEpochSecond() - now.getEpochSecond();
            if (diff <= 0) return 0L;
            return Math.min(diff, MAX_RETRY_AFTER_SECONDS);
        } catch (Exception ignored) {
            return null;
        }
    }

    public static java.time.Duration computeJitteredBackoff(int attempt, java.time.Duration baseDelay, java.time.Duration maxDelay, Long retryAfterSeconds) {
        int safeAttempt = Math.max(0, Math.min(attempt, 30));
        if (baseDelay == null || baseDelay.isNegative() || baseDelay.isZero()) {
            baseDelay = java.time.Duration.ofMillis(500);
        }
        if (maxDelay == null || maxDelay.isNegative() || maxDelay.isZero()) {
            maxDelay = java.time.Duration.ofSeconds(30);
        }
        if (retryAfterSeconds != null && retryAfterSeconds > 0) {
            java.time.Duration retryDur = java.time.Duration.ofSeconds(retryAfterSeconds);
            if (retryDur.compareTo(maxDelay) > 0) {
                retryDur = maxDelay;
            }
            double factor = 0.5 + 0.5 * Math.random();
            return java.time.Duration.ofMillis((long) (retryDur.toMillis() * factor));
        }
        long exp = 1L << safeAttempt;
        long rawMs = baseDelay.toMillis() * exp;
        long cappedMs = Math.min(rawMs, maxDelay.toMillis());
        double factor = 0.5 + 0.5 * Math.random();
        return java.time.Duration.ofMillis((long) (cappedMs * factor));
    }

    private static final java.util.regex.Pattern NROUTER_KEY_PATTERN =
            java.util.regex.Pattern.compile("\\bsk-nrouter-[A-Za-z0-9._-]{4,}");
    private static final java.util.regex.Pattern GENERIC_KEY_PATTERN =
            java.util.regex.Pattern.compile("\\bsk-[A-Za-z0-9._-]{6,}\\b");

    public static String redactKeys(String input) {
        if (input == null) return null;
        String masked = NROUTER_KEY_PATTERN.matcher(input).replaceAll("sk-nrouter-***");
        java.util.regex.Matcher m = GENERIC_KEY_PATTERN.matcher(masked);
        StringBuilder sb = new StringBuilder();
        while (m.find()) {
            String token = m.group();
            if (token.startsWith("sk-nrouter")) {
                m.appendReplacement(sb, java.util.regex.Matcher.quoteReplacement(token));
            } else {
                m.appendReplacement(sb, "sk-***");
            }
        }
        m.appendTail(sb);
        return sb.toString();
    }

    public static String formatError(NRouterException e) {
        if (e == null) return "";
        StringBuilder sb = new StringBuilder();
        sb.append("[").append(e.kind() != null ? e.kind().name().toLowerCase(java.util.Locale.ROOT) : "unknown").append("]");
        if (e.status() > 0) {
            sb.append(" HTTP ").append(e.status());
        }
        if (e.code() != null && !e.code().isBlank()) {
            sb.append(" code=").append(e.code());
        }
        if (e.param() != null && !e.param().isBlank()) {
            sb.append(" param=").append(e.param());
        }
        if (e.type() != null && !e.type().isBlank()) {
            sb.append(" type=").append(e.type());
        }
        if (e.meta() != null && e.meta().requestId() != null && !e.meta().requestId().isBlank()) {
            sb.append(" req_id=").append(e.meta().requestId());
        }
        String msg = e.getMessage();
        if (msg != null && !msg.isBlank()) {
            sb.append(" : ").append(redactKeys(msg));
        }
        return sb.toString();
    }

    @Override
    public String toString() {
        return formatError(this);
    }

    public static final class NRouterErrorEnvelope {
        private final String code;
        private final String message;
        private final String param;
        private final String type;

        public NRouterErrorEnvelope(String code, String message, String param, String type) {
            this.code = code;
            this.message = message;
            this.param = param;
            this.type = type;
        }

        public String code() { return code; }
        public String message() { return message; }
        public String param() { return param; }
        public String type() { return type; }
    }

    public static NRouterErrorEnvelope parseGatewayErrorEnvelope(String jsonString) {
        if (jsonString == null || jsonString.isBlank()) {
            return new NRouterErrorEnvelope(null, null, null, null);
        }
        try {
            com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
            com.fasterxml.jackson.databind.JsonNode parsed = mapper.readTree(jsonString);
            com.fasterxml.jackson.databind.JsonNode node = parsed != null && parsed.has("error") ? parsed.get("error") : parsed;
            if (node == null) {
                return new NRouterErrorEnvelope(null, null, null, null);
            }
            String code = node.hasNonNull("code") ? node.get("code").asText() : (parsed.hasNonNull("code") ? parsed.get("code").asText() : null);
            String message = node.hasNonNull("message") ? node.get("message").asText() : (parsed.hasNonNull("message") ? parsed.get("message").asText() : null);
            String param = node.hasNonNull("param") ? node.get("param").asText() : (parsed.hasNonNull("param") ? parsed.get("param").asText() : null);
            String type = node.hasNonNull("type") ? node.get("type").asText() : (parsed.hasNonNull("type") ? parsed.get("type").asText() : null);
            return new NRouterErrorEnvelope(code, redactKeys(message), param, type);
        } catch (Exception ignored) {
            return new NRouterErrorEnvelope(null, redactKeys(jsonString), null, null);
        }
    }
}

