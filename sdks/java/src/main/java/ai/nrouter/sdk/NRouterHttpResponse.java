package ai.nrouter.sdk;

import com.fasterxml.jackson.databind.JsonNode;

/** A decoded JSON body paired with nRouter metadata. */
public final class NRouterHttpResponse {
    private final JsonNode body;
    private final NRouterResponseMeta meta;
    private final int statusCode;

    NRouterHttpResponse(JsonNode body, NRouterResponseMeta meta, int statusCode) {
        this.body = body;
        this.meta = meta;
        this.statusCode = statusCode;
    }

    public JsonNode body() { return body; }
    public NRouterResponseMeta meta() { return meta; }
    public int statusCode() { return statusCode; }
}
