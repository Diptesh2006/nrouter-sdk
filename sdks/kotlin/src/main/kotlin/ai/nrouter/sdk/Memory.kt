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

public class NRouterMemory(private val store: MemoryStore = ArrayMemoryStore()) {
    public companion object {
        private val TENANCY_KEYS = setOf("organizationid", "orgid", "teamid", "userid", "nrouterorg")
        private val ROLES = setOf("system", "user", "assistant", "tool")

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
                throw NRouterError.Configuration("$context: message must contain a valid role (system, user, assistant, tool)")
            }
            return message
        }
    }

    public fun add(message: ChatMessage) {
        val clean = validateMessage(message, "NRouterMemory.add")
        val current = messages().toMutableList()
        current.add(clean)
        store.save(current)
    }

    public fun messages(): List<ChatMessage> {
        val raw = store.load()
        return raw.mapIndexed { i, msg -> validateMessage(msg, "MemoryStore.load()[$i]") }
    }

    public fun clear() {
        store.save(emptyList())
    }
}
