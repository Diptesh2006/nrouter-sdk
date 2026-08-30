package ai.nrouter.sdk;

/** Typed gateway refusal for the native Java HTTP surface. */
public final class NRouterException extends RuntimeException {
    public enum Kind {
        REQUEST, GUARDRAIL_BLOCKED, AUTHENTICATION, CREDIT, BUDGET_EXCEEDED,
        NOT_FOUND, RATE_LIMIT, SERVICE, OTHER, TRANSPORT, CONFIGURATION
    }

    private final Kind kind;
    private final String code;
    private final int status;
    private final NRouterResponseMeta meta;

    NRouterException(Kind kind, String message, String code, int status, NRouterResponseMeta meta) {
        super(message);
        this.kind = kind;
        this.code = code;
        this.status = status;
        this.meta = meta;
    }

    static NRouterException gateway(String message, String code, int status, NRouterResponseMeta meta) {
        return new NRouterException(classify(code, message, status), message, code, status, meta);
    }

    static NRouterException transport(String message) {
        return new NRouterException(Kind.TRANSPORT, message, null, 0, null);
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
            case 429: return Kind.RATE_LIMIT;
            case 502:
            case 503:
            case 504: return Kind.SERVICE;
            default: return Kind.OTHER;
        }
    }

    public Kind kind() { return kind; }
    public String code() { return code; }
    public int status() { return status; }
    public NRouterResponseMeta meta() { return meta; }
    public boolean isRetryable() {
        return kind == Kind.RATE_LIMIT || kind == Kind.SERVICE || kind == Kind.TRANSPORT;
    }
}
