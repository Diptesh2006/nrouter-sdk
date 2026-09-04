import 'dart:convert';

import 'package:http/http.dart' as http;

import 'errors.dart';
import 'meta.dart';

/// A body paired with the metadata the gateway reported for it.
class NRouterResponse {
  const NRouterResponse({
    required this.body,
    required this.meta,
    required this.statusCode,
  });

  final Map<String, dynamic> body;
  final NRouterResponseMeta meta;
  final int statusCode;
}

/// One decoded server-sent event from a streaming text request.
class NRouterStreamChunk {
  const NRouterStreamChunk({
    required this.event,
    required this.delta,
    required this.data,
    required this.meta,
  });

  final String event;
  final String delta;
  final Map<String, dynamic> data;
  final NRouterResponseMeta meta;
}

/// Raw bytes paired with the metadata and status reported by the gateway.
typedef NRouterBinaryResponse = ({
  List<int> bytes,
  NRouterResponseMeta meta,
  int statusCode,
});

/// nRouter client — one API key for models across six provider clouds.
///
/// The gateway speaks the OpenAI wire format, so request and response bodies
/// are the shapes you already know. This client adds the two things a raw
/// `http` call does not: key validation before egress, and the `x-nr-*`
/// metadata (cost, tokens, cache outcome) handed back beside every body.
///
/// ```dart
/// final client = NRouter(apiKey: myKey);
/// final result = await client.chatCompletions({
///   'model': 'claude-sonnet-4-5',
///   'messages': [{'role': 'user', 'content': 'Hello!'}],
/// });
/// // Unpriced is unknown, not free. Never render a null cost as 0.
/// print(result.meta.cost != null ? 'cost \$${result.meta.cost}' : 'unpriced');
/// client.close();
/// ```
///
/// ### Flutter: do not ship a customer key in the app
///
/// Anything compiled into an app bundle is readable by anyone who downloads it.
/// For a shipped Flutter app, mint a short-lived key on your own backend and
/// pass it here. There is deliberately no environment fallback in this package:
/// `Platform.environment` needs `dart:io`, which does not exist on Flutter web,
/// and it is empty on mobile anyway — a fallback that quietly resolves to
/// nothing is worse than none.
class NRouter {
  /// The gateway's customer surface. A dynamic value: override it for stage.
  static const String defaultBaseUrl = 'https://api.nrouter.ai/v1';

  /// The environment variable the server-side SDKs read. Named here so tooling
  /// and docs agree; this package never reads it (see the class doc).
  static const String envKey = 'NROUTER_API_KEY';

  /// Every customer key carries this prefix.
  static const String keyPrefix = 'sk-nrouter-';

  // --- transport deadlines --------------------------------------------------
  //
  // `package:http` applies NO timeout of any kind: a `Client` that connects to
  // a gateway which then goes silent leaves the future pending forever, and on
  // Flutter that is a spinner nobody can cancel. There is no socket-level knob
  // to set either — the package exposes none — so the bound has to be applied
  // to the FUTURE, which is what the two constants below do.
  //
  // Both are explicit decisions — name it, or you have chosen infinity — sized
  // against the gateway's own budget rather than picked for feel. The gateway's
  // worst HONEST case before a first byte is roughly 410 s: up to three
  // provider attempts, each with a 10 s connect timeout and a 120 s
  // between-bytes read timeout, plus at most 20 s of cumulative backoff. A
  // client deadline below that aborts a request the gateway is about to
  // answer — and the customer is billed anyway, because the provider tokens
  // were already spent.
  //
  // Neither ever RETRIES. Waiting is bounded here; re-sending is not done at
  // all. The gateway reserves credit ONCE per customer request and owns retry
  // and failover, so a client retry of a billed POST is a second call and a
  // second bill with nothing to dedupe on.

  /// Whole-request ceiling for BUFFERED calls — JSON `POST`/`GET` and
  /// multipart upload — 600 s.
  ///
  /// Above the gateway's ~410 s worst honest case with margin, and the same
  /// order as the OpenAI and Anthropic clients' own 600 s defaults, so a
  /// caller migrating from either is not surprised.
  static const Duration defaultTimeout = Duration(seconds: 600);

  /// Time-to-RESPONSE-HEADERS bound for streaming and binary calls — 180 s.
  ///
  /// [stream] and [bytes] bound only the wait for the first response headers;
  /// the body that follows is deliberately UNBOUNDED. A whole-request ceiling
  /// there would sever an SSE stream mid-generation and truncate a long
  /// `GET /videos/{id}/content` — both of them already billed. 180 s sits above
  /// the gateway's own 120 s between-bytes read timeout, so the gateway's
  /// honest error reaches the caller instead of a client-side abort racing it.
  static const Duration defaultStreamTimeout = Duration(seconds: 180);

  /// Build a client. The key is validated up front so a malformed one fails
  /// here rather than as a 401 that reads like a revoked credential.
  ///
  /// [timeout] and [streamTimeout] are separate from [httpClient] on purpose:
  /// `package:http`'s `Client` interface carries no timeout, so injecting one
  /// cannot supply the bound and would silently restore the unbounded default.
  NRouter({
    required String apiKey,
    String baseUrl = defaultBaseUrl,
    http.Client? httpClient,
    this.timeout = defaultTimeout,
    this.streamTimeout = defaultStreamTimeout,
  })  : _apiKey = validateApiKey(apiKey),
        baseUrl = baseUrl.endsWith('/')
            ? baseUrl.substring(0, baseUrl.length - 1)
            : baseUrl,
        _http = httpClient ?? http.Client(),
        _ownsClient = httpClient == null;

  final String _apiKey;
  final http.Client _http;
  final bool _ownsClient;

  /// Whole-request ceiling applied to buffered JSON and multipart calls.
  final Duration timeout;

  /// Time-to-response-headers ceiling applied to streaming and binary calls.
  final Duration streamTimeout;

  /// The one place a deadline turns into an error, so every path says the same
  /// thing — including that the request may already have been BILLED. The
  /// gateway reserves credit before it calls a provider, so a blind re-send
  /// after a timeout is a second call and a second bill.
  static NRouterTransportError _timedOut(Duration bound, String what) =>
      NRouterTransportError(
        'nRouter did not $what within ${bound.inSeconds}s. package:http applies '
        'no timeout of its own, so this bound is the SDK default; pass '
        '`timeout:` or `streamTimeout:` to change it. The request may already '
        'have been billed — do not re-send it blindly.',
      );

  /// The gateway this client talks to, with any trailing slash removed.
  final String baseUrl;

  /// Never the key. Dart's default `toString` is already opaque, but this is
  /// stated rather than relied upon — and it makes a logged client useful
  /// without making it dangerous (Rule #5).
  @override
  String toString() {
    final tail =
        _apiKey.length >= 4 ? _apiKey.substring(_apiKey.length - 4) : '';
    return 'NRouter(baseUrl: $baseUrl, apiKey: $keyPrefix...$tail)';
  }

  /// Validate a key's shape, returning it unchanged.
  static String validateApiKey(String apiKey) {
    if (apiKey.isEmpty) {
      throw const NRouterConfigurationError('No nRouter API key was supplied.');
    }
    if (!apiKey.startsWith(keyPrefix)) {
      throw const NRouterConfigurationError(
        "nRouter API keys start with '$keyPrefix'; got one that does not.",
      );
    }
    return apiKey;
  }

  /// `POST /chat/completions`
  Future<NRouterResponse> chatCompletions(Map<String, dynamic> body) =>
      post('/chat/completions', body);

  /// `POST /completions` — the legacy text-completions wire.
  Future<NRouterResponse> completions(Map<String, dynamic> body) =>
      post('/completions', body);

  /// `POST /embeddings`
  Future<NRouterResponse> embeddings(Map<String, dynamic> body) =>
      post('/embeddings', body);

  /// `POST /messages` — the Anthropic wire format the gateway also serves.
  Future<NRouterResponse> messages(Map<String, dynamic> body) =>
      post('/messages', body);

  /// `POST /responses`
  Future<NRouterResponse> responses(Map<String, dynamic> body) =>
      post('/responses', body);

  /// Incrementally stream `POST /chat/completions` as server-sent events.
  Stream<NRouterStreamChunk> chatCompletionsStream(Map<String, dynamic> body) =>
      stream('/chat/completions', body);

  /// Incrementally stream the legacy `POST /completions` wire.
  Stream<NRouterStreamChunk> completionsStream(Map<String, dynamic> body) =>
      stream('/completions', body);

  /// Incrementally stream the native Anthropic `POST /messages` wire.
  Stream<NRouterStreamChunk> messagesStream(Map<String, dynamic> body) =>
      stream('/messages', body);

  /// Incrementally stream `POST /responses`.
  Stream<NRouterStreamChunk> responsesStream(Map<String, dynamic> body) =>
      stream('/responses', body);

  /// Open a JSON POST as a cold, cancellable SSE stream.
  Stream<NRouterStreamChunk> stream(
    String path,
    Map<String, dynamic> body,
  ) async* {
    final uri = Uri.parse(
      '$baseUrl/${path.startsWith('/') ? path.substring(1) : path}',
    );
    final request = http.Request('POST', uri)
      ..headers['Authorization'] = 'Bearer $_apiKey'
      ..headers['Content-Type'] = 'application/json'
      ..headers['Accept'] = 'text/event-stream'
      ..body = jsonEncode(<String, dynamic>{...body, 'stream': true});

    final http.StreamedResponse response;
    try {
      // Only the wait for RESPONSE HEADERS is bounded. The SSE body that
      // follows has no ceiling: a long generation is a working stream, and
      // cutting it off discards tokens the caller has already paid for.
      response = await _http.send(request).timeout(
            streamTimeout,
            onTimeout: () => throw _timedOut(streamTimeout, 'start streaming'),
          );
    } on NRouterError {
      rethrow;
    } on Exception catch (e) {
      throw NRouterTransportError(e.toString());
    }

    final meta = NRouterResponseMeta.fromHeaders(response.headers);
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final buffered = await http.Response.fromStream(response);
      Map<String, dynamic> parsed = <String, dynamic>{};
      try {
        final decoded = jsonDecode(buffered.body);
        if (decoded is Map<String, dynamic>) parsed = decoded;
      } on FormatException {
        // Preserve the typed status fallback for non-JSON intermediary errors.
      }
      throw NRouterError.fromCode(
        errorBodyFrom(response.statusCode, parsed, meta),
      );
    }

    final contentType = (response.headers['content-type'] ?? '').toLowerCase();
    if (!contentType.contains('text/event-stream')) {
      await response.stream.listen((_) {}).cancel();
      throw NRouterTransportError(
        'nRouter returned ${response.statusCode} with content-type '
        "'$contentType', which is not an SSE stream.",
      );
    }

    var buffer = '';
    var terminated = false;
    try {
      await for (final text in response.stream.transform(utf8.decoder)) {
        buffer = (buffer + text).replaceAll('\r\n', '\n');
        var boundary = buffer.indexOf('\n\n');
        while (boundary >= 0) {
          final frame = buffer.substring(0, boundary);
          buffer = buffer.substring(boundary + 2);
          final result = _parseSseFrame(frame, meta, response.statusCode);
          if (result.terminal) {
            terminated = true;
            return;
          }
          if (result.chunk != null) yield result.chunk!;
          boundary = buffer.indexOf('\n\n');
        }
      }
    } on NRouterError {
      rethrow;
    } on Exception catch (e) {
      throw NRouterTransportError('the stream failed while being read: $e');
    }
    if (!terminated) {
      throw const NRouterTransportError(
        'the stream ended before its terminal event',
      );
    }
  }

  /// `POST /images/generations`
  Future<NRouterResponse> imagesGenerations(Map<String, dynamic> body) =>
      post('/images/generations', body);

  /// `POST /messages/count_tokens` — counts input without generating.
  Future<NRouterResponse> countTokens(Map<String, dynamic> body) =>
      post('/messages/count_tokens', body);

  /// `POST /audio/transcriptions` — Whisper-style speech to text.
  ///
  /// multipart/form-data, not JSON: the gateway requires a binary `file` part
  /// here, so the JSON helpers cannot reach this endpoint at all.
  ///
  /// [fileName] must carry the real extension — the upstream providers pick
  /// their decoder from it, so `audio` is rejected where `speech.mp3` is not.
  Future<NRouterResponse> audioTranscriptions(
    List<int> file,
    String fileName, {
    Map<String, String> fields = const {},
  }) =>
      multipart('/audio/transcriptions', file, fileName, fields: fields);

  /// `POST /audio/translations` — speech in any language to English text.
  Future<NRouterResponse> audioTranslations(
    List<int> file,
    String fileName, {
    Map<String, String> fields = const {},
  }) =>
      multipart('/audio/translations', file, fileName, fields: fields);

  /// `POST /audio/speech` — generated audio plus response metadata.
  Future<NRouterBinaryResponse> audioSpeech(Map<String, dynamic> body) =>
      bytes('/audio/speech', body);

  /// Any multipart `POST` under the gateway's `/v1` root.
  Future<NRouterResponse> multipart(
    String path,
    List<int> file,
    String fileName, {
    Map<String, String> fields = const {},
    String filePartName = 'file',
  }) async {
    final uri = Uri.parse(
      '$baseUrl/${path.startsWith('/') ? path.substring(1) : path}',
    );
    final request = http.MultipartRequest('POST', uri)
      ..headers['Authorization'] = 'Bearer $_apiKey'
      ..fields.addAll(fields)
      ..files.add(
        http.MultipartFile.fromBytes(filePartName, file, filename: fileName),
      );

    http.Response response;
    try {
      // A multipart POST is buffered: `send` completes only once the file has
      // been uploaded AND the response headers are back, so the whole-request
      // ceiling is the right bound here. The JSON body that follows is small.
      final streamed = await _http.send(request).timeout(
            timeout,
            onTimeout: () => throw _timedOut(timeout, 'answer'),
          );
      response = await http.Response.fromStream(streamed);
    } on NRouterError {
      rethrow;
    } on Exception catch (e) {
      throw NRouterTransportError(e.toString());
    }

    final meta = NRouterResponseMeta.fromHeaders(response.headers);
    if (response.statusCode >= 200 && response.statusCode < 300) {
      // A raw FormatException escapes the documented NRouterError hierarchy, so
      // a caller catching the SDK's errors would miss response corruption
      // entirely — on a request that was billed.
      final Object? decoded;
      try {
        decoded = jsonDecode(response.body);
      } on FormatException catch (e) {
        throw NRouterTransportError(
          'nRouter returned ${response.statusCode} with unparseable JSON '
          '(${e.message}); the request was billed but the body did not arrive '
          'intact.',
        );
      }
      if (decoded is! Map<String, dynamic>) {
        throw NRouterTransportError(
          'nRouter returned ${response.statusCode} with a JSON body that is not '
          'an object; the request was billed but the body did not arrive intact.',
        );
      }
      return NRouterResponse(
        body: decoded,
        meta: meta,
        statusCode: response.statusCode,
      );
    }
    Map<String, dynamic> parsed;
    try {
      final decoded = jsonDecode(response.body);
      parsed = decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
    } on FormatException {
      parsed = <String, dynamic>{};
    }
    throw NRouterError.fromCode(
      errorBodyFrom(response.statusCode, parsed, meta),
    );
  }

  /// `GET /models` — what this key is allowed to route to.
  Future<NRouterResponse> models() => get('/models');

  /// `GET /models/{model_id}` — one model visible to this key.
  Future<NRouterResponse> model(String modelId) =>
      get('/models/${modelId.split('/').map(Uri.encodeComponent).join('/')}');

  /// `POST /videos` — starts a video generation job.
  Future<NRouterResponse> createVideo(Map<String, dynamic> body) =>
      post('/videos', body);

  /// `GET /videos/{id}` — polls one video generation job.
  Future<NRouterResponse> retrieveVideo(String videoId) =>
      get('/videos/${Uri.encodeComponent(videoId)}');

  /// `GET /videos/{id}/content` — generated video bytes.
  Future<NRouterBinaryResponse> downloadVideoContent(String videoId) =>
      bytes('/videos/${Uri.encodeComponent(videoId)}/content');

  /// Any `POST` path under the gateway's `/v1` root.
  Future<NRouterResponse> post(String path, Map<String, dynamic> body) =>
      _send('POST', path, body);

  /// Any `GET` path under the gateway's `/v1` root.
  Future<NRouterResponse> get(String path) => _send('GET', path, null);

  /// Raw bytes plus metadata, for the endpoints that do not return JSON.
  ///
  /// `/v1/audio/speech` returns audio, `/v1/videos/{id}/content` returns a
  /// video, and `stream: true` returns SSE. The JSON helpers refuse those
  /// rather than handing back an empty body for a request you were billed for;
  /// this is the method that returns them.
  Future<NRouterBinaryResponse> bytes(
    String path, [
    Map<String, dynamic>? body,
  ]) async {
    final uri = Uri.parse(
      '$baseUrl/${path.startsWith('/') ? path.substring(1) : path}',
    );
    final headers = <String, String>{
      'Authorization': 'Bearer $_apiKey',
      if (body != null) 'Content-Type': 'application/json',
    };

    // Sent through `send` rather than `get`/`post` so the header wait and the
    // body read are two separate waits. Generated audio and video are large:
    // a whole-request ceiling truncates a download that has already been
    // billed, so only the wait for headers is bounded.
    final request = http.Request(body == null ? 'GET' : 'POST', uri)
      ..headers.addAll(headers);
    if (body != null) request.body = jsonEncode(body);

    http.Response response;
    try {
      final streamed = await _http.send(request).timeout(
            streamTimeout,
            onTimeout: () => throw _timedOut(streamTimeout, 'send headers for'),
          );
      response = await http.Response.fromStream(streamed);
    } on NRouterError {
      rethrow;
    } on Exception catch (e) {
      throw NRouterTransportError(e.toString());
    }

    final meta = NRouterResponseMeta.fromHeaders(response.headers);
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return (
        bytes: response.bodyBytes,
        meta: meta,
        statusCode: response.statusCode
      );
    }
    Map<String, dynamic> parsed;
    try {
      final decoded = jsonDecode(response.body);
      parsed = decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
    } on FormatException {
      parsed = <String, dynamic>{};
    }
    throw NRouterError.fromCode(
      errorBodyFrom(response.statusCode, parsed, meta),
    );
  }

  /// Release the underlying HTTP client, when this instance created it.
  void close() {
    if (_ownsClient) _http.close();
  }

  Future<NRouterResponse> _send(
    String method,
    String path,
    Map<String, dynamic>? body,
  ) async {
    final uri = Uri.parse(
      '$baseUrl/${path.startsWith('/') ? path.substring(1) : path}',
    );
    final headers = <String, String>{
      'Authorization': 'Bearer $_apiKey',
      if (body != null) 'Content-Type': 'application/json',
    };

    http.Response response;
    try {
      response = await (method == 'GET'
              ? _http.get(uri, headers: headers)
              : _http.post(uri, headers: headers, body: jsonEncode(body)))
          .timeout(timeout, onTimeout: () => throw _timedOut(timeout, 'answer'));
    } on NRouterError {
      rethrow;
    } on Exception catch (e) {
      throw NRouterTransportError(e.toString());
    }

    final meta = NRouterResponseMeta.fromHeaders(response.headers);

    if (response.statusCode >= 200 && response.statusCode < 300) {
      // A 2xx that is not JSON is a REAL RESPONSE you were billed for —
      // /v1/audio/speech returns audio, video content returns bytes,
      // stream:true returns SSE. Parsing those as JSON yields an empty map, so
      // the caller pays and receives nothing while the call reports success.
      // Refuse loudly instead.
      final contentType =
          (response.headers['content-type'] ?? '').toLowerCase();
      if (!contentType.contains('json')) {
        throw NRouterTransportError(
          'nRouter returned ${response.statusCode} with content-type '
          "'$contentType', which is not JSON. Use bytes() for binary or "
          'streaming endpoints (/v1/audio/speech, /v1/videos/{id}/content, or '
          'stream: true); the JSON helpers would report success with an empty '
          'body.',
        );
      }
      // A 2xx whose JSON does not parse is NOT an empty response — it is a
      // truncated or corrupted one, for a request that was billed. Returning
      // {} here reports success with nothing in it.
      final Object? decoded;
      try {
        decoded = jsonDecode(response.body);
      } on FormatException catch (e) {
        throw NRouterTransportError(
          'nRouter returned ${response.statusCode} with unparseable JSON '
          '(${e.message}); the request was billed but the body did not arrive '
          'intact.',
        );
      }
      if (decoded is! Map<String, dynamic>) {
        throw NRouterTransportError(
          'nRouter returned ${response.statusCode} with a JSON body that is not '
          'an object; the request was billed but the body did not arrive intact.',
        );
      }
      return NRouterResponse(
        body: decoded,
        meta: meta,
        statusCode: response.statusCode,
      );
    }
    Map<String, dynamic> parsed;
    try {
      final decoded = jsonDecode(response.body);
      parsed = decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
    } on FormatException {
      parsed = <String, dynamic>{};
    }
    throw NRouterError.fromCode(
      errorBodyFrom(response.statusCode, parsed, meta),
    );
  }

  /// Pull the gateway's stable `code` and message out of an error payload.
  ///
  /// The gateway nests them under `error`; a bare object is accepted too, so a
  /// proxy that reshapes the envelope cannot downgrade a typed error into a
  /// generic one.
  static NRouterErrorBody errorBodyFrom(
    int status,
    Map<String, dynamic> payload,
    NRouterResponseMeta meta,
  ) {
    final nested = payload['error'];
    final node = nested is Map<String, dynamic> ? nested : payload;
    final message = node['message'];
    final code = node['code'];
    return NRouterErrorBody(
      message: message is String ? message : 'nRouter request failed',
      code: code is String ? code : null,
      status: status,
      requestId: meta.requestId,
      limitSource: meta.limitSource,
      authReason: meta.authReason,
    );
  }
}

typedef _SseResult = ({NRouterStreamChunk? chunk, bool terminal});

_SseResult _parseSseFrame(
  String frame,
  NRouterResponseMeta meta,
  int status,
) {
  var event = '';
  final dataLines = <String>[];
  for (final line in frame.split('\n')) {
    if (line.isEmpty || line.startsWith(':')) continue;
    final separator = line.indexOf(':');
    final name = separator < 0 ? line : line.substring(0, separator);
    var value = separator < 0 ? '' : line.substring(separator + 1);
    if (value.startsWith(' ')) value = value.substring(1);
    if (name == 'event') event = value;
    if (name == 'data') dataLines.add(value);
  }
  if (dataLines.isEmpty) return (chunk: null, terminal: false);
  final encoded = dataLines.join('\n').trim();
  if (encoded.isEmpty) return (chunk: null, terminal: false);
  if (encoded == '[DONE]') return (chunk: null, terminal: true);

  final Object? decoded;
  try {
    decoded = jsonDecode(encoded);
  } on FormatException catch (e) {
    throw NRouterTransportError(
        'the stream contained invalid JSON: ${e.message}');
  }
  if (decoded is! Map<String, dynamic>) {
    throw const NRouterTransportError(
      'the stream contained a JSON event that is not an object',
    );
  }

  if (event == 'error' || decoded['error'] != null) {
    final nested = decoded['error'];
    final node = nested is Map<String, dynamic> ? nested : decoded;
    final type = node['type'];
    final code = node['code'];
    final promoted = code is String
        ? code
        : type is String && _knownErrorCode(type)
            ? type
            : null;
    throw NRouterError.fromCode(NRouterErrorBody(
      message: node['message'] is String
          ? node['message'] as String
          : 'nRouter stream failed',
      code: promoted,
      status: status,
      requestId: meta.requestId,
      limitSource: meta.limitSource,
      authReason: meta.authReason,
    ));
  }

  final type = decoded['type'];
  if (type == 'message_stop' || type == 'response.completed') {
    return (chunk: null, terminal: true);
  }
  return (
    chunk: NRouterStreamChunk(
      event: event,
      delta: _streamDelta(decoded),
      data: decoded,
      meta: meta,
    ),
    terminal: false,
  );
}

String _streamDelta(Map<String, dynamic> data) {
  final direct = data['delta'];
  if (direct is String) return direct;
  if (direct is Map<String, dynamic> && direct['text'] is String) {
    return direct['text'] as String;
  }
  final choices = data['choices'];
  if (choices is! List || choices.isEmpty || choices.first is! Map) return '';
  final choice = Map<String, dynamic>.from(choices.first as Map);
  if (choice['text'] is String) return choice['text'] as String;
  final delta = choice['delta'];
  return delta is Map && delta['content'] is String
      ? delta['content'] as String
      : '';
}

bool _knownErrorCode(String code) => const {
      'invalid_request',
      'guardrail_blocked',
      'invalid_api_key',
      'insufficient_credits',
      'model_not_found',
      'rate_limit_exceeded',
      'tpm_limit_exceeded',
      'credit_check_failed',
      'service_unavailable',
    }.contains(code);
