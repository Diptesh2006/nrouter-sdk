import Foundation

/// Audio formats supported by the nRouter speech endpoint.
public let validAudioFormats = ["mp3", "opus", "aac", "flac", "wav", "pcm"]

/// Validates an audio format string against the supported speech formats.
public func validateAudioFormat(_ format: String) throws {
    let lower = format.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    guard validAudioFormats.contains(lower) else {
        throw NRouterError.configuration("Invalid audio format '\(format)'; must be one of: \(validAudioFormats.joined(separator: ", "))")
    }
}

extension NRouter {
    /// Polls a video generation job until it reaches a terminal status ("completed", "failed", "cancelled")
    /// or until the timeout interval elapses.
    public func waitForVideo(
        _ videoID: String,
        pollInterval: TimeInterval = 0.5,
        timeout: TimeInterval = 60.0
    ) async throws -> Response {
        let trimmedID = videoID.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedID.isEmpty else {
            throw NRouterError.configuration("videoID must not be empty")
        }

        let start = Date()
        while Date().timeIntervalSince(start) < timeout {
            let resp = try await retrieveVideo(trimmedID)
            if let status = resp.body["status"] as? String {
                let s = status.lowercased()
                if s == "completed" || s == "succeeded" {
                    return resp
                } else if s == "failed" || s == "cancelled" {
                    throw NRouterError.service(
                        NRouterErrorBody(
                            message: "Video job \(trimmedID) ended with status: \(status)",
                            code: "video_failed",
                            status: 500
                        )
                    )
                }
            }
            try await Task.sleep(nanoseconds: UInt64(pollInterval * 1_000_000_000))
        }
        throw NRouterError.transport("Timeout waiting for video job \(trimmedID)")
    }
}
