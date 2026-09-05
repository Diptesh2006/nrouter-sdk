/// nRouter SDK — one API key for models across six provider clouds.
///
/// Works unchanged in Flutter (mobile, desktop, web) and plain Dart.
library;

export 'src/client.dart'
    show NRouter, NRouterResponse, NRouterStreamChunk, NRouterBinaryResponse;
export 'src/errors.dart';
export 'src/meta.dart' show NRouterResponseMeta;
export 'src/memory.dart';
export 'src/prompts.dart';
export 'src/media.dart';
export 'src/sampling.dart';
