package ai.nrouter.sdk;

import static org.junit.jupiter.api.Assertions.*;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CopyOnWriteArrayList;
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
}
