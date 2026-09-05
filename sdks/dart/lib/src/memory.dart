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

class NRouterMemory {
  NRouterMemory([MemoryStore? store]) : _store = store ?? ArrayMemoryStore();

  final MemoryStore _store;

  static const _tenancyKeys = {
    'organizationid',
    'orgid',
    'teamid',
    'userid',
    'nrouterorg'
  };

  static const _roles = {'system', 'user', 'assistant', 'tool'};

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
          '$context: message must contain a valid role (system, user, assistant, tool)');
    }
    return message;
  }

  Future<void> add(ChatMessage message) async {
    final clean = _validateMessage(message, 'NRouterMemory.add');
    final current = await messages();
    current.add(clean);
    await _store.save(current);
  }

  Future<List<ChatMessage>> messages() async {
    final raw = await _store.load();
    return [
      for (var i = 0; i < raw.length; i++)
        _validateMessage(raw[i], 'MemoryStore.load()[$i]')
    ];
  }

  Future<void> clear() async {
    await _store.save([]);
  }
}
