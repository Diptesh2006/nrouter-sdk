import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:nrouter/nrouter.dart';
import 'package:test/test.dart';

/// The gateway contract this SDK must keep, asserted against the values in
/// `spec/nrouter-sdk-spec.json`.
void main() {
  group('constants', () {
    test('match the spec', () {
      expect(NRouter.defaultBaseUrl, 'https://api.nrouter.ai/v1');
      expect(NRouter.envKey, 'NROUTER_API_KEY');
      expect(NRouter.keyPrefix, 'sk-nrouter-');
    });

    test('every spec header is read', () {
      const expected = [
        'x-nr-request-id', 'x-nr-request-cost', 'x-nr-cost-status', 'x-nr-model',
        'x-nr-input-tokens', 'x-nr-output-tokens', 'x-nr-total-tokens',
        'x-nr-cache-read-tokens', 'x-nr-cache-write-tokens', 'x-nr-limit-source',
        'x-nr-auth-reason', 'x-nr-response-cache', 'x-nr-response-cache-age',
      ];
      expect(NRouterResponseMeta.headerNames.length, 13);
      for (final name in expected) {
        expect(NRouterResponseMeta.headerNames, contains(name),
            reason: '$name is not read by this SDK');
      }
    });
  });

  group('error mapping', () {
    NRouterError build(String code) => NRouterError.fromCode(
          NRouterErrorBody(message: 'boom', code: code),
        );

    test('each gateway code maps to its type', () {
      expect(build('invalid_request'), isA<NRouterRequestError>());
      expect(build('guardrail_blocked'), isA<NRouterGuardrailBlockedError>());
      expect(build('invalid_api_key'), isA<NRouterAuthenticationError>());
      expect(build('insufficient_credits'), isA<NRouterCreditError>());
      expect(build('model_not_found'), isA<NRouterNotFoundError>());
      expect(build('rate_limit_exceeded'), isA<NRouterRateLimitError>());
      expect(build('tpm_limit_exceeded'), isA<NRouterRateLimitError>());
      expect(build('credit_check_failed'), isA<NRouterServiceError>());
      expect(build('service_unavailable'), isA<NRouterServiceError>());
    });

    test('a codeless 400 is split on the message', () {
      // The gateway's MAIN error path emits {"error":{"type","message"}} with
      // no code, so this is the ordinary shape. Calling every codeless 400 a
      // request error makes NRouterGuardrailBlockedError unreachable.
      expect(
        NRouterError.fromCode(
          const NRouterErrorBody(message: "blocked by guardrail 'pii'", status: 400),
        ),
        isA<NRouterGuardrailBlockedError>(),
      );
      expect(
        NRouterError.fromCode(
          const NRouterErrorBody(message: 'invalid request: bad shape', status: 400),
        ),
        isA<NRouterRequestError>(),
      );
    });

    test('the real gateway envelope classifies without a code', () {
      // Byte-for-byte what GatewayError::into_response emits.
      final body = NRouter.errorBodyFrom(
        400,
        {'error': {'type': 'gateway_error', 'message': "blocked by guardrail 'pii'"}},
        const NRouterResponseMeta(),
      );
      expect(body.code, isNull, reason: 'the gateway sends no code on this path');
      expect(NRouterError.fromCode(body), isA<NRouterGuardrailBlockedError>());
    });

    test('a codeless 402 separates a budget ceiling from a shortfall', () {
      // Two of the three 402s are budget ceilings, whose fix is the OPPOSITE
      // of a shortfall's.
      expect(
        NRouterError.fromCode(
          const NRouterErrorBody(message: 'budget exceeded: spend 5.00', status: 402),
        ),
        isA<NRouterBudgetExceededError>(),
      );
      expect(
        NRouterError.fromCode(
          const NRouterErrorBody(message: 'insufficient credits', status: 402),
        ),
        isA<NRouterCreditError>(),
      );
    });

    test('a codeless 404 is only model_not_found when it names a model', () {
      expect(
        NRouterError.fromCode(
          const NRouterErrorBody(message: "model 'x' not found", status: 404),
        ),
        isA<NRouterNotFoundError>(),
      );
      // A missing video job or MCP server is also a 404.
      expect(
        NRouterError.fromCode(
          const NRouterErrorBody(message: 'unknown video job', status: 404),
        ),
        isA<NRouterOtherError>(),
      );
    });

    test('an unknown code is never reclassified', () {
      expect(build('some_future_code'), isA<NRouterOtherError>());
    });

    test('only transient failures are retryable', () {
      for (final code in [
        'rate_limit_exceeded',
        'service_unavailable',
        'credit_check_failed',
      ]) {
        expect(build(code).isRetryable, isTrue, reason: code);
      }
      for (final code in [
        'invalid_request',
        'guardrail_blocked',
        'invalid_api_key',
        'insufficient_credits',
        'model_not_found',
      ]) {
        expect(build(code).isRetryable, isFalse,
            reason: '$code must not be advertised as retryable');
      }
      expect(const NRouterTransportError('dns').isRetryable, isTrue);
      // A local configuration failure is PERMANENT. Marking it retryable makes
      // a caller's retry loop spin forever without ever sending.
      expect(const NRouterConfigurationError('no key').isRetryable, isFalse);
    });
  });

  group('response metadata', () {
    test('an unpriced response reports no cost rather than zero', () {
      final meta = NRouterResponseMeta.fromHeaders({
        'x-nr-cost-status': 'unpriced',
        'x-nr-request-id': 'req_1',
      });
      expect(meta.cost, isNull, reason: 'unpriced must not become a number');
      expect(meta.isPriced, isFalse);
      expect(meta.requestId, 'req_1');
    });

    test('a priced response parses its numbers', () {
      final meta = NRouterResponseMeta.fromHeaders({
        'x-nr-request-cost': '0.00042',
        'x-nr-cost-status': 'exact',
        'x-nr-input-tokens': '11',
        'x-nr-response-cache': 'hit',
        'x-nr-response-cache-age': '7',
      });
      expect(meta.cost, 0.00042);
      expect(meta.isPriced, isTrue);
      expect(meta.inputTokens, 11);
      expect(meta.responseCache, 'hit');
      expect(meta.responseCacheAge, 7);
    });
  });

  group('key handling', () {
    test('a key without the prefix is refused before any request', () {
      expect(() => NRouter(apiKey: 'sk-openai-nope'),
          throwsA(isA<NRouterConfigurationError>()));
      expect(() => NRouter(apiKey: ''),
          throwsA(isA<NRouterConfigurationError>()));
      expect(NRouter.validateApiKey('sk-nrouter-abc'), 'sk-nrouter-abc');
    });

    test('toString never prints the api key', () {
      // A logged client must be useful without being dangerous (Rule #5).
      final rendered =
          NRouter(apiKey: 'sk-nrouter-SECRET123').toString();
      expect(rendered, isNot(contains('SECRET123')));
      expect(rendered, contains('sk-nrouter-...T123'));
    });

    test('a trailing slash on the base URL is normalised', () {
      final client = NRouter(
        apiKey: 'sk-nrouter-abc',
        baseUrl: 'https://api.nrouter.ai/v1/',
      );
      expect(client.baseUrl, 'https://api.nrouter.ai/v1');
    });
  });

  group('over the wire', () {
    test('a call carries the key and returns the gateway metadata', () async {
      late http.Request seen;
      final mock = MockClient((request) async {
        seen = request;
        return http.Response(
          jsonEncode({'choices': []}),
          200,
          headers: {
            'content-type': 'application/json',
            'x-nr-request-id': 'req_42',
            'x-nr-request-cost': '0.00042',
            'x-nr-cost-status': 'exact',
            'x-nr-input-tokens': '11',
          },
        );
      });

      final client = NRouter(apiKey: 'sk-nrouter-test', httpClient: mock);
      final result = await client.chatCompletions({'model': 'claude-sonnet-4-5'});

      expect(seen.headers['Authorization'], 'Bearer sk-nrouter-test');
      expect(seen.url.path, '/v1/chat/completions');
      expect(result.meta.requestId, 'req_42');
      expect(result.meta.cost, 0.00042);
      expect(result.meta.inputTokens, 11);
    });

    test('a non-JSON 2xx refuses instead of reporting an empty success',
        () async {
      // /v1/audio/speech returns audio. Decoded as JSON it becomes {} — the
      // caller is billed and receives nothing, while the call reports 200.
      final mock = MockClient((request) async => http.Response(
            'binary-audio',
            200,
            headers: {'content-type': 'audio/mpeg', 'x-nr-request-cost': '0.004'},
          ));
      final client = NRouter(apiKey: 'sk-nrouter-test', httpClient: mock);
      await expectLater(
        client.post('/audio/speech', {}),
        throwsA(isA<NRouterTransportError>()),
      );
    });

    test('bytes returns the raw body a non-JSON endpoint sent', () async {
      final mock = MockClient((request) async => http.Response(
            'binary-audio',
            200,
            headers: {'content-type': 'audio/mpeg', 'x-nr-request-cost': '0.004'},
          ));
      final client = NRouter(apiKey: 'sk-nrouter-test', httpClient: mock);
      final raw = await client.bytes('/audio/speech', {});
      expect(String.fromCharCodes(raw.bytes), 'binary-audio');
      expect(raw.meta.cost, 0.004);
    });

    test('a 2xx with unparseable JSON is a failure, not an empty success',
        () async {
      // Truncated mid-stream. The request was BILLED; returning {} reports
      // success with nothing in it.
      final mock = MockClient((request) async => http.Response(
            '{"choices":[{"message":',
            200,
            headers: {
              'content-type': 'application/json',
              'x-nr-request-cost': '0.004',
            },
          ));
      final client = NRouter(apiKey: 'sk-nrouter-test', httpClient: mock);
      await expectLater(
        client.chatCompletions({}),
        throwsA(isA<NRouterTransportError>()),
      );
    });

    test('audio transcriptions sends multipart with a named file part',
        () async {
      // The gateway requires multipart/form-data with a binary `file` here;
      // sent as JSON the endpoint is unreachable.
      late http.BaseRequest seen;
      String body = '';
      final mock = MockClient.streaming((request, bodyStream) async {
        seen = request;
        body = String.fromCharCodes(await bodyStream.toBytes());
        return http.StreamedResponse(
          Stream.value(utf8.encode('{"text":"hello"}')),
          200,
          headers: {'content-type': 'application/json'},
        );
      });

      final client = NRouter(apiKey: 'sk-nrouter-test', httpClient: mock);
      final result = await client.audioTranscriptions(
        utf8.encode('fake-audio'),
        'speech.mp3',
        fields: {'model': 'whisper-1'},
      );

      expect(seen.headers['content-type'], startsWith('multipart/form-data'));
      expect(body, contains('name="file"'));
      // The extension is load-bearing: providers pick their decoder from it.
      expect(body, contains('speech.mp3'));
      expect(body, contains('name="model"'));
      expect(body, contains('fake-audio'));
      expect(result.body['text'], 'hello');
    });

    test('a gateway error becomes its typed exception with metadata', () async {
      final mock = MockClient((request) async => http.Response(
            jsonEncode({
              'error': {'message': 'slow down', 'code': 'tpm_limit_exceeded'}
            }),
            429,
            headers: {
              'content-type': 'application/json',
              'x-nr-request-id': 'req_9',
              'x-nr-limit-source': 'tpm',
            },
          ));

      final client = NRouter(apiKey: 'sk-nrouter-test', httpClient: mock);

      await expectLater(
        client.chatCompletions({}),
        throwsA(
          isA<NRouterRateLimitError>()
              .having((e) => e.body?.code, 'code', 'tpm_limit_exceeded')
              .having((e) => e.body?.limitSource, 'limitSource', 'tpm')
              .having((e) => e.body?.requestId, 'requestId', 'req_9')
              .having((e) => e.isRetryable, 'isRetryable', isTrue),
        ),
      );
    });

    test('a bare error envelope still yields a typed error with its code',
        () async {
      // A proxy that unwraps `error` must not downgrade a typed error. Assert
      // the CODE, not just the type — the HTTP-status fallback would produce
      // the same type for a 402 even if the bare envelope were ignored.
      final mock = MockClient((request) async => http.Response(
            jsonEncode({'message': 'no credits', 'code': 'insufficient_credits'}),
            402,
            headers: {'content-type': 'application/json'},
          ));

      final client = NRouter(apiKey: 'sk-nrouter-test', httpClient: mock);
      await expectLater(
        client.chatCompletions({}),
        throwsA(
          isA<NRouterCreditError>()
              .having((e) => e.body?.code, 'code', 'insufficient_credits')
              .having((e) => e.body?.message, 'message', 'no credits'),
        ),
      );
    });

    test('named helpers cover every remaining gateway operation', () async {
      late http.Request seen;
      final mock = MockClient((request) async {
        seen = request;
        final binary = request.url.path == '/v1/audio/speech' ||
            request.url.path.endsWith('/content');
        return http.Response(
          binary ? 'bytes' : '{}',
          200,
          headers: {'content-type': binary ? 'application/octet-stream' : 'application/json'},
        );
      });
      final client = NRouter(apiKey: 'sk-nrouter-test', httpClient: mock);

      await client.completions({});
      expect(seen.url.path, '/v1/completions');
      await client.imagesGenerations({});
      expect(seen.url.path, '/v1/images/generations');
      await client.countTokens({});
      expect(seen.url.path, '/v1/messages/count_tokens');
      await client.model('provider/model one');
      expect(seen.url.toString(), contains('/v1/models/provider/model%20one'));
      await client.createVideo({});
      expect(seen.url.path, '/v1/videos');
      await client.retrieveVideo('video/one');
      expect(seen.url.toString(), contains('/v1/videos/video%2Fone'));
      await client.audioSpeech({});
      expect(seen.url.path, '/v1/audio/speech');
      await client.downloadVideoContent('video/one');
      expect(seen.url.toString(), contains('/v1/videos/video%2Fone/content'));
    });
  });
}
