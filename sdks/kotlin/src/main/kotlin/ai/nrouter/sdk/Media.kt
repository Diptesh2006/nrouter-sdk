package ai.nrouter.sdk

import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import java.util.Locale

/** Supported audio formats for speech generation. */
public val VALID_AUDIO_FORMATS: List<String> = listOf("mp3", "opus", "aac", "flac", "wav", "pcm")

/**
 * Validates an audio format string against the supported speech formats.
 *
 * @throws NRouterError.Configuration if null or unsupported.
 */
public fun validateAudioFormat(format: String) {
    val clean = format.trim().lowercase(Locale.ROOT)
    if (!VALID_AUDIO_FORMATS.contains(clean)) {
        throw NRouterError.Configuration(
            "Invalid audio format '$format'; must be one of: ${VALID_AUDIO_FORMATS.joinToString(", ")}"
        )
    }
}

/**
 * Polls a video generation job until completion, terminal failure, or timeout.
 */
public suspend fun NRouter.waitForVideo(
    videoID: String,
    pollIntervalMillis: Long = 50L,
    timeoutMillis: Long = 30_000L
): NRouter.Response {
    val cleanId = videoID.trim()
    if (cleanId.isEmpty()) {
        throw NRouterError.Configuration("videoID must not be empty")
    }

    val start = System.currentTimeMillis()
    while (System.currentTimeMillis() - start < timeoutMillis) {
        currentCoroutineContext().ensureActive()
        val resp = retrieveVideo(cleanId)
        val status = resp.body.optString("status")?.trim()?.lowercase(Locale.ROOT)
        if (status == "completed" || status == "succeeded") {
            return resp
        } else if (status == "failed" || status == "cancelled") {
            throw NRouterError.Service(
                NRouterErrorBody(
                    message = "Video job $cleanId ended with status: $status",
                    code = "video_failed",
                    status = 500
                )
            )
        }
        delay(pollIntervalMillis)
    }

    throw NRouterError.Transport("Timeout waiting for video job $cleanId")
}
