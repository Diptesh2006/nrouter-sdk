import 'dart:async';
import 'client.dart';
import 'errors.dart';

/// Supported audio formats for speech generation.
const List<String> validAudioFormats = ['mp3', 'opus', 'aac', 'flac', 'wav', 'pcm'];

/// Validates an audio format string.
void validateAudioFormat(String format) {
  final clean = format.trim().toLowerCase();
  if (!validAudioFormats.contains(clean)) {
    throw NRouterConfigurationError(
      "Invalid audio format '$format'; must be one of: ${validAudioFormats.join(', ')}",
    );
  }
}

/// Extension providing polling helpers on the NRouter client.
extension VideoPolling on NRouter {
  /// Polls a video generation job until it completes, fails, or times out.
  Future<NRouterResponse> waitForVideo(
    String videoId, {
    Duration pollInterval = const Duration(milliseconds: 50),
    Duration timeout = const Duration(seconds: 30),
  }) async {
    final cleanId = videoId.trim();
    if (cleanId.isEmpty) {
      throw NRouterConfigurationError('videoId must not be empty');
    }
    final stopAt = DateTime.now().add(timeout);
    while (DateTime.now().isBefore(stopAt)) {
      final resp = await retrieveVideo(cleanId);
      final status = resp.body['status']?.toString().toLowerCase();
      if (status == 'completed' || status == 'succeeded') {
        return resp;
      } else if (status == 'failed' || status == 'cancelled') {
        throw NRouterServiceError(
          NRouterErrorBody(
            message: 'Video job $cleanId ended with status: $status',
            code: 'video_failed',
            status: 500,
          ),
        );
      }
      await Future.delayed(pollInterval);
    }
    throw NRouterTransportError('Timeout waiting for video job $cleanId');
  }
}
