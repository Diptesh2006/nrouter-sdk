package ai.nrouter.sdk;

import static org.junit.jupiter.api.Assertions.*;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.Authenticator;
import java.net.CookieHandler;
import java.net.InetSocketAddress;
import java.net.ProxySelector;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.WebSocket;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.Executor;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import org.junit.jupiter.api.Test;

class NRouterHttpClientTest {
    private static final class SeenRequest {
        final String method;
        final String path;
        final String authorization;
        final String accept;
        final String contentType;
        final byte[] body;

        SeenRequest(String method, String path, String authorization, String accept, String contentType, byte[] body) {
            this.method = method;
            this.path = path;
            this.authorization = authorization;
            this.accept = accept;
            this.contentType = contentType;
            this.body = body;
        }
    }

    /**
     * Delegates to a real client while recording the {@link HttpRequest} it was
     * handed.
     *
     * <p>This exists because the behavioural tests below cannot decide the
     * question on their own: today's JDK stops the per-request timer once
     * response HEADERS arrive, so a slow BODY survives whether or not the SDK
     * set a timeout, and a behavioural assertion stays green under the mutation
     * it is supposed to catch. What the SDK actually promises is a property of
     * the request it builds, so assert that directly.
     */
    private static final class RecordingHttpClient extends HttpClient {
        private final HttpClient delegate;
        final List<HttpRequest> sent = new CopyOnWriteArrayList<>();

        RecordingHttpClient(HttpClient delegate) {
            this.delegate = delegate;
        }

        @Override
        public <T> HttpResponse<T> send(HttpRequest request, HttpResponse.BodyHandler<T> handler)
                throws IOException, InterruptedException {
            sent.add(request);
            return delegate.send(request, handler);
        }

        @Override
        public <T> CompletableFuture<HttpResponse<T>> sendAsync(
                HttpRequest request, HttpResponse.BodyHandler<T> handler) {
            sent.add(request);
            return delegate.sendAsync(request, handler);
        }

        @Override
        public <T> CompletableFuture<HttpResponse<T>> sendAsync(
                HttpRequest request,
                HttpResponse.BodyHandler<T> handler,
                HttpResponse.PushPromiseHandler<T> pushPromiseHandler) {
            sent.add(request);
            return delegate.sendAsync(request, handler, pushPromiseHandler);
        }

        @Override public Optional<CookieHandler> cookieHandler() { return delegate.cookieHandler(); }
        @Override public Optional<Duration> connectTimeout() { return delegate.connectTimeout(); }
        @Override public Redirect followRedirects() { return delegate.followRedirects(); }
        @Override public Optional<ProxySelector> proxy() { return delegate.proxy(); }
        @Override public SSLContext sslContext() { return delegate.sslContext(); }
        @Override public SSLParameters sslParameters() { return delegate.sslParameters(); }
        @Override public Optional<Authenticator> authenticator() { return delegate.authenticator(); }
        @Override public Version version() { return delegate.version(); }
        @Override public Optional<Executor> executor() { return delegate.executor(); }
        @Override public WebSocket.Builder newWebSocketBuilder() { return delegate.newWebSocketBuilder(); }
    }

    @Test
    void publishesTheCompleteResponseHeaderContract() {
        assertEquals(15, NRouterResponseMeta.HEADER_NAMES.size());
        assertEquals(15, NRouterResponseMeta.HEADER_NAMES.stream().distinct().count());
        assertTrue(NRouterResponseMeta.HEADER_NAMES.contains("x-nr-budget-warning"));
        assertTrue(NRouterResponseMeta.HEADER_NAMES.contains("x-nr-guardrails"));
        assertTrue(NRouterResponseMeta.HEADER_NAMES.contains("x-nr-request-id"));
        assertTrue(NRouterResponseMeta.HEADER_NAMES.contains("x-nr-response-cache-age"));
    }

    @Test
    void messagesUsesRealPathAndReturnsMetadata() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/messages", exchange -> {
            assertEquals("Bearer sk-nrouter-test", exchange.getRequestHeaders().getFirst("Authorization"));
            byte[] body = "{\"content\":[{\"text\":\"ok\"}]}".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("content-type", "application/json");
            exchange.getResponseHeaders().set("x-nr-request-id", "req_java");
            exchange.getResponseHeaders().set("x-nr-request-cost", "0.00042");
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
            NRouterHttpResponse response = NRouter.httpClient("sk-nrouter-test", base)
                    .messages(Map.of("model", "claude"));
            assertEquals("req_java", response.meta().requestId());
            assertEquals(0.00042, response.meta().cost());
            assertEquals("ok", response.body().at("/content/0/text").asText());
        } finally {
            server.stop(0);
        }
    }

    @Test
    void gatewayFailuresAreTypedAndKeepResponseContext() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/messages", exchange -> {
            byte[] body = ("{\"error\":{\"type\":\"guardrail_blocked\"," +
                    "\"message\":\"the response was withheld by an output guardrail\"}}")
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("content-type", "application/json");
            exchange.getResponseHeaders().set("x-nr-request-id", "req_blocked");
            exchange.sendResponseHeaders(400, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
            NRouterException error = assertThrows(NRouterException.class, () ->
                    NRouter.httpClient("sk-nrouter-test", base).messages(Map.of()));
            assertEquals(NRouterException.Kind.GUARDRAIL_BLOCKED, error.kind());
            assertEquals("guardrail_blocked", error.code());
            assertEquals("req_blocked", error.meta().requestId());
            assertFalse(error.isRetryable());
        } finally {
            server.stop(0);
        }
    }

    @Test
    void everyGatewayOperationAndStreamHasANamedWireHelper() throws Exception {
        List<SeenRequest> seen = new CopyOnWriteArrayList<>();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1", exchange -> {
            byte[] requestBody = exchange.getRequestBody().readAllBytes();
            seen.add(new SeenRequest(
                    exchange.getRequestMethod(),
                    exchange.getRequestURI().getRawPath(),
                    exchange.getRequestHeaders().getFirst("Authorization"),
                    exchange.getRequestHeaders().getFirst("Accept"),
                    exchange.getRequestHeaders().getFirst("Content-Type"),
                    requestBody));
            boolean binary = exchange.getRequestURI().getPath().equals("/v1/audio/speech")
                    || exchange.getRequestURI().getPath().endsWith("/content");
            boolean stream = new String(requestBody, StandardCharsets.UTF_8).contains("\"stream\":true");
            byte[] responseBody = binary
                    ? new byte[] {0, 1, 2, (byte) 255}
                    : (stream ? "data: {\"delta\":\"ok\"}\n\ndata: [DONE]\n\n" : "{\"ok\":true}")
                            .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "content-type",
                    binary ? "application/octet-stream" : (stream ? "text/event-stream" : "application/json"));
            exchange.getResponseHeaders().set("x-nr-request-id", "req_java_matrix");
            exchange.sendResponseHeaders(200, responseBody.length);
            exchange.getResponseBody().write(responseBody);
            exchange.close();
        });
        server.start();
        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
            NRouterHttpClient client = NRouter.httpClient("sk-nrouter-test", base);
            Map<String, Object> json = Map.of("model", "test");
            client.chatCompletions(json);
            client.completions(json);
            client.embeddings(json);
            client.imagesGenerations(json);
            client.createVideo(json);
            assertArrayEquals(new byte[] {0, 1, 2, (byte) 255}, client.audioSpeech(json).body());
            client.audioTranscriptions("sample.wav", new byte[] {7, 8}, Map.of("model", "test"));
            client.models();
            client.model("anthropic/claude sonnet?beta#1");
            client.messages(json);
            client.countTokens(json);
            client.responses(json);
            client.audioTranslations("sample.wav", new byte[] {9, 10}, Map.of("model", "test"));
            client.retrieveVideo("vid/unsafe");
            assertEquals(4, client.downloadVideoContent("vid/unsafe").body().length);

            try (NRouterStreamResponse stream = client.chatCompletionsStream(json)) {
                assertEquals(4, stream.lines().count());
                assertEquals("req_java_matrix", stream.meta().requestId());
            }
            try (NRouterStreamResponse stream = client.completionsStream(json)) {
                assertEquals(4, stream.lines().count());
            }
            try (NRouterStreamResponse stream = client.messagesStream(json)) {
                assertEquals(4, stream.lines().count());
            }
            try (NRouterStreamResponse stream = client.responsesStream(json)) {
                assertEquals(4, stream.lines().count());
            }

            List<String> wires = new ArrayList<>();
            for (SeenRequest request : seen) {
                wires.add(request.method + " " + request.path);
                assertEquals("Bearer sk-nrouter-test", request.authorization);
            }
            assertEquals(List.of(
                    "POST /v1/chat/completions",
                    "POST /v1/completions",
                    "POST /v1/embeddings",
                    "POST /v1/images/generations",
                    "POST /v1/videos",
                    "POST /v1/audio/speech",
                    "POST /v1/audio/transcriptions",
                    "GET /v1/models",
                    "GET /v1/models/anthropic/claude%20sonnet%3Fbeta%231",
                    "POST /v1/messages",
                    "POST /v1/messages/count_tokens",
                    "POST /v1/responses",
                    "POST /v1/audio/translations",
                    "GET /v1/videos/vid%2Funsafe",
                    "GET /v1/videos/vid%2Funsafe/content",
                    "POST /v1/chat/completions",
                    "POST /v1/completions",
                    "POST /v1/messages",
                    "POST /v1/responses"), wires);
            assertTrue(seen.get(6).contentType.startsWith("multipart/form-data; boundary=nrouter-"));
            assertEquals("application/octet-stream", seen.get(5).accept);
            assertEquals("application/octet-stream", seen.get(14).accept);
            assertEquals("application/json", seen.get(6).accept);
            String multipart = new String(seen.get(6).body, StandardCharsets.ISO_8859_1);
            assertTrue(multipart.contains("filename=\"sample.wav\""));
            assertTrue(multipart.contains("name=\"model\"\r\n\r\ntest"));
            for (int index = 15; index < seen.size(); index++) {
                assertEquals("text/event-stream", seen.get(index).accept);
                assertTrue(new String(seen.get(index).body, StandardCharsets.UTF_8).contains("\"stream\":true"));
            }
        } finally {
            server.stop(0);
        }
    }

    @Test
    void multipartRefusesHeaderInjectionBeforeNetworkIO() {
        NRouterHttpClient client = NRouter.httpClient("sk-nrouter-test", "http://127.0.0.1:1/v1");
        assertThrows(IllegalArgumentException.class, () ->
                client.audioTranscriptions("safe.wav\r\nX-Evil: yes", new byte[] {1}, Map.of()));
        assertThrows(IllegalArgumentException.class, () ->
                client.audioTranslations("safe.wav", new byte[] {1}, Map.of("bad\r\nname", "x")));
    }

    @Test
    void malformedJsonSuccessKeepsBillingContext() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/models", exchange -> {
            byte[] body = "not-json".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("content-type", "text/plain");
            exchange.getResponseHeaders().set("x-nr-request-id", "req_billed_bad_json");
            exchange.getResponseHeaders().set("x-nr-request-cost", "0.0042");
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
            NRouterException error = assertThrows(
                    NRouterException.class,
                    () -> NRouter.httpClient("sk-nrouter-test", base).models());
            assertEquals(NRouterException.Kind.TRANSPORT, error.kind());
            assertEquals(200, error.status());
            assertEquals("req_billed_bad_json", error.meta().requestId());
            assertEquals(0.0042, error.meta().cost());
            assertTrue(error.getMessage().contains("may have been billed"));
        } finally {
            server.stop(0);
        }
    }

    @Test
    void guardrailErrorInsideSuccessfulStreamIsTypedLazily() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/messages", exchange -> {
            byte[] body = ("event: error\n"
                    + "data: {\"error\":{\n"
                    + "data: \"type\":\"guardrail_blocked\",\"message\":\"withheld\"}}\n\n")
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("content-type", "text/event-stream");
            exchange.getResponseHeaders().set("x-nr-request-id", "req_stream_blocked");
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
            try (NRouterStreamResponse stream = NRouter.httpClient("sk-nrouter-test", base)
                    .messagesStream(Map.of("model", "claude"))) {
                NRouterException error = assertThrows(NRouterException.class, () ->
                        stream.lines().forEach(ignored -> { }));
                assertEquals(NRouterException.Kind.GUARDRAIL_BLOCKED, error.kind());
                assertEquals(200, error.status());
                assertEquals("req_stream_blocked", error.meta().requestId());
            }
        } finally {
            server.stop(0);
        }
    }

    @Test
    void pathParametersRejectDotTraversalBeforeNetworkIO() {
        NRouterHttpClient client = NRouter.httpClient("sk-nrouter-test", "http://127.0.0.1:1/v1");
        assertThrows(IllegalArgumentException.class, () -> client.model("provider/../secret"));
        assertThrows(IllegalArgumentException.class, () -> client.retrieveVideo(".."));
        assertThrows(IllegalArgumentException.class, () -> client.downloadVideoContent("."));
    }

    @Test
    void nonJsonProxyFailureDoesNotExposeItsBody() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/models", exchange -> {
            byte[] body = "proxy at http://10.0.0.7 failed with sk-nrouter-secret"
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("x-nr-request-id", "req_proxy_failure");
            exchange.sendResponseHeaders(502, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
            NRouterException error = assertThrows(
                    NRouterException.class,
                    () -> NRouter.httpClient("sk-nrouter-test", base).models());
            assertEquals(NRouterException.Kind.SERVICE, error.kind());
            assertEquals("nRouter request failed with HTTP 502", error.getMessage());
            assertEquals("req_proxy_failure", error.meta().requestId());
        } finally {
            server.stop(0);
        }
    }

    @Test
    void lazyStreamReadFailureIsTypedAndKeepsMetadata() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/messages", exchange -> {
            byte[] partial = "data: {\"partial\":true}\n".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("content-type", "text/event-stream");
            exchange.getResponseHeaders().set("x-nr-request-id", "req_broken_stream");
            exchange.sendResponseHeaders(200, partial.length + 100);
            exchange.getResponseBody().write(partial);
            exchange.getResponseBody().flush();
            exchange.close();
        });
        server.start();
        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
            try (NRouterStreamResponse stream = NRouter.httpClient("sk-nrouter-test", base)
                    .messagesStream(Map.of("model", "claude"))) {
                NRouterException error = assertThrows(NRouterException.class, () ->
                        stream.lines().forEach(ignored -> { }));
                assertEquals(NRouterException.Kind.TRANSPORT, error.kind());
                assertEquals(200, error.status());
                assertEquals("req_broken_stream", error.meta().requestId());
                assertTrue(error.getMessage().contains("may have been billed"));
            }
        } finally {
            server.stop(0);
        }
    }

    @Test
    void defaultTransportBoundsConnectAndBufferedRequestTime() {
        // HttpClient.newHttpClient() carries NEITHER, so a stall hung the caller
        // forever. Assert the values, not that a builder was called.
        NRouterHttpClient client = NRouter.httpClient("sk-nrouter-test", "http://127.0.0.1:1/v1");
        assertEquals(
                Optional.of(Duration.ofSeconds(15)),
                client.httpClient().connectTimeout());
        assertEquals(Duration.ofMinutes(10), client.requestTimeout());
        // The buffered ceiling must sit above the gateway's worst honest case:
        // three provider attempts, up to 20s cumulative backoff, a 120s
        // between-bytes budget each. Cutting below that aborts a call the
        // gateway settles and BILLS.
        assertTrue(client.requestTimeout().compareTo(Duration.ofMinutes(7)) > 0);
    }

    @Test
    void aStalledServerCutsABufferedRequestInsteadOfHangingForever() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/models", exchange -> {
            try {
                Thread.sleep(5_000);
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
            exchange.sendResponseHeaders(200, 0);
            exchange.close();
        });
        server.start();
        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
            NRouterHttpClient client = NRouter.httpClient(
                    "sk-nrouter-test", base, NRouterHttpClient.defaultHttpClient(), Duration.ofMillis(400));
            long started = System.nanoTime();
            NRouterException error = assertThrows(NRouterException.class, client::models);
            long elapsedMillis = (System.nanoTime() - started) / 1_000_000;
            assertEquals(NRouterException.Kind.TRANSPORT, error.kind());
            assertTrue(elapsedMillis < 4_000, "the buffered request was not cut: " + elapsedMillis + "ms");
        } finally {
            server.stop(0);
        }
    }

    @Test
    void aSlowStreamingBodyIsNeverCutByTheBufferedRequestTimeout() throws Exception {
        // SSE is long BY DESIGN. A whole-exchange ceiling on this path would
        // kill a healthy completion the gateway has already billed for.
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/messages", exchange -> {
            exchange.getResponseHeaders().set("content-type", "text/event-stream");
            exchange.getResponseHeaders().set("x-nr-request-id", "req_slow_stream");
            exchange.sendResponseHeaders(200, 0);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write("data: {\"delta\":\"one\"}\n\n".getBytes(StandardCharsets.UTF_8));
                out.flush();
                Thread.sleep(1_200);
                out.write("data: {\"delta\":\"two\"}\n\ndata: [DONE]\n\n".getBytes(StandardCharsets.UTF_8));
                out.flush();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
            exchange.close();
        });
        server.start();
        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
            NRouterHttpClient client = NRouter.httpClient(
                    "sk-nrouter-test", base, NRouterHttpClient.defaultHttpClient(), Duration.ofMillis(200));
            try (NRouterStreamResponse stream = client.messagesStream(Map.of("model", "claude"))) {
                List<String> lines = stream.lines().toList();
                assertEquals("req_slow_stream", stream.meta().requestId());
                assertTrue(lines.contains("data: {\"delta\":\"two\"}"),
                        "the stream was cut before its second frame: " + lines);
                assertTrue(lines.contains("data: [DONE]"), "the stream never reached [DONE]: " + lines);
            }
        } finally {
            server.stop(0);
        }
    }

    @Test
    void aSlowBinaryDownloadIsNeverCutByTheBufferedRequestTimeout() throws Exception {
        // Generated audio and video are large and slow, and already paid for.
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/audio/speech", exchange -> {
            exchange.getResponseHeaders().set("content-type", "application/octet-stream");
            exchange.sendResponseHeaders(200, 0);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(new byte[] {1, 2});
                out.flush();
                Thread.sleep(1_200);
                out.write(new byte[] {3, 4});
                out.flush();
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
            }
            exchange.close();
        });
        server.start();
        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
            NRouterHttpClient client = NRouter.httpClient(
                    "sk-nrouter-test", base, NRouterHttpClient.defaultHttpClient(), Duration.ofMillis(200));
            assertArrayEquals(new byte[] {1, 2, 3, 4}, client.audioSpeech(Map.of("model", "tts")).body());
        } finally {
            server.stop(0);
        }
    }

    @Test
    void anInjectedTransportFullyOverridesTheDefaults() throws Exception {
        HttpClient injected = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
        NRouterHttpClient client = NRouter.httpClient(
                "sk-nrouter-test", "http://127.0.0.1:1/v1", injected, Duration.ofSeconds(7));
        assertSame(injected, client.httpClient());
        assertEquals(Optional.of(Duration.ofSeconds(3)), client.httpClient().connectTimeout());
        assertEquals(Duration.ofSeconds(7), client.requestTimeout());

        // And it is the transport actually used, not merely stored.
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/models", exchange -> {
            byte[] body = "{\"ok\":true}".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("content-type", "application/json");
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
            NRouterHttpResponse response = NRouter
                    .httpClient("sk-nrouter-test", base, injected, Duration.ofSeconds(7))
                    .models();
            assertTrue(response.body().get("ok").asBoolean());
        } finally {
            server.stop(0);
        }
    }

    @Test
    void aNonPositiveRequestTimeoutIsRefusedRatherThanMeaningUnbounded() {
        HttpClient injected = HttpClient.newHttpClient();
        assertThrows(IllegalArgumentException.class, () ->
                NRouter.httpClient("sk-nrouter-test", "http://127.0.0.1:1/v1", injected, Duration.ZERO));
        assertThrows(IllegalArgumentException.class, () ->
                NRouter.httpClient("sk-nrouter-test", "http://127.0.0.1:1/v1", injected, Duration.ofSeconds(-1)));
    }

    @Test
    void onlyBufferedRequestsCarryAWholeRequestTimeout() throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1", exchange -> {
            boolean binary = exchange.getRequestURI().getPath().equals("/v1/audio/speech")
                    || exchange.getRequestURI().getPath().endsWith("/content");
            boolean stream = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8)
                    .contains("\"stream\":true");
            byte[] body = binary
                    ? new byte[] {1}
                    : (stream ? "data: [DONE]\n\n" : "{\"ok\":true}").getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "content-type",
                    binary ? "application/octet-stream" : (stream ? "text/event-stream" : "application/json"));
            exchange.sendResponseHeaders(200, body.length);
            exchange.getResponseBody().write(body);
            exchange.close();
        });
        server.start();
        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
            RecordingHttpClient recorder = new RecordingHttpClient(NRouterHttpClient.defaultHttpClient());
            Duration ceiling = Duration.ofSeconds(42);
            NRouterHttpClient client = NRouter.httpClient("sk-nrouter-test", base, recorder, ceiling);

            client.chatCompletions(Map.of("model", "test"));                       // buffered JSON POST
            client.models();                                                       // buffered JSON GET
            client.audioTranscriptions("a.wav", new byte[] {1}, Map.of());         // buffered multipart
            client.audioSpeech(Map.of("model", "tts"));                            // binary download
            client.downloadVideoContent("vid");                                    // binary download
            try (NRouterStreamResponse stream = client.messagesStream(Map.of("model", "claude"))) {
                stream.lines().forEach(ignored -> { });
            }

            List<Optional<Duration>> timeouts = new ArrayList<>();
            for (HttpRequest request : recorder.sent) {
                timeouts.add(request.timeout());
            }
            assertEquals(
                    List.of(
                            Optional.of(ceiling),   // POST /v1/chat/completions
                            Optional.of(ceiling),   // GET  /v1/models
                            Optional.of(ceiling),   // POST /v1/audio/transcriptions
                            Optional.empty(),       // POST /v1/audio/speech      — generated audio
                            Optional.empty(),       // GET  /v1/videos/vid/content — generated video
                            Optional.empty()),      // POST /v1/messages (SSE)     — long by design
                    timeouts);
        } finally {
            server.stop(0);
        }
    }
}
