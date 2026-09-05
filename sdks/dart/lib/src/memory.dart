import 'errors.dart';

typedef ChatMessage = Map<String, dynamic>;

abstract class MemoryStore {
  Future<List<ChatMessage>> load();
  Future<void> save(List<ChatMessage> messages);
}

class ArrayMemoryStore implements MemoryStore {
  ArrayMemoryStore([List<ChatMessage>? seed])
      : _messages = seed != null ? List.from(seed) : [];

  final List<ChatMessage> _messages;

  @override
  Future<List<ChatMessage>> load() async => List.from(_messages);

  @override
  Future<void> save(List<ChatMessage> messages) async {
    _messages
      ..clear()
      ..addAll(messages);
  }
}

/// Prunes a list of messages to the most recent maxMessages, preserving index 0
/// system/developer message by default.
List<ChatMessage> slidingWindow(
  List<ChatMessage> messages,
  int maxMessages, {
  bool preserveSystem = true,
}) {
  if (maxMessages <= 0) {
    return [];
  }
  if (messages.length <= maxMessages) {
    return List.from(messages);
  }
  if (preserveSystem && messages.isNotEmpty) {
    final role = messages.first['role'];
    if (role == 'system' || role == 'developer') {
      if (maxMessages == 1) {
        return [messages.last];
      }
      final tailCount = maxMessages - 1;
      return [
        messages.first,
        ...messages.sublist(messages.length - tailCount),
      ];
    }
  }
  return messages.sublist(messages.length - maxMessages);
}

class NRouterMemory {
  NRouterMemory([MemoryStore? store]) : _store = store ?? ArrayMemoryStore();

  final MemoryStore _store;
  Future<void> _chain = Future.value();

  static const _tenancyKeys = {
    'organizationid',
    'orgid',
    'teamid',
    'userid',
    'nrouterorg'
  };

  static const _roles = {'system', 'user', 'assistant', 'tool', 'developer'};

  static String _normalizeKey(String key) =>
      key.toLowerCase().replaceAll('_', '').replaceAll('-', '');

  static ChatMessage _validateMessage(ChatMessage message, String context) {
    for (final key in message.keys) {
      final norm = _normalizeKey(key);
      if (_tenancyKeys.contains(norm)) {
        throw NRouterConfigurationError(
            '$context: message contains forbidden tenancy key "$key"');
      }
    }
    final role = message['role'];
    if (role is! String || !_roles.contains(role)) {
      throw NRouterConfigurationError(
          '$context: message must contain a valid role (system, user, assistant, tool, developer)');
    }
    final content = message['content'];
    final toolCalls = message['tool_calls'];
    final hasToolCalls = toolCalls is List && toolCalls.isNotEmpty;
    if (content == null) {
      if (!hasToolCalls && role != 'assistant') {
        throw NRouterConfigurationError(
            '$context: message content must be a string or list of content parts');
      }
    } else if (content is! String && content is! List) {
      throw NRouterConfigurationError(
          '$context: message content must be a string or list of content parts');
    }
    return message;
  }

  Future<void> add(ChatMessage message) {
    final clean = _validateMessage(message, 'NRouterMemory.add');
    _chain = _chain.then((_) async {
      final current = await _loadAndValidate();
      current.add(clean);
      await _store.save(current);
    });
    return _chain;
  }

  Future<List<ChatMessage>> _loadAndValidate() async {
    final raw = await _store.load();
    return [
      for (var i = 0; i < raw.length; i++)
        _validateMessage(raw[i], 'MemoryStore.load()[$i]')
    ];
  }

  Future<List<ChatMessage>> messages({
    int? maxMessages,
    bool preserveSystem = true,
  }) async {
    final list = await _loadAndValidate();
    if (maxMessages != null && maxMessages > 0) {
      return slidingWindow(list, maxMessages, preserveSystem: preserveSystem);
    }
    return list;
  }

  Future<void> clear() {
    _chain = _chain.then((_) => _store.save([]));
    return _chain;
  }
}
