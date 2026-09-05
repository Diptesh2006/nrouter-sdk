import 'dart:async';
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

    test('usesMessagesWire', () {
      expect(NRouter.usesMessagesWire('claude-3-5-sonnet-20241022'), isTrue);
      expect(NRouter.usesMessagesWire('anthropic/claude-3-haiku'), isTrue);
      expect(NRouter.usesMessagesWire('my-model', provider: 'anthropic'), isTrue);
      expect(NRouter.usesMessagesWire('gpt-4o'), isFalse);
      expect(NRouter.usesMessagesWire('meta-llama/llama-3'), isFalse);
    });

    test('every spec header is read', () {
      const expected = [
        'x-nr-request-id',
        'x-nr-request-cost',
        'x-nr-cost-status',
        'x-nr-model',
        'x-nr-input-tokens',
        'x-nr-output-tokens',
        'x-nr-total-tokens',
        'x-nr-cache-read-tokens',
        'x-nr-cache-write-tokens',
        'x-nr-limit-source',
        'x-nr-auth-reason',
        'x-nr-response-cache',
        'x-nr-response-cache-age',
        'x-nr-budget-warning',
        'x-nr-guardrails',
      ];
      expect(NRouterResponseMeta.headerNames.length, 15);
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
          const NRouterErrorBody(
              message: "blocked by guardrail 'pii'", status: 400),
        ),
        isA<NRouterGuardrailBlockedError>(),
      );
      expect(
        NRouterError.fromCode(
          const NRouterErrorBody(
              message: 'invalid request: bad shape', status: 400),
        ),
        isA<NRouterRequestError>(),
      );
    });

    test('the real gateway envelope classifies without a code', () {
      // Byte-for-byte what GatewayError::into_response emits.
      final body = NRouter.errorBodyFrom(
        400,
        {
          'error': {
            'type': 'gateway_error',
            'message': "blocked by guardrail 'pii'"
          }
        },
        const NRouterResponseMeta(),
      );
      expect(body.code, isNull,
          reason: 'the gateway sends no code on this path');
      expect(NRouterError.fromCode(body), isA<NRouterGuardrailBlockedError>());
    });

    test('a codeless 402 separates a budget ceiling from a shortfall', () {
      // Two of the three 402s are budget ceilings, whose fix is the OPPOSITE
      // of a shortfall's.
      expect(
        NRouterError.fromCode(
          const NRouterErrorBody(
              message: 'budget exceeded: spend 5.00', status: 402),
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
        'x-nr-budget-warning': 'org soft_budget 80.00/100.00',
        'x-nr-guardrails': 'pass',
      });
      expect(meta.cost, 0.00042);
      expect(meta.isPriced, isTrue);
      expect(meta.inputTokens, 11);
      expect(meta.responseCache, 'hit');
      expect(meta.responseCacheAge, 7);
      expect(meta.budgetWarning, 'org soft_budget 80.00/100.00');
      expect(meta.guardrails, 'pass');
    });
  });

  group('key handling', () {
    test('a key without the prefix is refused before any request', () {
      expect(() => NRouter(apiKey: 'sk-openai-nope'),
          throwsA(isA<NRouterConfigurationError>()));
      expect(
          () => NRouter(apiKey: ''), throwsA(isA<NRouterConfigurationError>()));
      expect(NRouter.validateApiKey('sk-nrouter-abc'), 'sk-nrouter-abc');
    });

    test('toString never prints the api key', () {
      // A logged client must be useful without being dangerous (Rule #5).
      final rendered = NRouter(apiKey: 'sk-nrouter-SECRET123').toString();
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

    test('cleartext is limited to loopback development gateways and rejects credentials', () {
      for (final allowed in [
        'http://127.0.0.1:4000/v1',
        'http://[::1]:4000/v1',
        'http://localhost:4000/v1',
        'https://api.nrouter.ai/v1',
      ]) {
        expect(() => NRouter(apiKey: 'sk-nrouter-abc', baseUrl: allowed), returnsNormally);
      }

      for (final refused in [
        'http://api.nrouter.ai/v1',
        'http://192.0.2.10:4000/v1',
        'ftp://127.0.0.1/v1',
        'https://user:pass@api.nrouter.ai/v1',
        'not-a-url',
      ]) {
        expect(
          () => NRouter(apiKey: 'sk-nrouter-abc', baseUrl: refused),
          throwsA(isA<NRouterConfigurationError>()),
        );
      }
    });
  });

  group('transport deadlines', () {
    test('the declared defaults are the ones a client gets', () {
      expect(NRouter.defaultTimeout, const Duration(seconds: 600));
      expect(NRouter.defaultStreamTimeout, const Duration(seconds: 180));
      expect(NRouter.defaultBodyIdleTimeout, const Duration(seconds: 130));

      final client = NRouter(apiKey: 'sk-nrouter-test');
      expect(client.timeout, NRouter.defaultTimeout);
      expect(client.streamTimeout, NRouter.defaultStreamTimeout);
      expect(client.bodyIdleTimeout, NRouter.defaultBodyIdleTimeout);
      client.close();
    });

    test('post-header body stalls fail for binary and streaming responses',
        () async {
      for (final streaming in [false, true]) {
        final body = StreamController<List<int>>();
        final mock = MockClient.streaming((request, requestBody) async {
          await requestBody.drain<void>();
          return http.StreamedResponse(
            body.stream,
            200,
            headers: {
              'content-type':
                  streaming ? 'text/event-stream' : 'application/octet-stream',
            },
          );
        });
        final client = NRouter(
          apiKey: 'sk-nrouter-test',
          httpClient: mock,
          bodyIdleTimeout: const Duration(milliseconds: 75),
        );

        final stopwatch = Stopwatch()..start();
        final Future<void> call;
        if (streaming) {
          call = client.responsesStream({}).drain<void>();
          body.add(utf8.encode('data: {"delta":"first"}\n\n'));
        } else {
          call = client.bytes('/videos/v/content').then((_) {});
          body.add(utf8.encode('first'));
        }

        await expectLater(
          call.timeout(
            const Duration(seconds: 1),
            onTimeout: () => throw StateError(
              'post-header body stall was left unbounded',
            ),
          ),
          throwsA(isA<NRouterTransportError>()),
        );
        stopwatch.stop();
        expect(stopwatch.elapsed, lessThan(const Duration(seconds: 2)));
        await body.close();
      }

      final active = MockClient.streaming((request, requestBody) async {
        await requestBody.drain<void>();
        return http.StreamedResponse(
          () async* {
            for (var i = 0; i < 5; i++) {
              yield utf8.encode('data: {"delta":"$i"}\n\n');
              await Future<void>.delayed(const Duration(milliseconds: 50));
            }
            yield utf8.encode('data: [DONE]\n\n');
          }(),
          200,
          headers: {'content-type': 'text/event-stream'},
        );
      });
      final activeClient = NRouter(
        apiKey: 'sk-nrouter-test',
        httpClient: active,
        bodyIdleTimeout: const Duration(milliseconds: 150),
      );
      final stopwatch = Stopwatch()..start();
      final chunks = await activeClient.responsesStream({}).toList();
      stopwatch.stop();
      expect(chunks, hasLength(5));
      expect(stopwatch.elapsed, greaterThan(const Duration(milliseconds: 150)));
    });

    test('a buffered call that never answers fails instead of hanging',
        () async {
      // package:http applies NO timeout of its own, so without this bound the
      // future below never completes and the caller hangs forever.
      final mock = MockClient((request) async {
        await Future<void>.delayed(const Duration(seconds: 30));
        return http.Response('{}', 200);
      });
      final client = NRouter(
        apiKey: 'sk-nrouter-test',
        httpClient: mock,
        timeout: const Duration(seconds: 1),
      );

      await expectLater(
        client.chatCompletions({'model': 'gpt-5.4-mini'}),
        throwsA(
          isA<NRouterTransportError>().having(
            (e) => e.message,
            'message',
            allOf(contains('within 1s'),
                contains('may already have been billed')),
          ),
        ),
      );
    });

    test('an injected client keeps the caller timeout, not the SDK default',
        () async {
      // The injection point survives the change: `httpClient` cannot carry a
      // deadline (package:http's Client interface has none), so `timeout:` is
      // the separate knob — and a 1 s bound firing proves the 600 s default is
      // not silently in force behind the injected client.
      final stopwatch = Stopwatch()..start();
      final mock = MockClient((request) async {
        await Future<void>.delayed(const Duration(seconds: 30));
        return http.Response('{}', 200);
      });
      final client = NRouter(
        apiKey: 'sk-nrouter-test',
        httpClient: mock,
        timeout: const Duration(seconds: 1),
      );
      expect(client.timeout, const Duration(seconds: 1));

      await expectLater(
        client.models(),
        throwsA(isA<NRouterTransportError>()),
      );
      stopwatch.stop();
      expect(stopwatch.elapsed, lessThan(const Duration(seconds: 10)));
    });

    test('a stream body outlives the buffered ceiling', () async {
      // The property that keeps a paid response intact. `timeout` here is
      // shorter than the gap before the first token, so a whole-request ceiling
      // would sever a stream the customer is already being billed for. Only the
      // wait for RESPONSE HEADERS is bounded, by `streamTimeout`.
      final mock = MockClient.streaming((request, bodyStream) async {
        await bodyStream.drain<void>();
        return http.StreamedResponse(
          () async* {
            await Future<void>.delayed(const Duration(milliseconds: 300));
            yield utf8.encode(
                'event: content_block_delta\ndata: {"delta":{"type":"text_delta","text":"hello"}}\n\n');
            yield utf8.encode(
                'event: message_stop\ndata: {"type":"message_stop"}\n\n');
          }(),
          200,
          headers: {'content-type': 'text/event-stream'},
        );
      });
      final client = NRouter(
        apiKey: 'sk-nrouter-test',
        httpClient: mock,
        timeout: const Duration(milliseconds: 10),
        streamTimeout: const Duration(seconds: 5),
      );

      final chunks = await client.messagesStream({'model': 'claude'}).toList();

      expect(chunks.single.delta, 'hello');
    });

    test('a stream whose headers never arrive fails on streamTimeout',
        () async {
      final mock = MockClient.streaming((request, bodyStream) async {
        await bodyStream.drain<void>();
        await Future<void>.delayed(const Duration(seconds: 30));
        return http.StreamedResponse(const Stream.empty(), 200);
      });
      final client = NRouter(
        apiKey: 'sk-nrouter-test',
        httpClient: mock,
        streamTimeout: const Duration(seconds: 1),
      );

      await expectLater(
        client.messagesStream({'model': 'claude'}).drain<void>(),
        throwsA(
          isA<NRouterTransportError>().having(
            (e) => e.message,
            'message',
            contains('start streaming within 1s'),
          ),
        ),
      );
    });
  });

  group('over the wire', () {
    test('messagesStream parses incremental Anthropic deltas', () async {
      late http.BaseRequest seen;
      final mock = MockClient.streaming((request, bodyStream) async {
        await bodyStream.drain<void>();
        seen = request;
        return http.StreamedResponse(
          Stream.fromIterable([
            utf8.encode(
                'event: content_block_delta\ndata: {"type":"content_block_delta","delta":{"type":"text_delta","text":"hel'),
            utf8.encode(
                'lo"}}\n\nevent: message_stop\ndata: {"type":"message_stop"}\n\n'),
          ]),
          200,
          headers: {
            'content-type': 'text/event-stream',
            'x-nr-request-id': 'req_stream',
          },
        );
      });
      final client = NRouter(apiKey: 'sk-nrouter-test', httpClient: mock);

      final chunks = await client.messagesStream({'model': 'claude'}).toList();

      expect(seen.headers['Accept'], 'text/event-stream');
      expect(jsonDecode((seen as http.Request).body)['stream'], isTrue);
      expect(chunks, hasLength(1));
      expect(chunks.single.delta, 'hello');
      expect(chunks.single.meta.requestId, 'req_stream');
    });

    test('stream surfaces an in-band guardrail error as typed', () async {
      final mock = MockClient.streaming((request, bodyStream) async {
        await bodyStream.drain<void>();
        return http.StreamedResponse(
          Stream.value(utf8.encode(
            'event: error\ndata: {"error":{"type":"guardrail_blocked","message":"withheld by guardrail"}}\n\n',
          )),
          200,
          headers: {'content-type': 'text/event-stream'},
        );
      });
      final client = NRouter(apiKey: 'sk-nrouter-test', httpClient: mock);

      await expectLater(
        client.messagesStream({}).drain<void>(),
        throwsA(isA<NRouterGuardrailBlockedError>()),
      );
    });

    test('stream rejects EOF without a protocol terminator', () async {
      final mock = MockClient.streaming((request, bodyStream) async {
        await bodyStream.drain<void>();
        return http.StreamedResponse(
          Stream.value(utf8.encode('data: {"delta":"partial"}\n\n')),
          200,
          headers: {'content-type': 'text/event-stream'},
        );
      });
      final client = NRouter(apiKey: 'sk-nrouter-test', httpClient: mock);

      await expectLater(
        client.responsesStream({}).drain<void>(),
        throwsA(isA<NRouterTransportError>()),
      );
    });

    test('stream handles non-JSON keepalives, CR-only boundaries, and trailing event', () async {
      final mock = MockClient.streaming((request, bodyStream) async {
        await bodyStream.drain<void>();
        return http.StreamedResponse(
          Stream.value(utf8.encode(
            ': keep-alive\r\r'
            'data: ping\r\r'
            'data: {"choices":[{"delta":{"content":"  def foo():"}}]}\n\n'
            'data: [DONE]',
          )),
          200,
          headers: {'content-type': 'text/event-stream'},
        );
      });
      final client = NRouter(apiKey: 'sk-nrouter-test', httpClient: mock);

      final chunks = await client.chatCompletionsStream({}).toList();
      expect(chunks, hasLength(1));
      expect(chunks.single.delta, '  def foo():');
    });

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
      final result =
          await client.chatCompletions({'model': 'claude-sonnet-4-5'});

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
            headers: {
              'content-type': 'audio/mpeg',
              'x-nr-request-cost': '0.004'
            },
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
            headers: {
              'content-type': 'audio/mpeg',
              'x-nr-request-cost': '0.004'
            },
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
            jsonEncode(
                {'message': 'no credits', 'code': 'insufficient_credits'}),
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
          headers: {
            'content-type':
                binary ? 'application/octet-stream' : 'application/json'
          },
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

    test('NRouterMemory manages messages and rejects forbidden tenancy keys', () async {
      final mem = NRouterMemory();
      await mem.add({'role': 'user', 'content': 'Hello'});
      await mem.add({'role': 'assistant', 'content': 'Hi!'});
      final msgs = await mem.messages();
      expect(msgs.length, 2);

      expect(
        () => mem.add({'role': 'user', 'content': 'evil', 'organization_id': 'org_123'}),
        throwsA(isA<NRouterConfigurationError>()),
      );

      await mem.clear();
      final cleared = await mem.messages();
      expect(cleared.length, 0);

      // Developer and tool roles
      await mem.add({'role': 'developer', 'content': 'sys prompt'});
      await mem.add({'role': 'tool', 'content': 'tool res'});

      // Assistant with tool_calls and null content
      await mem.add({'role': 'assistant', 'content': null, 'tool_calls': [{'id': 'c1'}]});
      final updated = await mem.messages();
      expect(updated.length, 3);
      expect(updated[0]['role'], 'developer');
      expect(updated[1]['role'], 'tool');
      expect(updated[2]['role'], 'assistant');

      // Sliding window via messages
      final windowed = await mem.messages(maxMessages: 2, preserveSystem: true);
      expect(windowed.length, 2);
      expect(windowed[0]['role'], 'developer');
      expect(windowed[1]['role'], 'assistant');
    });

    test('slidingWindow helper prunes messages and preserves system', () {
      final msgs = [
        {'role': 'system', 'content': 'sys'},
        {'role': 'user', 'content': '1'},
        {'role': 'assistant', 'content': '2'},
        {'role': 'user', 'content': '3'},
        {'role': 'assistant', 'content': '4'},
      ];
      final pruned = slidingWindow(msgs, 3, preserveSystem: true);
      expect(pruned.length, 3);
      expect(pruned[0]['role'], 'system');
      expect(pruned[1]['content'], '3');
      expect(pruned[2]['content'], '4');
    });

    test('prompt helpers and system variable conflicts', () {
      final sel = promptTemplate('tpl_123', {'customer': 'Acme'});
      expect(sel.templateId, 'tpl_123');
      expect(sel.variables['customer'], 'Acme');

      expect(() => promptTemplate('   '), throwsA(isA<NRouterConfigurationError>()));

      final merged = sel.withVariables({'customer': 'Beta', 'user': 'Alice'});
      expect(merged.variables['customer'], 'Beta');
      expect(merged.variables['user'], 'Alice');

      final conflicts = systemVariableConflicts({
        'user_id': 'u1',
        'custom': 'val',
        'org_name': 'orgX',
        'timestamp': 123,
      });
      expect(conflicts, ['org_name', 'timestamp', 'user_id']);
    });

    test('renderPrompt safely interpolates variables', () {
      // 1. Whitespace tolerance & type formatting
      final tpl = 'Hello {{name}}! Age: {{  age  }}, active: {{ active }}.';
      final out = renderPrompt(tpl, {'name': 'Alice', 'age': 30, 'active': true});
      expect(out, 'Hello Alice! Age: 30, active: true.');

      // 2. Single-pass non-recursive expansion
      final tpl2 = 'Value: {{a}}';
      final out2 = renderPrompt(tpl2, {'a': '{{b}}', 'b': 'final'});
      expect(out2, 'Value: {{b}}');

      // 3. Metacharacter safety ($1, $&, escapes)
      final tpl3 = 'Price: {{price}}, Path: {{path}}';
      final out3 = renderPrompt(tpl3, {'price': r'$100', 'path': r'C:\test\1'});
      expect(out3, r'Price: $100, Path: C:\test\1');

      // 4. Non-strict preserves missing tokens
      final tpl4 = 'Greeting: {{hello}}, missing: {{world}}';
      final out4 = renderPrompt(tpl4, {'hello': 'hi'});
      expect(out4, 'Greeting: hi, missing: {{world}}');

      // 5. Strict throws error on missing tokens
      expect(
        () => renderPrompt(tpl4, {'hello': 'hi'}, const RenderPromptOptions(strict: true)),
        throwsA(isA<NRouterConfigurationError>()),
      );

      // 6. System variables override
      final tpl5 = 'Model: {{model}}, User: {{user}}';
      final out5 = renderPrompt(
        tpl5,
        {'model': 'caller-model', 'user': 'alice'},
        const RenderPromptOptions(systemVariables: {'model': 'claude-3-7-sonnet'}),
      );
      expect(out5, 'Model: claude-3-7-sonnet, User: alice');
    });


    test('media audio validation and video polling', () async {
      for (final fmt in ['mp3', 'opus', 'aac', 'flac', 'wav', 'pcm', 'MP3']) {
        expect(() => validateAudioFormat(fmt), returnsNormally);
      }
      expect(
        () => validateAudioFormat('unsupported_fmt'),
        throwsA(isA<NRouterConfigurationError>()),
      );

      final client = NRouter(
        apiKey: 'sk-nrouter-test',
        baseUrl: 'http://127.0.0.1:9/v1',
        httpClient: MockClient((req) async {
          return http.Response(
            '{"id":"vid_123","status":"completed"}',
            200,
            headers: {'content-type': 'application/json'},
          );
        }),
      );

      final video = await client.waitForVideo('vid_123', pollInterval: const Duration(milliseconds: 10));
      expect(video.body['status'], 'completed');
    });

    test('sampling policy adheres to Claude rules', () {
      expect(isClaudeModel('claude-3-opus'), isTrue);
      expect(isClaudeModel('sonnet-4-5'), isTrue);
      expect(isClaudeModel('haiku-3-5'), isTrue);
      expect(isClaudeModel('opus-4'), isTrue);
      expect(isClaudeModel('custom-model', 'anthropic'), isTrue);
      expect(isClaudeModel('gpt-4o', 'openai'), isFalse);

      final empty = buildSamplingParams(advanced: false, model: 'claude-3', temperature: 0.7, topP: 0.9);
      expect(empty.isEmpty, isTrue);

      final claude = buildSamplingParams(advanced: true, model: 'claude-3-opus', temperature: 0.7, topP: 0.9);
      expect(claude.containsKey('temperature'), isFalse);
      expect(claude['top_p'], 0.9);

      final gpt = buildSamplingParams(advanced: true, model: 'gpt-4o', provider: 'openai', temperature: 0.7, topP: 0.9);
      expect(gpt['temperature'], 0.7);
      expect(gpt['top_p'], 0.9);

      expect(
        () => buildSamplingParams(advanced: true, model: 'gpt-4o', temperature: -1.0),
        throwsA(isA<NRouterConfigurationError>()),
      );
      expect(
        () => buildSamplingParams(advanced: true, model: 'gpt-4o', topP: 1.5),
        throwsA(isA<NRouterConfigurationError>()),
      );

      final normalized = NRouter.normalizeAnthropicMessages({
        'model': 'claude-sonnet-4-5',
        'system': 'Initial system',
        'messages': [
          {'role': 'system', 'content': 'Turn system'},
          {'role': 'user', 'content': 'Hello'},
        ],
        'max_completion_tokens': 1024,
        'stop': 'Human:',
      });
      expect(normalized['system'], 'Initial system\n\nTurn system');
      expect((normalized['messages'] as List).length, 1);
      expect(normalized['max_tokens'], 1024);
      expect(normalized['stop_sequences'], ['Human:']);
    });
  });
}
