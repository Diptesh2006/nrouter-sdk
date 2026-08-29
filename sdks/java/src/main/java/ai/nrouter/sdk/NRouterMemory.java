package ai.nrouter.sdk;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * Client-side conversation memory.
 *
 * The nRouter gateway is stateless between calls. This helper only stores
 * message maps locally and returns copies that callers can pass as messages.
 */
public final class NRouterMemory {

    private static final Set<String> ROLES = Set.of("system", "user", "assistant");
    private static final Set<String> TENANCY_KEYS =
            Set.of("organizationid", "orgid", "teamid", "userid", "nrouterorg");

    private final MemoryStore store;

    public NRouterMemory() {
        this(new ArrayMemoryStore(Collections.emptyList()));
    }

    public NRouterMemory(MemoryStore store) {
        this.store = store;
    }

    public synchronized void add(Map<String, Object> message) {
        Map<String, Object> clean = validateMessage(message, "add()");
        List<Map<String, Object>> current = messages();
        current.add(clean);
        store.save(current);
    }

    public synchronized List<Map<String, Object>> messages() {
        List<Map<String, Object>> raw = store.load();
        if (raw == null) {
            throw new IllegalArgumentException("MemoryStore.load() must return a list of messages.");
        }
        List<Map<String, Object>> out = new ArrayList<>();
        for (int i = 0; i < raw.size(); i++) {
            out.add(validateMessage(raw.get(i), "MemoryStore.load()[" + i + "]"));
        }
        return out;
    }

    public synchronized void clear() {
        store.save(Collections.emptyList());
    }

    public interface MemoryStore {
        List<Map<String, Object>> load();
        void save(List<Map<String, Object>> messages);
    }

    public static final class ArrayMemoryStore implements MemoryStore {
        private List<Map<String, Object>> rows;

        public ArrayMemoryStore(List<Map<String, Object>> seed) {
            this.rows = copyMessages(seed == null ? Collections.emptyList() : seed);
        }

        @Override
        public List<Map<String, Object>> load() {
            return copyMessages(rows);
        }

        @Override
        public void save(List<Map<String, Object>> messages) {
            this.rows = copyMessages(messages);
        }
    }

    public static ArrayMemoryStore createArrayStore(List<Map<String, Object>> seed) {
        return new ArrayMemoryStore(seed);
    }

    public static NRouterMemory createMemory() {
        return new NRouterMemory();
    }

    public static NRouterMemory createMemory(MemoryStore store) {
        return new NRouterMemory(store);
    }

    private static Map<String, Object> validateMessage(Map<String, Object> message, String where) {
        if (message == null) {
            throw new IllegalArgumentException(where + ": a message must be a map.");
        }
        Map<String, Object> copy = copyMessage(message);
        for (String key : copy.keySet()) {
            if (TENANCY_KEYS.contains(normalizeKey(key))) {
                throw new IllegalArgumentException(
                        where + ": a message must not carry the tenancy field \"" + key + "\".");
            }
        }
        Object role = copy.get("role");
        if (!(role instanceof String) || !ROLES.contains(role)) {
            throw new IllegalArgumentException(where + ": role must be one of system, user, assistant.");
        }
        Object content = copy.get("content");
        if (!(content instanceof String) && !(content instanceof List<?>)) {
            throw new IllegalArgumentException(where + ": content must be a string or content-parts list.");
        }
        return copy;
    }

    private static List<Map<String, Object>> copyMessages(List<Map<String, Object>> messages) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> message : messages) {
            out.add(copyMessage(message));
        }
        return out;
    }

    private static Map<String, Object> copyMessage(Map<String, Object> message) {
        Map<String, Object> out = new LinkedHashMap<>();
        for (Map.Entry<String, Object> entry : message.entrySet()) {
            out.put(entry.getKey(), copyValue(entry.getValue()));
        }
        return out;
    }

    @SuppressWarnings("unchecked")
    private static Object copyValue(Object value) {
        if (value instanceof Map<?, ?>) {
            Map<String, Object> out = new LinkedHashMap<>();
            for (Map.Entry<?, ?> entry : ((Map<?, ?>) value).entrySet()) {
                out.put(String.valueOf(entry.getKey()), copyValue(entry.getValue()));
            }
            return out;
        }
        if (value instanceof List<?>) {
            List<Object> out = new ArrayList<>();
            for (Object item : (List<Object>) value) {
                out.add(copyValue(item));
            }
            return out;
        }
        return value;
    }

    private static String normalizeKey(String key) {
        return key.toLowerCase(Locale.ROOT).replace("_", "");
    }
}
