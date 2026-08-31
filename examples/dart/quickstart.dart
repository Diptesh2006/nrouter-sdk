import 'dart:io';
import 'package:nrouter/nrouter.dart';

void main() async {
  final apiKey = Platform.environment['NROUTER_API_KEY'];
  if (apiKey == null) {
    stderr.writeln('Set NROUTER_API_KEY before running.');
    exit(1);
  }

  final client = NRouter(apiKey: apiKey);
  final result = await client.chatCompletions({
    'model': 'claude-sonnet-4-5-20250929',
    'messages': [
      {'role': 'user', 'content': 'Hello, nRouter from Dart!'}
    ],
  });

  print(result.body['choices']);
  print('Request ID: ${result.meta.requestId}');
  client.close();
}
