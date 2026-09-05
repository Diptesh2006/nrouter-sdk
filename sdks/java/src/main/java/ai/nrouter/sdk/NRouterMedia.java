package ai.nrouter.sdk;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Duration;
import java.time.Instant;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Locale;

/**
 * Multimodal media helpers and video polling utilities for nRouter.
 */
public final class NRouterMedia {

    public static final List<String> VALID_AUDIO_FORMATS = Collections.unmodifiableList(
            Arrays.asList("mp3", "opus", "aac", "flac", "wav", "pcm")
    );

    private NRouterMedia() {}

    /**
     * Validates that the provided audio format is one of the supported speech formats.
     *
     * @param format the format string (e.g. "mp3", "wav")
     * @throws NRouterException if null, empty, or unsupported
     */
    public static void validateAudioFormat(String format) {
        if (format == null) {
            throw NRouterException.configuration("Audio format must not be null");
        }
        String clean = format.trim().toLowerCase(Locale.ROOT);
        if (!VALID_AUDIO_FORMATS.contains(clean)) {
            throw NRouterException.configuration(
                    "Invalid audio format '" + format + "'; must be one of: " + String.join(", ", VALID_AUDIO_FORMATS)
            );
        }
    }

    /**
     * Polls a video generation job until completion, terminal failure, or timeout.
     */
    public static NRouterHttpResponse waitForVideo(
            NRouterHttpClient client,
            String videoId,
            Duration pollInterval,
            Duration timeout
    ) {
        if (client == null) {
            throw NRouterException.configuration("client must not be null");
        }
        if (videoId == null || videoId.trim().isEmpty()) {
            throw NRouterException.configuration("videoId must not be empty");
        }
        String cleanId = videoId.trim();
        Duration interval = pollInterval != null ? pollInterval : Duration.ofMillis(50);
        Duration maxDuration = timeout != null ? timeout : Duration.ofSeconds(30);

        Instant stopAt = Instant.now().plus(maxDuration);

        while (Instant.now().isBefore(stopAt)) {
            if (Thread.currentThread().isInterrupted()) {
                throw NRouterException.transport("Video polling interrupted for job " + cleanId);
            }

            NRouterHttpResponse resp = client.retrieveVideo(cleanId);
            JsonNode body = resp.body();
            if (body != null && body.hasNonNull("status")) {
                String status = body.get("status").asText().trim().toLowerCase(Locale.ROOT);
                if ("completed".equals(status) || "succeeded".equals(status)) {
                    return resp;
                } else if ("failed".equals(status) || "cancelled".equals(status)) {
                    throw NRouterException.gateway(
                            "Video job " + cleanId + " ended with status: " + body.get("status").asText(),
                            "video_failed",
                            500,
                            resp.meta()
                    );
                }
            }

            try {
                Thread.sleep(interval.toMillis());
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                throw NRouterException.transport("Video polling interrupted for job " + cleanId);
            }
        }

        throw NRouterException.transport("Timeout waiting for video job " + cleanId);
    }
}
