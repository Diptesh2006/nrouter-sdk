package ai.nrouter.sdk;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class NRouterMemoryTest {

    @Test
    void storesCopiesOfMessages() {
        NRouterMemory memory = NRouterMemory.createMemory();
        Map<String, Object> part = new java.util.LinkedHashMap<>(Map.of("type", "text", "text", "hi"));
        Map<String, Object> message = new java.util.LinkedHashMap<>(
                Map.of("role", "user", "content", new ArrayList<>(List.of(part))));

        memory.add(message);
        part.put("text", "changed");

        List<Map<String, Object>> stored = memory.messages();
        assertEquals("hi", ((Map<?, ?>) ((List<?>) stored.get(0).get("content")).get(0)).get("text"));

        ((Map<String, Object>) ((List<?>) stored.get(0).get("content")).get(0)).put("text", "mutated");
        assertEquals("hi", ((Map<?, ?>) ((List<?>) memory.messages().get(0).get("content")).get(0)).get("text"));
    }

    @Test
    void clearRemovesAllMessages() {
        NRouterMemory memory = NRouterMemory.createMemory();
        memory.add(Map.of("role", "user", "content", "hi"));
        memory.clear();
        assertEquals(List.of(), memory.messages());
    }

    @Test
    void refusesTenancyFields() {
        NRouterMemory memory = NRouterMemory.createMemory();
        assertThrows(
                IllegalArgumentException.class,
                () -> memory.add(Map.of("role", "user", "content", "hi", "team_id", "team")));
    }

    @Test
    void refusesMalformedMessages() {
        NRouterMemory memory = NRouterMemory.createMemory();
        assertThrows(IllegalArgumentException.class, () -> memory.add(Map.of("role", "tool", "content", "hi")));
        assertThrows(IllegalArgumentException.class, () -> memory.add(Map.of("role", "user", "content", 42)));
    }
}
