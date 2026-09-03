package ai.nrouter.sdk;

/** Raw response bytes paired with nRouter billing and request metadata. */
public final class NRouterBinaryResponse {
    private final byte[] body;
    private final NRouterResponseMeta meta;
    private final int statusCode;
    private final String contentType;

    NRouterBinaryResponse(byte[] body, NRouterResponseMeta meta, int statusCode, String contentType) {
        this.body = body.clone();
        this.meta = meta;
        this.statusCode = statusCode;
        this.contentType = contentType;
    }

    public byte[] body() { return body.clone(); }
    public NRouterResponseMeta meta() { return meta; }
    public int statusCode() { return statusCode; }
    public String contentType() { return contentType; }
}
