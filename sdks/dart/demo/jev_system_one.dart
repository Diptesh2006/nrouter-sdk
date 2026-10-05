import 'dart:io';
import 'package:nrouter/nrouter.dart';

Future<void> main() async {
  final apiKey = Platform.environment['NROUTER_API_KEY'];
  if (apiKey == null || apiKey.isEmpty) {
    stderr.writeln('Set NROUTER_API_KEY before running.');
    exitCode = 1;
    return;
  }

  final client = NRouter(apiKey: apiKey);
  try {
    final response = await client.chatCompletions({
      'model': 'typesafe/jev',
      'temperature': 0,
      'max_tokens': 128,
      'messages': [
        {'role': 'system', 'content': 'Classify the incident. Return JSON only with priority, queue, and summary.'},
        {'role': 'user', 'content': 'Production payment requests return HTTP 500 in two regions.'},
      ],
    });
    final choices = response.body['choices'] as List<dynamic>;
    final message = choices.first['message'] as Map<String, dynamic>;
    print('Decision: ${message['content']}');
    print('Request ID: ${response.meta.requestId}');
    print('Served model: ${response.meta.model}');
  } finally {
    client.close();
  }
}
