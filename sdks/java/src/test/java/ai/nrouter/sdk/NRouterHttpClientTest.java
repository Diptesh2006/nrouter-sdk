package ai.nrouter.sdk;

import static org.junit.jupiter.api.Assertions.*;

import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.junit.jupiter.api.Test;

class NRouterHttpClientTest {
    @Test
    void publishesTheCompleteResponseHeaderContract() {
        assertEquals(14, NRouterResponseMeta.HEADER_NAMES.size());
        assertEquals(14, NRouterResponseMeta.HEADER_NAMES.stream().distinct().count());
        assertTrue(NRouterResponseMeta.HEADER_NAMES.contains("x-nr-budget-warning"));
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
}
