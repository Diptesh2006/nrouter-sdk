package ai.nrouter.sdk;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.FilterInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.UncheckedIOException;
import java.net.SocketTimeoutException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.Spliterator;
import java.util.Spliterators;
import java.util.UUID;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;
import java.util.regex.Pattern;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import java.util.stream.StreamSupport;

/** Native Java 11 client with full gateway-route, metadata, binary and SSE coverage. */
public final class NRouterHttpClient {
    private static final Set<String> ERROR_CODES = Set.of(
            "invalid_request", "guardrail_blocked", "invalid_api_key", "insufficient_credits",
            "model_not_found", "rate_limit_exceeded", "tpm_limit_exceeded",
            "credit_check_failed", "service_unavailable");
    private static final Pattern KEY = Pattern.compile("sk-nrouter-[A-Za-z0-9._-]+");

    /**
     * How long to wait for the TCP and TLS handshake with the gateway.
     *
     * <p>The gateway allows itself 10s to connect to a PROVIDER; reaching our
     * own edge is cheaper than that, so 15s is generous headroom for a bad
     * mobile or corporate network while still being finite. {@code
     * HttpClient.newHttpClient()} sets none at all, which is how a dead route
     * turns into a caller that never returns.
     */
    public static final Duration DEFAULT_CONNECT_TIMEOUT = Duration.ofSeconds(15);

    /**
     * Whole-exchange ceiling for a BUFFERED request (the JSON and multipart
     * paths). Never applied to SSE or to a binary download — see
     * {@link #buffered(String)}.
     *
     * <p>Sized against the gateway's own worst honest case, not against a
     * comfortable average: it may make up to three provider attempts with up to
     * 20s of cumulative backoff between them, holding a 120s between-bytes read
     * timeout on each. The gateway may spend about 410s reaching the first
     * byte, then permits a healthy stream to run for 900s. Twenty-three minutes
     * covers both phases with 70s of delivery margin while remaining finite.
     *
     * <p>Erring high is deliberate. A client that gives up while the gateway is
     * still completing the call aborts a request that the gateway settles and
     * BILLS: the customer pays for tokens they never receive, and it is
     * indistinguishable from us being broken.
     */
    static final Duration GATEWAY_STREAMING_DEADLINE = Duration.ofSeconds(900);
    static final Duration GATEWAY_MAX_TIME_TO_FIRST_BYTE = Duration.ofSeconds(410);

    /** Seventy seconds beyond the gateway's longest healthy full exchange. */
    public static final Duration DEFAULT_REQUEST_TIMEOUT = Duration.ofMinutes(23);

    /**
     * Gap-between-bytes ceiling. The JDK's {@link HttpClient} has no socket
     * read timeout to apply it to — it offers a connect timeout and a
     * whole-exchange timeout and nothing in between — so this exists for the
     * OkHttp-backed {@code OpenAIClient} that {@code NRouter.create} builds,
     * where it IS expressible. Matches the gateway's own between-bytes budget.
     */
    public static final Duration DEFAULT_READ_TIMEOUT = Duration.ofSeconds(120);

    /**
     * Native-client silence bound between response bytes. Ten seconds above
     * the gateway's 120s provider-read bound lets its structured timeout arrive
     * before this transport backstop races it.
     */
    public static final Duration DEFAULT_BODY_IDLE_TIMEOUT = Duration.ofSeconds(130);

    /** How long a request BODY may take to push — an audio file for transcription. */
    public static final Duration DEFAULT_WRITE_TIMEOUT = Duration.ofSeconds(60);

    private final String apiKey;
    private final String baseUrl;
    private final HttpClient http;
    private final Duration requestTimeout;
    private final Duration bodyIdleTimeout;
    private final ObjectMapper json = new ObjectMapper();

    NRouterHttpClient(String apiKey, String baseUrl) {
        this(apiKey, baseUrl, defaultHttpClient(), DEFAULT_REQUEST_TIMEOUT, DEFAULT_BODY_IDLE_TIMEOUT);
    }

    NRouterHttpClient(String apiKey, String baseUrl, HttpClient http, Duration requestTimeout) {
        this(apiKey, baseUrl, http, requestTimeout, DEFAULT_BODY_IDLE_TIMEOUT);
    }

    NRouterHttpClient(
            String apiKey,
            String baseUrl,
            HttpClient http,
            Duration requestTimeout,
            Duration bodyIdleTimeout) {
        if (http == null) {
            throw new IllegalArgumentException("httpClient must not be null");
        }
        if (requestTimeout == null || requestTimeout.isZero() || requestTimeout.isNegative()) {
            throw new IllegalArgumentException("requestTimeout must be a positive duration");
        }
        if (bodyIdleTimeout == null || bodyIdleTimeout.isZero() || bodyIdleTimeout.isNegative()) {
            throw new IllegalArgumentException("bodyIdleTimeout must be a positive duration");
        }
        this.apiKey = apiKey;
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.http = http;
        this.requestTimeout = requestTimeout;
        this.bodyIdleTimeout = bodyIdleTimeout;
    }

    /**
     * The transport this SDK builds when the caller injects none.
     *
     * <p>There is deliberately NO retry policy here. The gateway reserves credit
     * once per customer request and owns retry and failover across providers; a
     * client-side retry of a billed POST is a second call and a second bill with
     * nothing to deduplicate on. The JDK client does not retry a non-idempotent
     * request by default, and nothing here turns that on.
     */
    public static HttpClient defaultHttpClient() {
        return HttpClient.newBuilder().connectTimeout(DEFAULT_CONNECT_TIMEOUT).build();
    }

    /** The transport in force, so a caller can read the timeouts it actually carries. */
    public HttpClient httpClient() {
        return http;
    }

    /** The whole-exchange ceiling applied to buffered requests, and to nothing else. */
    public Duration requestTimeout() {
        return requestTimeout;
    }

    /** The maximum silence permitted between response body bytes. */
    public Duration bodyIdleTimeout() {
        return bodyIdleTimeout;
    }

    public NRouterHttpResponse chatCompletions(Map<String, ?> body) { return post("/chat/completions", body); }
    public NRouterHttpResponse completions(Map<String, ?> body) { return post("/completions", body); }
    public NRouterHttpResponse embeddings(Map<String, ?> body) { return post("/embeddings", body); }
    public NRouterHttpResponse imagesGenerations(Map<String, ?> body) { return post("/images/generations", body); }
    public NRouterHttpResponse createVideo(Map<String, ?> body) { return post("/videos", body); }
    public NRouterBinaryResponse audioSpeech(Map<String, ?> body) { return postBinary("/audio/speech", body); }
    public NRouterHttpResponse audioTranscriptions(String filename, byte[] file, Map<String, ?> fields) {
        return postMultipart("/audio/transcriptions", filename, file, fields);
    }
    public NRouterHttpResponse models() { return get("/models"); }
    public NRouterHttpResponse model(String modelId) { return get("/models/" + encodeModelId(modelId)); }
    public NRouterHttpResponse messages(Map<String, ?> body) { return post("/messages", body); }
    public NRouterHttpResponse countTokens(Map<String, ?> body) { return post("/messages/count_tokens", body); }
    public NRouterHttpResponse responses(Map<String, ?> body) { return post("/responses", body); }
    public NRouterHttpResponse audioTranslations(String filename, byte[] file, Map<String, ?> fields) {
        return postMultipart("/audio/translations", filename, file, fields);
    }
    public NRouterHttpResponse retrieveVideo(String videoId) { return get("/videos/" + encodeSegment(videoId, "videoId")); }
    public NRouterBinaryResponse downloadVideoContent(String videoId) {
        return getBinary("/videos/" + encodeSegment(videoId, "videoId") + "/content");
    }

    public NRouterStreamResponse chatCompletionsStream(Map<String, ?> body) {
        return postStream("/chat/completions", body);
    }
    public NRouterStreamResponse completionsStream(Map<String, ?> body) {
        return postStream("/completions", body);
    }
    public NRouterStreamResponse messagesStream(Map<String, ?> body) {
        return postStream("/messages", body);
    }
    public NRouterStreamResponse responsesStream(Map<String, ?> body) {
        return postStream("/responses", body);
    }

    /** Send a JSON POST to a custom gateway path. Prefer the named helpers above. */
    public NRouterHttpResponse post(String path, Object body) {
        return sendJson(buffered(path).header("Accept", "application/json")
                .header("Content-Type", "application/json").POST(jsonBody(body)).build());
    }

    private NRouterHttpResponse get(String path) {
        return sendJson(buffered(path).header("Accept", "application/json").GET().build());
    }

    private NRouterBinaryResponse postBinary(String path, Object body) {
        // No whole-exchange ceiling: this is generated audio, and a long one is
        // a healthy one. See buffered(String).
        return sendBinary(request(path).header("Accept", "application/octet-stream")
                .header("Content-Type", "application/json").POST(jsonBody(body)).build());
    }

    private NRouterBinaryResponse getBinary(String path) {
        // No whole-exchange ceiling: a rendered video is large and slow by
        // nature, and the customer has already paid for it. See buffered(String).
        return sendBinary(request(path).header("Accept", "application/octet-stream").GET().build());
    }

    private NRouterHttpResponse postMultipart(
            String path, String filename, byte[] file, Map<String, ?> fields) {
        String boundary = "nrouter-" + UUID.randomUUID();
        byte[] body = multipart(boundary, filename, file, fields);
        HttpRequest request = buffered(path)
                .header("Accept", "application/json")
                .header("Content-Type", "multipart/form-data; boundary=" + boundary)
                .POST(HttpRequest.BodyPublishers.ofByteArray(body))
                .build();
        return sendJson(request);
    }

    private NRouterStreamResponse postStream(String path, Map<String, ?> body) {
        Map<String, Object> streamed = new LinkedHashMap<>();
        if (body != null) {
            streamed.putAll(body);
        }
        // This is the explicitly streaming method: `true` wins over a stale or
        // contradictory value in a caller-reused body map.
        streamed.put("stream", true);
        try {
            // No whole-exchange ceiling: an SSE stream is long BY DESIGN, and
            // the ceiling would fire mid-completion. See buffered(String).
            HttpResponse<InputStream> response = http.send(
                    request(path).header("Accept", "text/event-stream")
                            .header("Content-Type", "application/json").POST(jsonBody(streamed)).build(),
                    HttpResponse.BodyHandlers.ofInputStream());
            BufferedReader reader = new BufferedReader(new InputStreamReader(
                    new IdleTimeoutInputStream(response.body(), bodyIdleTimeout), StandardCharsets.UTF_8));
            Stream<String> lines = reader.lines().onClose(() -> closeQuietly(reader));
            NRouterResponseMeta meta = NRouterResponseMeta.fromHeaders(response.headers());
            if (isSuccess(response.statusCode())) {
                Stream<String> guarded = guardSse(lines, response.statusCode(), meta);
                return new NRouterStreamResponse(guarded, meta, response.statusCode());
            }
            String errorBody;
            try (lines) {
                errorBody = lines.collect(Collectors.joining("\n"));
            } catch (UncheckedIOException error) {
                throw NRouterException.transport(
                        "the streaming error response became idle; the request may have been billed ("
                                + redact(error.getMessage()) + ")",
                        response.statusCode(),
                        meta);
            }
            throw gatewayFailure(errorBody.getBytes(StandardCharsets.UTF_8), response.statusCode(), meta);
        } catch (NRouterException error) {
            throw error;
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw NRouterException.transport("nRouter request interrupted");
        } catch (Exception error) {
            throw NRouterException.transport(redact(error.getMessage()));
        }
    }

    private NRouterHttpResponse sendJson(HttpRequest request) {
        PendingResponse pending = send(request);
        HttpResponse<InputStream> response = pending.response;
        NRouterResponseMeta meta = NRouterResponseMeta.fromHeaders(response.headers());
        byte[] body = readBody(pending, meta);
        if (!isSuccess(response.statusCode())) {
            throw gatewayFailure(body, response.statusCode(), meta);
        }
        try {
            JsonNode parsed = json.readTree(body);
            if (parsed == null) {
                throw new IOException("empty JSON body");
            }
            return new NRouterHttpResponse(parsed, meta, response.statusCode());
        } catch (IOException error) {
            throw NRouterException.transport(
                    "nRouter returned an invalid JSON success; the request may have been billed",
                    response.statusCode(), meta);
        }
    }

    private NRouterBinaryResponse sendBinary(HttpRequest request) {
        PendingResponse pending = send(request);
        HttpResponse<InputStream> response = pending.response;
        NRouterResponseMeta meta = NRouterResponseMeta.fromHeaders(response.headers());
        byte[] body = readBody(pending, meta);
        if (!isSuccess(response.statusCode())) {
            throw gatewayFailure(body, response.statusCode(), meta);
        }
        String contentType = response.headers().firstValue("content-type").orElse(null);
        return new NRouterBinaryResponse(body, meta, response.statusCode(), contentType);
    }

    private PendingResponse send(HttpRequest request) {
        long startedNanos = System.nanoTime();
        try {
            return new PendingResponse(
                    http.send(request, HttpResponse.BodyHandlers.ofInputStream()), startedNanos);
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw NRouterException.transport("nRouter request interrupted");
        } catch (Exception error) {
            throw NRouterException.transport(redact(error.getMessage()));
        }
    }

    private byte[] readBody(PendingResponse pending, NRouterResponseMeta meta) {
        HttpResponse<InputStream> response = pending.response;
        AtomicBoolean wholeTimedOut = new AtomicBoolean();
        ScheduledFuture<?> wholeDeadline = response.request().timeout().map(total -> {
            long elapsed = System.nanoTime() - pending.startedNanos;
            long remaining = Math.max(0L, total.toNanos() - elapsed);
            return BODY_IDLE_TIMER.schedule(() -> {
                wholeTimedOut.set(true);
                closeQuietly(response.body());
            }, remaining, TimeUnit.NANOSECONDS);
        }).orElse(null);
        try (InputStream body = new IdleTimeoutInputStream(response.body(), bodyIdleTimeout)) {
            return body.readAllBytes();
        } catch (IOException error) {
            String reason;
            if (wholeTimedOut.get()) {
                reason = "the buffered response exceeded its whole-request deadline";
            } else if (error instanceof SocketTimeoutException) {
                reason = "the response body became idle";
            } else {
                reason = "the response body could not be read";
            }
            throw NRouterException.transport(
                    reason + "; the request may have been billed ("
                            + redact(error.getMessage()) + ")",
                    response.statusCode(),
                    meta);
        } finally {
            if (wholeDeadline != null) {
                wholeDeadline.cancel(false);
            }
        }
    }

    private static final class PendingResponse {
        final HttpResponse<InputStream> response;
        final long startedNanos;

        PendingResponse(HttpResponse<InputStream> response, long startedNanos) {
            this.response = response;
            this.startedNanos = startedNanos;
        }
    }

    private static void closeQuietly(java.io.Closeable closeable) {
        try {
            closeable.close();
        } catch (IOException ignored) {
            // Closing an already-failed response must not mask its typed error.
        }
    }

    private static final ScheduledExecutorService BODY_IDLE_TIMER =
            Executors.newSingleThreadScheduledExecutor(task -> {
                Thread thread = new Thread(task, "nrouter-java-body-idle");
                thread.setDaemon(true);
                return thread;
            });

    private static final class IdleTimeoutInputStream extends FilterInputStream {
        private final Duration timeout;
        private final AtomicBoolean timedOut = new AtomicBoolean();

        IdleTimeoutInputStream(InputStream source, Duration timeout) {
            super(source);
            this.timeout = timeout;
        }

        @Override
        public int read() throws IOException {
            byte[] one = new byte[1];
            int count = read(one, 0, 1);
            return count < 0 ? -1 : one[0] & 0xff;
        }

        @Override
        public int read(byte[] target, int offset, int length) throws IOException {
            if (timedOut.get()) {
                throw idleError();
            }
            ScheduledFuture<?> deadline = BODY_IDLE_TIMER.schedule(() -> {
                timedOut.set(true);
                closeQuietly(in);
            }, timeout.toNanos(), TimeUnit.NANOSECONDS);
            try {
                int count = in.read(target, offset, length);
                if (timedOut.get()) {
                    throw idleError();
                }
                return count;
            } catch (IOException error) {
                if (timedOut.get()) {
                    SocketTimeoutException timeoutError = idleError();
                    timeoutError.initCause(error);
                    throw timeoutError;
                }
                throw error;
            } finally {
                deadline.cancel(false);
            }
        }

        private SocketTimeoutException idleError() {
            return new SocketTimeoutException(
                    "response body remained idle for " + timeout.toMillis() + "ms");
        }
    }

    private NRouterException gatewayFailure(byte[] body, int status, NRouterResponseMeta meta) {
        // A non-JSON proxy page is untrusted and can contain upstream URLs,
        // internal hostnames or stack traces. Only the gateway JSON envelope is
        // customer-safe enough to surface; status and x-nr metadata still make
        // a generic failure diagnosable.
        String message = "nRouter request failed with HTTP " + status;
        String code = null;
        try {
            JsonNode parsed = json.readTree(body);
            JsonNode node = parsed != null && parsed.has("error") ? parsed.get("error") : parsed;
            if (node != null) {
                message = node.hasNonNull("message") ? node.get("message").asText() : message;
                code = node.hasNonNull("code") ? node.get("code").asText() : null;
                if (code == null && node.hasNonNull("type") && ERROR_CODES.contains(node.get("type").asText())) {
                    code = node.get("type").asText();
                }
            }
        } catch (IOException ignored) {
            // A proxy can return text or HTML. Preserve it, but still type by status.
        }
        if (message == null || message.isBlank()) {
            message = "nRouter request failed";
        }
        return NRouterException.gateway(redact(message), code, status, meta);
    }

    private Stream<String> guardSse(Stream<String> raw, int status, NRouterResponseMeta meta) {
        Iterator<String> input = raw.iterator();
        Spliterator<String> guarded = new Spliterators.AbstractSpliterator<String>(
                Long.MAX_VALUE, Spliterator.ORDERED | Spliterator.NONNULL) {
            private final Deque<String> ready = new ArrayDeque<>();
            private final List<String> event = new ArrayList<>();

            @Override
            public boolean tryAdvance(Consumer<? super String> action) {
                while (ready.isEmpty()) {
                    final boolean hasNext;
                    try {
                        hasNext = input.hasNext();
                        if (hasNext) {
                            String line = input.next();
                            event.add(line);
                            if (!line.isEmpty()) {
                                continue;
                            }
                        }
                    } catch (NRouterException error) {
                        throw error;
                    } catch (RuntimeException error) {
                        throw NRouterException.transport(
                                "the streaming response could not be read; the request may have been billed ("
                                        + redact(error.getMessage()) + ")",
                                status,
                                meta);
                    }

                    if (!event.isEmpty()) {
                        inspectSseEvent(event, status, meta);
                        ready.addAll(event);
                        event.clear();
                    }
                    if (!hasNext && ready.isEmpty()) {
                        return false;
                    }
                }
                action.accept(ready.removeFirst());
                return true;
            }
        };
        return StreamSupport.stream(guarded, false).onClose(raw::close);
    }

    private void inspectSseEvent(List<String> lines, int status, NRouterResponseMeta meta) {
        String payload = lines.stream()
                .filter(line -> line.startsWith("data:"))
                .map(line -> line.substring("data:".length()).stripLeading())
                .collect(Collectors.joining("\n"));
        if (payload.isEmpty() || "[DONE]".equals(payload)) {
            return;
        }
        try {
            JsonNode parsed = json.readTree(payload);
            if (parsed != null && parsed.has("error")) {
                throw gatewayFailure(payload.getBytes(StandardCharsets.UTF_8), status, meta);
            }
        } catch (NRouterException error) {
            throw error;
        } catch (IOException ignored) {
            // Provider delta payloads need not be JSON; only complete error envelopes matter here.
        }
    }

    private HttpRequest.Builder request(String path) {
        return HttpRequest.newBuilder(URI.create(baseUrl + "/" + path.replaceFirst("^/+", "")))
                .header("Authorization", "Bearer " + apiKey);
    }

    /**
     * A request builder for a BUFFERED exchange, bounded by {@link #requestTimeout()}.
     *
     * <p>The streaming and binary-download paths deliberately do NOT get this,
     * and the difference is not an oversight.
     *
     * <p>{@code HttpRequest.timeout} is specified as a bound on receiving THE
     * RESPONSE, and the JDK offers no between-bytes (idle) timeout to use
     * instead. So by its own contract it cannot tell "the server stopped
     * responding" apart from "this response is legitimately long". On a buffered
     * JSON call those are the same thing, and this ceiling is the only thing
     * standing between a stalled peer and a caller that hangs forever. On an SSE
     * stream, a TTS download or a generated video, being long is the NORMAL
     * case, and a ceiling that fires would kill a response the gateway has
     * already completed, settled and BILLED — the customer pays for bytes they
     * never receive.
     *
     * <p>Today's JDK implementation happens to stop the clock once response
     * HEADERS arrive, which would make the ceiling harmless on those paths. That
     * is an implementation detail the javadoc does not promise, and betting a
     * billed stream on it is how a JDK upgrade starts cutting customer
     * completions. Streaming and binary are bounded by connect time and by the
     * caller closing the response, not by a total.
     */
    private HttpRequest.Builder buffered(String path) {
        return request(path).timeout(requestTimeout);
    }

    private HttpRequest.BodyPublisher jsonBody(Object body) {
        try {
            return HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body));
        } catch (IOException error) {
            throw NRouterException.transport("request body is not JSON-serializable");
        }
    }

    private byte[] multipart(String boundary, String filename, byte[] file, Map<String, ?> fields) {
        String safeName = requireFilename(filename);
        byte[] content = file == null ? new byte[0] : file;
        try {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            if (fields != null) {
                for (Map.Entry<String, ?> field : fields.entrySet()) {
                    requireFormName(field.getKey());
                    write(out, "--" + boundary + "\r\n");
                    write(out, "Content-Disposition: form-data; name=\"" + field.getKey() + "\"\r\n\r\n");
                    write(out, String.valueOf(field.getValue()) + "\r\n");
                }
            }
            write(out, "--" + boundary + "\r\n");
            write(out, "Content-Disposition: form-data; name=\"file\"; filename=\"" + safeName + "\"\r\n");
            write(out, "Content-Type: application/octet-stream\r\n\r\n");
            out.write(content);
            write(out, "\r\n--" + boundary + "--\r\n");
            return out.toByteArray();
        } catch (IOException impossible) {
            throw new IllegalStateException(impossible);
        }
    }

    private static void write(ByteArrayOutputStream out, String value) throws IOException {
        out.write(value.getBytes(StandardCharsets.UTF_8));
    }

    private static String requireFilename(String filename) {
        if (filename == null || filename.isBlank()) {
            throw new IllegalArgumentException("filename must not be empty");
        }
        if (filename.indexOf('\r') >= 0 || filename.indexOf('\n') >= 0) {
            throw new IllegalArgumentException("filename must not contain CR or LF");
        }
        return filename.replace("\\", "_").replace("\"", "%22");
    }

    private static void requireFormName(String name) {
        if (name == null || name.isBlank() || name.indexOf('\r') >= 0 || name.indexOf('\n') >= 0
                || name.indexOf('\"') >= 0) {
            throw new IllegalArgumentException("multipart field names must be non-empty header-safe strings");
        }
    }

    private static String encodeModelId(String modelId) {
        if (modelId == null || modelId.isBlank()) {
            throw new IllegalArgumentException("modelId must not be empty");
        }
        return Stream.of(modelId.split("/", -1))
                .map(part -> encodeSegment(part, "modelId"))
                .collect(Collectors.joining("/"));
    }

    private static String encodeSegment(String value, String label) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(label + " must not be empty");
        }
        if (".".equals(value) || "..".equals(value)) {
            throw new IllegalArgumentException(label + " must not contain dot-path segments");
        }
        return URLEncoder.encode(value, StandardCharsets.UTF_8).replace("+", "%20");
    }

    private static boolean isSuccess(int status) {
        return status >= 200 && status < 300;
    }

    private static String redact(String value) {
        return value == null ? "nRouter transport failed" : KEY.matcher(value).replaceAll("sk-nrouter-...[REDACTED]");
    }
}
