package ai.nrouter.sdk;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class NRouterMediaTest {

    @Test
    void testValidateAudioFormat() {
        for (String fmt : NRouterMedia.VALID_AUDIO_FORMATS) {
            assertDoesNotThrow(() -> NRouterMedia.validateAudioFormat(fmt));
            assertDoesNotThrow(() -> NRouterMedia.validateAudioFormat(" " + fmt.toUpperCase() + " "));
        }

        NRouterException ex = assertThrows(NRouterException.class, () -> NRouterMedia.validateAudioFormat("invalid_fmt"));
        assertEquals(NRouterException.Kind.CONFIGURATION, ex.kind());
        assertTrue(ex.getMessage().contains("Invalid audio format"));

        assertThrows(NRouterException.class, () -> NRouterMedia.validateAudioFormat(null));
    }

    @Test
    void testWaitForVideoSuccess() throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        AtomicInteger count = new AtomicInteger(0);
        server.createContext("/v1/videos/vid_123", exchange -> {
            int attempt = count.incrementAndGet();
            byte[] responseBody;
            if (attempt < 2) {
                responseBody = "{\"id\":\"vid_123\",\"status\":\"processing\"}".getBytes(StandardCharsets.UTF_8);
            } else {
                responseBody = "{\"id\":\"vid_123\",\"status\":\"completed\",\"output\":\"https://example.com/out.mp4\"}".getBytes(StandardCharsets.UTF_8);
            }
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, responseBody.length);
            exchange.getResponseBody().write(responseBody);
            exchange.close();
        });
        server.start();

        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
            NRouterHttpClient client = NRouter.httpClient("sk-nrouter-test", base);

            NRouterHttpResponse resp = client.waitForVideo("vid_123", Duration.ofMillis(10), Duration.ofSeconds(2));
            assertNotNull(resp);
            assertEquals("completed", resp.body().get("status").asText());
            assertTrue(count.get() >= 2);
        } finally {
            server.stop(0);
        }
    }

    @Test
    void testWaitForVideoTerminalFailure() throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/videos/vid_fail", exchange -> {
            byte[] responseBody = "{\"id\":\"vid_fail\",\"status\":\"failed\",\"error\":{\"message\":\"Generation failed\"}}".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, responseBody.length);
            exchange.getResponseBody().write(responseBody);
            exchange.close();
        });
        server.start();

        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
            NRouterHttpClient client = NRouter.httpClient("sk-nrouter-test", base);

            NRouterException ex = assertThrows(NRouterException.class, () ->
                    client.waitForVideo("vid_fail", Duration.ofMillis(10), Duration.ofSeconds(2))
            );
            assertTrue(ex.getMessage().contains("ended with status: failed"));
        } finally {
            server.stop(0);
        }
    }

    @Test
    void testWaitForVideoTimeout() throws IOException {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/v1/videos/vid_slow", exchange -> {
            byte[] responseBody = "{\"id\":\"vid_slow\",\"status\":\"processing\"}".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, responseBody.length);
            exchange.getResponseBody().write(responseBody);
            exchange.close();
        });
        server.start();

        try {
            String base = "http://127.0.0.1:" + server.getAddress().getPort() + "/v1";
            NRouterHttpClient client = NRouter.httpClient("sk-nrouter-test", base);

            NRouterException ex = assertThrows(NRouterException.class, () ->
                    client.waitForVideo("vid_slow", Duration.ofMillis(10), Duration.ofMillis(50))
            );
            assertEquals(NRouterException.Kind.TRANSPORT, ex.kind());
            assertTrue(ex.getMessage().contains("Timeout waiting for video job"));
        } finally {
            server.stop(0);
        }
    }
}
