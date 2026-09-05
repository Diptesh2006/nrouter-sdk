package ai.nrouter.sdk;

import java.util.*;
import java.util.regex.*;

/**
 * Managed prompt helpers and safe client-side prompt template interpolation.
 */
public final class NRouterPrompts {
    private NRouterPrompts() {}

    public static final String PROMPT_TEMPLATE_ID_FIELD = "nrouter_prompt_template_id";
    public static final String PROMPT_VARIABLES_FIELD = "nrouter_prompt_variables";
    public static final List<String> PROMPT_WIRE_FIELDS =
            Collections.unmodifiableList(Arrays.asList(PROMPT_TEMPLATE_ID_FIELD, PROMPT_VARIABLES_FIELD));
    public static final List<String> SYSTEM_VARIABLE_NAMES =
            Collections.unmodifiableList(Arrays.asList("org_name", "model", "timestamp", "user_id"));

    public static class PromptSelection {
        private final String templateId;
        private final Map<String, Object> variables;

        public PromptSelection(String templateId, Map<String, ?> variables) {
            this.templateId = templateId;
            this.variables = variables != null ? new HashMap<>(variables) : new HashMap<>();
        }

        public String getTemplateId() {
            return templateId;
        }

        public Map<String, Object> getVariables() {
            return Collections.unmodifiableMap(variables);
        }

        public PromptSelection withVariables(Map<String, ?> newVars) {
            Map<String, Object> merged = new HashMap<>(this.variables);
            if (newVars != null) {
                merged.putAll(newVars);
            }
            return new PromptSelection(this.templateId, merged);
        }

        public void applyTo(Map<String, Object> extra) {
            if (extra == null) return;
            if (templateId != null && !templateId.trim().isEmpty()) {
                extra.put(PROMPT_TEMPLATE_ID_FIELD, templateId.trim());
            }
            if (!variables.isEmpty()) {
                extra.put(PROMPT_VARIABLES_FIELD, variables);
            }
        }
    }

    public static PromptSelection promptTemplate(String templateId, Map<String, ?> variables) {
        if (templateId == null || templateId.trim().isEmpty()) {
            throw NRouterException.configuration("promptTemplate requires a non-empty template id");
        }
        return new PromptSelection(templateId.trim(), variables);
    }

    public static PromptSelection promptTemplate(String templateId) {
        return promptTemplate(templateId, Collections.emptyMap());
    }

    public static PromptSelection promptVariables(Map<String, ?> variables) {
        return new PromptSelection(null, variables);
    }

    public static List<String> systemVariableConflicts(Map<String, ?> variables) {
        if (variables == null) return Collections.emptyList();
        List<String> conflicts = new ArrayList<>();
        for (String sysVar : SYSTEM_VARIABLE_NAMES) {
            if (variables.containsKey(sysVar)) {
                conflicts.add(sysVar);
            }
        }
        return conflicts;
    }

    public static class RenderOptions {
        private final boolean strict;
        private final Map<String, String> systemVariables;

        public RenderOptions(boolean strict, Map<String, String> systemVariables) {
            this.strict = strict;
            this.systemVariables = systemVariables != null ? new HashMap<>(systemVariables) : null;
        }

        public RenderOptions(boolean strict) {
            this(strict, null);
        }

        public RenderOptions() {
            this(false, null);
        }

        public boolean isStrict() {
            return strict;
        }

        public Map<String, String> getSystemVariables() {
            return systemVariables;
        }
    }

    private static final Pattern VARIABLE_PATTERN = Pattern.compile("\\{\\{\\s*([a-zA-Z0-9_-]+)\\s*\\}\\}");

    /**
     * Safely renders a prompt template by interpolating `{{variable}}` or `{{ variable }}` tokens.
     *
     * Security & resiliency features:
     * - Single-pass replacement prevents recursive variable expansion loops.
     * - Matcher.quoteReplacement avoids regex backreference corruption ($1, $&).
     * - Strict mode: throws NRouterException when any template variable is missing.
     * - System variables: take precedence over caller variables matching gateway rules.
     */
    public static String renderPrompt(String template, Map<String, ?> variables, RenderOptions options) {
        if (template == null || template.isEmpty()) {
            return "";
        }
        RenderOptions opts = options != null ? options : new RenderOptions();
        Matcher matcher = VARIABLE_PATTERN.matcher(template);
        StringBuffer sb = new StringBuffer();
        List<String> missingKeys = new ArrayList<>();

        while (matcher.find()) {
            String key = matcher.group(1);
            if (opts.getSystemVariables() != null && opts.getSystemVariables().containsKey(key)) {
                String val = opts.getSystemVariables().get(key);
                matcher.appendReplacement(sb, Matcher.quoteReplacement(val != null ? val : ""));
            } else if (variables != null && variables.containsKey(key)) {
                Object val = variables.get(key);
                matcher.appendReplacement(sb, Matcher.quoteReplacement(val != null ? String.valueOf(val) : ""));
            } else if (opts.isStrict()) {
                missingKeys.add(key);
                matcher.appendReplacement(sb, Matcher.quoteReplacement(matcher.group(0)));
            } else {
                matcher.appendReplacement(sb, Matcher.quoteReplacement(matcher.group(0)));
            }
        }
        matcher.appendTail(sb);

        if (opts.isStrict() && !missingKeys.isEmpty()) {
            throw NRouterException.configuration(
                "Missing required prompt template variables: " + String.join(", ", missingKeys)
            );
        }

        return sb.toString();
    }

    public static String renderPrompt(String template, Map<String, ?> variables) {
        return renderPrompt(template, variables, new RenderOptions());
    }
}
