import Foundation

public let neutralTopP: Double = 1.0

/// Returns true if the model or provider indicates an Anthropic Claude model.
public func isClaudeModel(_ model: String, provider: String? = nil) -> Bool {
    let m = model.lowercased()
    let p = provider?.lowercased() ?? ""
    return m.contains("claude")
        || m.contains("anthropic")
        || m.contains("haiku")
        || m.contains("sonnet")
        || m.contains("opus")
        || p.contains("anthropic")
}

/// Implements Claude sampling policy: mutual exclusion between temperature and top_p.
public func buildSamplingParams(
    advanced: Bool,
    model: String,
    provider: String? = nil,
    temperature: Double? = nil,
    topP: Double? = nil
) throws -> [String: Double] {
    guard advanced else { return [:] }

    if let t = temperature {
        guard t.isFinite else {
            throw NRouterError.configuration("temperature must be a finite number")
        }
        guard t >= 0.0 else {
            throw NRouterError.configuration("temperature must be 0 or greater, got \(t)")
        }
    }

    if let p = topP {
        guard p.isFinite else {
            throw NRouterError.configuration("top_p must be a finite number")
        }
        guard p >= 0.0 && p <= 1.0 else {
            throw NRouterError.configuration("top_p must be between 0 and 1.0, got \(p)")
        }
    }

    let topPSet = topP != nil && topP != neutralTopP
    let suppressTemperature = topPSet && isClaudeModel(model, provider: provider)

    var out: [String: Double] = [:]
    if let t = temperature, !suppressTemperature {
        out["temperature"] = t
    }
    if let p = topP, topPSet {
        out["top_p"] = p
    }
    return out
}
