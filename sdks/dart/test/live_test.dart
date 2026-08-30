import 'dart:io';

import 'package:nrouter/nrouter.dart';
import 'package:test/test.dart';

void main() {
  test(
    'live Claude messages stream returns billing metadata',
    () async {
      final client = NRouter(
        apiKey: Platform.environment['NROUTER_API_KEY']!,
        baseUrl: Platform.environment['NROUTER_BASE_URL'] ??
            'http://127.0.0.1:4000/v1',
      );
      try {
        final chunks = await client.messagesStream({
          'model': 'claude-haiku-4-5-20251001',
          'max_tokens': 2,
          'messages': [
            {'role': 'user', 'content': 'Reply OK'},
          ],
        }).toList();

        expect(chunks, isNotEmpty);
        expect(chunks.first.meta.requestId, isNotEmpty);
        // SSE response headers are committed before final usage is known, so
        // the gateway cannot add the post-stream cost retroactively. Unknown
        // must remain null; rendering it as zero would report a free request.
        expect(chunks.first.meta.isPriced, isFalse);
        expect(chunks.first.meta.cost, isNull);
      } finally {
        client.close();
      }
    },
    skip: Platform.environment['NROUTER_LIVE'] == '1'
        ? false
        : 'set NROUTER_LIVE=1 for the billed local-gateway acceptance',
  );
}
