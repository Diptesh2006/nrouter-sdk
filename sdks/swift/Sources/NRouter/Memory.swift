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

/// Prune messages to the most recent maxMessages, preserving index 0 system/developer message.
public func slidingWindow(messages: [ChatMessage], maxMessages: Int, preserveSystem: Bool = true) -> [ChatMessage] {
    if maxMessages <= 0 {
        return []
    }
    if messages.count <= maxMessages {
        return messages
    }
    if preserveSystem, let first = messages.first,
       let role = first["role"] as? String,
       role == "system" || role == "developer" {
        if maxMessages == 1 {
            return [messages[messages.count - 1]]
        }
        let tailCount = maxMessages - 1
        var out = [first]
        out.append(contentsOf: messages.suffix(tailCount))
        return out
    }
    return Array(messages.suffix(maxMessages))
}

/// Manages conversation history with tenancy validation and optional windowing.
public struct NRouterMemory: Sendable {
    private let store: any MemoryStore

    private static let tenancyKeys: Set<String> = [
        "organizationid", "orgid", "teamid", "userid", "nrouterorg"
    ]

    private static let validRoles: Set<String> = [
        "system", "user", "assistant", "tool", "developer"
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
        guard let role = message["role"] as? String, validRoles.contains(role) else {
            throw NRouterError.configuration("\(context): message must contain a valid role (system, user, assistant, tool, developer)")
        }

        let content = message["content"]
        let hasToolCalls = message["tool_calls"] != nil
        let isNilOrNSNull = content == nil || content is NSNull
        if isNilOrNSNull {
            if !hasToolCalls && role != "assistant" {
                throw NRouterError.configuration("\(context): content must be a string or array of parts")
            }
        } else if !(content is String) && !(content is [Any]) {
            throw NRouterError.configuration("\(context): content must be a string or array of parts")
        }
        return message
    }

    public func add(_ message: ChatMessage) async throws {
        let clean = try Self.validateMessage(message, context: "NRouterMemory.add")
        var current = try await self.messages()
        current.append(clean)
        try await store.save(current)
    }

    public func messages(maxMessages: Int? = nil, preserveSystem: Bool = true) async throws -> [ChatMessage] {
        let raw = try await store.load()
        var out: [ChatMessage] = []
        for (i, msg) in raw.enumerated() {
            let clean = try Self.validateMessage(msg, context: "MemoryStore.load()[\(i)]")
            out.append(clean)
        }
        if let max = maxMessages, max > 0 {
            return slidingWindow(messages: out, maxMessages: max, preserveSystem: preserveSystem)
        }
        return out
    }

    public func clear() async throws {
        try await store.save([])
    }
}
