import Foundation

/// A single chat message in conversation memory, safe across concurrency boundaries.
public struct ChatMessage: @unchecked Sendable, ExpressibleByDictionaryLiteral {
    public var fields: [String: Any]

    public init(dictionaryLiteral elements: (String, Any)...) {
        var dict: [String: Any] = [:]
        for (k, v) in elements {
            dict[k] = v
        }
        self.fields = dict
    }

    public init(_ fields: [String: Any]) {
        self.fields = fields
    }

    public subscript(key: String) -> Any? {
        get { fields[key] }
        set { fields[key] = newValue }
    }

    public var keys: Dictionary<String, Any>.Keys {
        fields.keys
    }
}

/// Protocol for custom memory storage backends.
public protocol MemoryStore: Sendable {
    func load() async throws -> [ChatMessage]
    func save(_ messages: [ChatMessage]) async throws
}

/// In-memory thread-safe implementation of `MemoryStore`.
public actor ArrayMemoryStore: MemoryStore {
    private var messages: [ChatMessage]

    public init(seed: [ChatMessage] = []) {
        self.messages = seed
    }

    public func load() async throws -> [ChatMessage] {
        return messages
    }

    public func save(_ messages: [ChatMessage]) async throws {
        self.messages = messages
    }
}

/// Manages conversation history with tenancy validation.
public struct NRouterMemory: Sendable {
    private let store: any MemoryStore

    private static let tenancyKeys: Set<String> = [
        "organizationid", "orgid", "teamid", "userid", "nrouterorg"
    ]

    public init(store: any MemoryStore = ArrayMemoryStore()) {
        self.store = store
    }

    private static func normalizeKey(_ key: String) -> String {
        return key.lowercased()
            .replacingOccurrences(of: "_", with: "")
            .replacingOccurrences(of: "-", with: "")
    }

    private static func validateMessage(_ message: ChatMessage, context: String) throws -> ChatMessage {
        for key in message.keys {
            let norm = normalizeKey(key)
            if tenancyKeys.contains(norm) {
                throw NRouterError.configuration("\(context): message contains forbidden tenancy key '\(key)'")
            }
        }
        guard let role = message["role"] as? String,
              ["system", "user", "assistant", "tool"].contains(role) else {
            throw NRouterError.configuration("\(context): message must contain a valid role (system, user, assistant, tool)")
        }
        return message
    }

    public func add(_ message: ChatMessage) async throws {
        let clean = try Self.validateMessage(message, context: "NRouterMemory.add")
        var current = try await self.messages()
        current.append(clean)
        try await store.save(current)
    }

    public func messages() async throws -> [ChatMessage] {
        let raw = try await store.load()
        var out: [ChatMessage] = []
        for (i, msg) in raw.enumerated() {
            let clean = try Self.validateMessage(msg, context: "MemoryStore.load()[\(i)]")
            out.append(clean)
        }
        return out
    }

    public func clear() async throws {
        try await store.save([])
    }
}
