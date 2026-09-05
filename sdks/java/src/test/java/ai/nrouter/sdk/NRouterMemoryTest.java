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
    void acceptsDeveloperAndToolRoles() {
        NRouterMemory memory = NRouterMemory.createMemory();
        memory.add(Map.of("role", "developer", "content", "system prompt"));
        memory.add(Map.of("role", "tool", "content", "tool result"));
        List<Map<String, Object>> msgs = memory.messages();
        assertEquals(2, msgs.size());
        assertEquals("developer", msgs.get(0).get("role"));
        assertEquals("tool", msgs.get(1).get("role"));
    }

    @Test
    void acceptsAssistantWithNullContentAndToolCalls() {
        NRouterMemory memory = NRouterMemory.createMemory();
        Map<String, Object> asst = new java.util.HashMap<>();
        asst.put("role", "assistant");
        asst.put("content", null);
        asst.put("tool_calls", List.of(Map.of("id", "c1")));
        memory.add(asst);
        List<Map<String, Object>> msgs = memory.messages();
        assertEquals(1, msgs.size());
        assertEquals("assistant", msgs.get(0).get("role"));
    }

    @Test
    void slidingWindowPreservesSystem() {
        List<Map<String, Object>> msgs = List.of(
                Map.of("role", "system", "content", "sys"),
                Map.of("role", "user", "content", "1"),
                Map.of("role", "assistant", "content", "2"),
                Map.of("role", "user", "content", "3"),
                Map.of("role", "assistant", "content", "4"));
        List<Map<String, Object>> pruned = NRouterMemory.slidingWindow(msgs, 3, true);
        assertEquals(3, pruned.size());
        assertEquals("system", pruned.get(0).get("role"));
        assertEquals("3", pruned.get(1).get("content"));
        assertEquals("4", pruned.get(2).get("content"));
    }

    @Test
    void refusesMalformedMessages() {
        NRouterMemory memory = NRouterMemory.createMemory();
        assertThrows(IllegalArgumentException.class, () -> memory.add(Map.of("role", "invalid_role", "content", "hi")));
        assertThrows(IllegalArgumentException.class, () -> memory.add(Map.of("role", "user", "content", 42)));
    }
}
