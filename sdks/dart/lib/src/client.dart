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
      throw const NRouterTransportError('No nRouter API key was supplied.');
    }
    if (!apiKey.startsWith(keyPrefix)) {
      throw const NRouterTransportError(
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

  /// `GET /models` — what this key is allowed to route to.
  Future<NRouterResponse> models() => get('/models');

  /// Any `POST` path under the gateway's `/v1` root.
  Future<NRouterResponse> post(String path, Map<String, dynamic> body) =>
      _send('POST', path, body);

  /// Any `GET` path under the gateway's `/v1` root.
  Future<NRouterResponse> get(String path) => _send('GET', path, null);

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
    Map<String, dynamic> parsed;
    try {
      final decoded = jsonDecode(response.body);
      parsed = decoded is Map<String, dynamic> ? decoded : <String, dynamic>{};
    } on FormatException {
      parsed = <String, dynamic>{};
    }

    if (response.statusCode >= 200 && response.statusCode < 300) {
      return NRouterResponse(
        body: parsed,
        meta: meta,
        statusCode: response.statusCode,
      );
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
