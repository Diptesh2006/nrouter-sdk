package ai.nrouter.sdk;

import java.util.stream.Stream;

/**
 * Incremental SSE lines, including blank event boundaries, paired with response metadata.
 * Consume fully or use try-with-resources so an abandoned response releases its connection.
 */
public final class NRouterStreamResponse implements AutoCloseable {
    private final Stream<String> lines;
    private final NRouterResponseMeta meta;
    private final int statusCode;

    NRouterStreamResponse(Stream<String> lines, NRouterResponseMeta meta, int statusCode) {
        this.lines = lines;
        this.meta = meta;
        this.statusCode = statusCode;
    }

    /** The one-shot body stream. Closing this response closes the stream. */
    public Stream<String> lines() { return lines; }
    public NRouterResponseMeta meta() { return meta; }
    public int statusCode() { return statusCode; }

    @Override
    public void close() {
        lines.close();
    }
}
