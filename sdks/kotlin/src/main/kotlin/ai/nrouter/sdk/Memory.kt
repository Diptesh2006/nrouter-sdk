package ai.nrouter.sdk

public typealias ChatMessage = Map<String, Any?>

public interface MemoryStore {
    public fun load(): List<ChatMessage>
    public fun save(messages: List<ChatMessage>)
}

public class ArrayMemoryStore(seed: List<ChatMessage> = emptyList()) : MemoryStore {
    private val messages = mutableListOf<ChatMessage>().apply { addAll(seed) }

    @Synchronized
    override fun load(): List<ChatMessage> = messages.toList()

    @Synchronized
    override fun save(messages: List<ChatMessage>) {
        this.messages.clear()
        this.messages.addAll(messages)
    }
}

public fun slidingWindow(
    messages: List<ChatMessage>,
    maxMessages: Int,
    preserveSystem: Boolean = true
): List<ChatMessage> {
    if (maxMessages <= 0) return emptyList()
    if (messages.size <= maxMessages) return messages.toList()
    if (preserveSystem && messages.isNotEmpty()) {
        val role = messages[0]["role"] as? String
        if (role == "system" || role == "developer") {
            if (maxMessages == 1) return listOf(messages.last())
            val tailCount = maxMessages - 1
            return listOf(messages[0]) + messages.takeLast(tailCount)
        }
    }
    return messages.takeLast(maxMessages)
}

public class NRouterMemory(private val store: MemoryStore = ArrayMemoryStore()) {
    public companion object {
        private val TENANCY_KEYS = setOf("organizationid", "orgid", "teamid", "userid", "nrouterorg")
        private val ROLES = setOf("system", "user", "assistant", "tool", "developer")

        private fun normalizeKey(key: String): String =
            key.lowercase().replace("_", "").replace("-", "")

        public fun validateMessage(message: ChatMessage, context: String): ChatMessage {
            for (key in message.keys) {
                val norm = normalizeKey(key)
                if (norm in TENANCY_KEYS) {
                    throw NRouterError.Configuration("$context: message contains forbidden tenancy key '$key'")
                }
            }
            val role = message["role"] as? String
            if (role == null || role !in ROLES) {
                throw NRouterError.Configuration("$context: message must contain a valid role (system, user, assistant, tool, developer)")
            }
            val content = message["content"]
            val toolCalls = message["tool_calls"]
            val hasToolCalls = toolCalls is List<*> && toolCalls.isNotEmpty()
            if (content == null) {
                if (!hasToolCalls && role != "assistant") {
                    throw NRouterError.Configuration("$context: content must be a string or list of content parts")
                }
            } else if (content !is String && content !is List<*>) {
                throw NRouterError.Configuration("$context: content must be a string or list of content parts")
            }
            return message
        }
    }

    @Synchronized
    public fun add(message: ChatMessage) {
        val clean = validateMessage(message, "NRouterMemory.add")
        val current = messages().toMutableList()
        current.add(clean)
        store.save(current)
    }

    @Synchronized
    public fun messages(): List<ChatMessage> {
        val raw = store.load()
        return raw.mapIndexed { i, msg -> validateMessage(msg, "MemoryStore.load()[$i]") }
    }

    @Synchronized
    public fun messages(maxMessages: Int, preserveSystem: Boolean = true): List<ChatMessage> =
        slidingWindow(messages(), maxMessages, preserveSystem)

    @Synchronized
    public fun clear() {
        store.save(emptyList())
    }
}
