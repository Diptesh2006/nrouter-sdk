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

  /// Build a client. The key is validated up front so a malformed one fails
  /// here rather than as a 401 that reads like a revoked credential.
  NRouter({
    required String apiKey,
    String baseUrl = defaultBaseUrl,
    http.Client? httpClient,
  })  : _apiKey = validateApiKey(apiKey),
        baseUrl = baseUrl.endsWith('/')
            ? baseUrl.substring(0, baseUrl.length - 1)
            : baseUrl,
        _http = httpClient ?? http.Client(),
        _ownsClient = httpClient == null;

  final String _apiKey;
  final http.Client _http;
  final bool _ownsClient;

  /// The gateway this client talks to, with any trailing slash removed.
  final String baseUrl;

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

  /// `POST /embeddings`
  Future<NRouterResponse> embeddings(Map<String, dynamic> body) =>
      post('/embeddings', body);

  /// `POST /messages` — the Anthropic wire format the gateway also serves.
  Future<NRouterResponse> messages(Map<String, dynamic> body) =>
      post('/messages', body);

  /// `POST /responses`
  Future<NRouterResponse> responses(Map<String, dynamic> body) =>
      post('/responses', body);

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
      final streamed = await _http.send(request);
      response = await http.Response.fromStream(streamed);
    } on Exception catch (e) {
      throw NRouterTransportError(e.toString());
    }

    final meta = NRouterResponseMeta.fromHeaders(response.headers);
    if (response.statusCode >= 200 && response.statusCode < 300) {
      final decoded = jsonDecode(response.body);
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
  Future<({List<int> bytes, NRouterResponseMeta meta, int statusCode})> bytes(
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

    http.Response response;
    try {
      response = body == null
          ? await _http.get(uri, headers: headers)
          : await _http.post(uri, headers: headers, body: jsonEncode(body));
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
      response = method == 'GET'
          ? await _http.get(uri, headers: headers)
          : await _http.post(uri, headers: headers, body: jsonEncode(body));
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
