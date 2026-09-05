package ai.nrouter.sdk

public const val NEUTRAL_TOP_P: Double = 1.0

/** Returns true if the model or provider indicates an Anthropic Claude model. */
public fun isClaudeModel(model: String, provider: String? = null): Boolean {
    val m = model.lowercase()
    val p = provider?.lowercase() ?: ""
    return m.contains("claude") || m.contains("haiku") || m.contains("sonnet") || m.contains("opus") || p.contains("anthropic")
}

/** Implements Claude sampling policy: mutual exclusion between temperature and top_p. */
public fun buildSamplingParams(
    advanced: Boolean,
    model: String,
    provider: String? = null,
    temperature: Double? = null,
    topP: Double? = null,
): Map<String, Double> {
    if (!advanced) return emptyMap()

    if (temperature != null) {
        if (!temperature.isFinite()) {
            throw NRouterError.Configuration("temperature must be a finite number")
        }
        if (temperature < 0.0) {
            throw NRouterError.Configuration("temperature must be 0 or greater, got $temperature")
        }
    }

    if (topP != null) {
        if (!topP.isFinite()) {
            throw NRouterError.Configuration("top_p must be a finite number")
        }
        if (topP < 0.0 || topP > 1.0) {
            throw NRouterError.Configuration("top_p must be between 0 and 1.0, got $topP")
        }
    }

    val topPSet = topP != null && topP != NEUTRAL_TOP_P
    val suppressTemperature = topPSet && isClaudeModel(model, provider)

    val out = mutableMapOf<String, Double>()
    if (temperature != null && !suppressTemperature) {
        out["temperature"] = temperature
    }
    if (topP != null && topPSet) {
        out["top_p"] = topP
    }
    return out
}
