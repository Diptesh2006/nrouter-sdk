import 'package:nrouter/nrouter.dart';

void main() async {
  // 1. Initialize the client with an nRouter API key.
  // In a Flutter mobile/web app, pass a short-lived key minted on your backend.
  final client = NRouter(apiKey: 'sk-nrouter-example-key');

  try {
    // 2. Chat Completion
    final response = await client.chatCompletions({
      'model': 'claude-sonnet-4-5-20250929',
      'messages': [
        {'role': 'user', 'content': 'Hello, nRouter!'},
      ],
    });

    print('Response: ${response.body['choices']}');

    // 3. Metadata and Cost tracking (from x-nr-* headers)
    final meta = response.meta;
    print('Request ID: ${meta.requestId}');
    print('Model: ${meta.model}');
    if (meta.isPriced) {
      print('Cost: \$${meta.cost}');
    } else {
      print('Cost: unpriced (${meta.costStatus})');
    }

    // 4. Streaming Text Generation
    print('\nStreaming messages:');
    final stream = client.messagesStream({
      'model': 'claude-haiku-4-5-20251001',
      'max_tokens': 128,
      'messages': [
        {'role': 'user', 'content': 'Count from 1 to 5.'},
      ],
    });

    await for (final chunk in stream) {
      print(chunk.delta);
    }
  } on NRouterGuardrailBlockedError catch (e) {
    print('Guardrail blocked: ${e.message}');
  } on NRouterCreditError catch (e) {
    print('Insufficient credits: ${e.message}');
  } on NRouterRateLimitError catch (e) {
    print('Rate limit exceeded: ${e.message} (source: ${e.body?.limitSource})');
  } on NRouterError catch (e) {
    print('nRouter error: ${e.message}');
  } finally {
    // 5. Close client resources when finished
    client.close();
  }
}
