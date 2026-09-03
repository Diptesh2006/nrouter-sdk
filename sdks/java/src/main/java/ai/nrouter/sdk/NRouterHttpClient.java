package ai.nrouter.sdk;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
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
    private final String apiKey;
    private final String baseUrl;
    private final HttpClient http;
    private final ObjectMapper json = new ObjectMapper();

    NRouterHttpClient(String apiKey, String baseUrl) {
        this.apiKey = apiKey;
        this.baseUrl = baseUrl.replaceAll("/+$", "");
        this.http = HttpClient.newHttpClient();
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
        return sendJson(request(path).header("Accept", "application/json")
                .header("Content-Type", "application/json").POST(jsonBody(body)).build());
    }

    private NRouterHttpResponse get(String path) {
        return sendJson(request(path).header("Accept", "application/json").GET().build());
    }

    private NRouterBinaryResponse postBinary(String path, Object body) {
        return sendBinary(request(path).header("Accept", "application/octet-stream")
                .header("Content-Type", "application/json").POST(jsonBody(body)).build());
    }

    private NRouterBinaryResponse getBinary(String path) {
        return sendBinary(request(path).header("Accept", "application/octet-stream").GET().build());
    }

    private NRouterHttpResponse postMultipart(
            String path, String filename, byte[] file, Map<String, ?> fields) {
        String boundary = "nrouter-" + UUID.randomUUID();
        byte[] body = multipart(boundary, filename, file, fields);
        HttpRequest request = request(path)
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
            HttpResponse<Stream<String>> response = http.send(
                    request(path).header("Accept", "text/event-stream")
                            .header("Content-Type", "application/json").POST(jsonBody(streamed)).build(),
                    HttpResponse.BodyHandlers.ofLines());
            NRouterResponseMeta meta = NRouterResponseMeta.fromHeaders(response.headers());
            if (isSuccess(response.statusCode())) {
                Stream<String> guarded = guardSse(response.body(), response.statusCode(), meta);
                return new NRouterStreamResponse(guarded, meta, response.statusCode());
            }
            String errorBody;
            try (Stream<String> lines = response.body()) {
                errorBody = lines.collect(Collectors.joining("\n"));
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
        HttpResponse<byte[]> response = send(request);
        NRouterResponseMeta meta = NRouterResponseMeta.fromHeaders(response.headers());
        if (!isSuccess(response.statusCode())) {
            throw gatewayFailure(response.body(), response.statusCode(), meta);
        }
        try {
            JsonNode parsed = json.readTree(response.body());
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
        HttpResponse<byte[]> response = send(request);
        NRouterResponseMeta meta = NRouterResponseMeta.fromHeaders(response.headers());
        if (!isSuccess(response.statusCode())) {
            throw gatewayFailure(response.body(), response.statusCode(), meta);
        }
        String contentType = response.headers().firstValue("content-type").orElse(null);
        return new NRouterBinaryResponse(response.body(), meta, response.statusCode(), contentType);
    }

    private HttpResponse<byte[]> send(HttpRequest request) {
        try {
            return http.send(request, HttpResponse.BodyHandlers.ofByteArray());
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw NRouterException.transport("nRouter request interrupted");
        } catch (Exception error) {
            throw NRouterException.transport(redact(error.getMessage()));
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
