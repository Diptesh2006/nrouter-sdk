package ai.nrouter.sdk

public const val PROMPT_TEMPLATE_ID_FIELD: String = "nrouter_prompt_template_id"
public const val PROMPT_VARIABLES_FIELD: String = "nrouter_prompt_variables"

public val PROMPT_WIRE_FIELDS: List<String> = listOf(PROMPT_TEMPLATE_ID_FIELD, PROMPT_VARIABLES_FIELD)
public val SYSTEM_VARIABLE_NAMES: List<String> = listOf("org_name", "model", "timestamp", "user_id")

public data class PromptSelection(
    val templateId: String? = null,
    val variables: Map<String, Any?> = emptyMap(),
) {
    public fun withVariables(newVars: Map<String, Any?>): PromptSelection {
        val merged = variables.toMutableMap()
        merged.putAll(newVars)
        return PromptSelection(templateId, merged)
    }

    public fun applyTo(extra: MutableMap<String, Any?>) {
        if (!templateId.isNullOrBlank()) {
            extra[PROMPT_TEMPLATE_ID_FIELD] = templateId
        }
        if (variables.isNotEmpty()) {
            extra[PROMPT_VARIABLES_FIELD] = variables
        }
    }
}

public fun promptTemplate(id: String, variables: Map<String, Any?> = emptyMap()): PromptSelection {
    val trimmed = id.trim()
    if (trimmed.isEmpty()) {
        throw NRouterError.Configuration("promptTemplate requires a non-empty template id")
    }
    return PromptSelection(trimmed, variables)
}

public fun promptVariables(variables: Map<String, Any?>): PromptSelection =
    PromptSelection(null, variables)

public fun systemVariableConflicts(variables: Map<String, Any?>?): List<String> {
    if (variables == null) return emptyList()
    val conflicts = mutableListOf<String>()
    for (sysVar in SYSTEM_VARIABLE_NAMES) {
        if (variables.containsKey(sysVar)) {
            conflicts.add(sysVar)
        }
    }
    return conflicts
}

public data class RenderPromptOptions(
    val strict: Boolean = false,
    val systemVariables: Map<String, String>? = null,
)

private val PROMPT_VARIABLE_REGEX: Regex = Regex("""\{\{\s*([a-zA-Z0-9_-]+)\s*\}\}""")

/**
 * Safely renders a prompt template by interpolating `{{variable}}` or `{{ variable }}` tokens.
 *
 * Security & resiliency features:
 * - Single-pass replacement prevents recursive variable expansion loops.
 * - Regex.replace transform avoids regex backreference and format injection ($1, $&).
 * - Strict mode: throws NRouterError.Configuration if any template variable is missing.
 * - System variables: take precedence over caller variables matching gateway rules.
 */
public fun renderPrompt(
    template: String,
    variables: Map<String, Any?> = emptyMap(),
    options: RenderPromptOptions = RenderPromptOptions(),
): String {
    if (template.isEmpty()) return ""
    val missingKeys = mutableListOf<String>()

    val result = PROMPT_VARIABLE_REGEX.replace(template) { match ->
        val key = match.groupValues[1]
        if (options.systemVariables != null && options.systemVariables.containsKey(key)) {
            options.systemVariables[key] ?: ""
        } else if (variables.containsKey(key)) {
            val v = variables[key]
            v?.toString() ?: ""
        } else {
            if (options.strict) {
                missingKeys.add(key)
            }
            match.value
        }
    }

    if (options.strict && missingKeys.isNotEmpty()) {
        throw NRouterError.Configuration(
            "Missing required prompt template variables: ${missingKeys.joinToString(", ")}"
        )
    }

    return result
}

