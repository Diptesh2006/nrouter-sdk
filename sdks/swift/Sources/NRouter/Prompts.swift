import Foundation

public let promptTemplateIDField = "nrouter_prompt_template_id"
public let promptVariablesField = "nrouter_prompt_variables"
public let promptWireFields = [promptTemplateIDField, promptVariablesField]
public let systemVariableNames = ["org_name", "model", "timestamp", "user_id"]

public struct NRouterPromptSelection: @unchecked Sendable {
    public let templateID: String?
    public let variables: [String: Any]?

    public init(templateID: String? = nil, variables: [String: Any]? = nil) {
        self.templateID = templateID
        self.variables = variables
    }

    public func withVariables(_ newVars: [String: Any]) -> NRouterPromptSelection {
        var merged = self.variables ?? [:]
        for (k, v) in newVars {
            merged[k] = v
        }
        return NRouterPromptSelection(templateID: self.templateID, variables: merged)
    }

    public func apply(to body: inout [String: Any]) {
        if let tid = templateID {
            body[promptTemplateIDField] = tid
        }
        if let vars = variables, !vars.isEmpty {
            body[promptVariablesField] = vars
        }
    }
}

public func promptTemplate(_ id: String, variables: [String: Any]? = nil) throws -> NRouterPromptSelection {
    let trimmed = id.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else {
        throw NRouterError.configuration("promptTemplate requires a non-empty template id")
    }
    return NRouterPromptSelection(templateID: trimmed, variables: variables)
}

public func promptVariables(_ variables: [String: Any]) -> NRouterPromptSelection {
    return NRouterPromptSelection(templateID: nil, variables: variables)
}

public func systemVariableConflicts(_ variables: [String: Any]?) -> [String] {
    guard let variables = variables else { return [] }
    var conflicts: [String] = []
    for sysVar in systemVariableNames {
        if variables[sysVar] != nil {
            conflicts.append(sysVar)
        }
    }
    return conflicts
}

public struct NRouterRenderPromptOptions: Sendable {
    public let strict: Bool
    public let systemVariables: [String: String]?

    public init(strict: Bool = false, systemVariables: [String: String]? = nil) {
        self.strict = strict
        self.systemVariables = systemVariables
    }
}

/// Safely renders a prompt template by interpolating `{{variable}}` or `{{ variable }}` tokens.
///
/// Security & resiliency features:
/// - Single-pass replacement prevents recursive variable expansion loops.
/// - Escape-safe: string appends avoid regex backreference and format injection.
/// - Strict mode: throws `NRouterError.configuration` if any template variable is missing.
/// - System variables: take precedence over caller variables matching gateway rules.
public func renderPrompt(
    _ template: String,
    variables: [String: Any]? = nil,
    options: NRouterRenderPromptOptions = NRouterRenderPromptOptions()
) throws -> String {
    if template.isEmpty {
        return ""
    }
    let pattern = "\\{\\{\\s*([a-zA-Z0-9_-]+)\\s*\\}\\}"
    guard let regex = try? NSRegularExpression(pattern: pattern, options: []) else {
        return template
    }

    let nsString = template as NSString
    let matches = regex.matches(in: template, options: [], range: NSRange(location: 0, length: nsString.length))

    var missingKeys: [String] = []
    var result = ""
    var lastIndex = 0

    for match in matches {
        let matchRange = match.range
        let keyRange = match.range(at: 1)

        let prefix = nsString.substring(with: NSRange(location: lastIndex, length: matchRange.location - lastIndex))
        result.append(prefix)
        lastIndex = matchRange.location + matchRange.length

        let key = nsString.substring(with: keyRange)
        if let sysVal = options.systemVariables?[key] {
            result.append(sysVal)
        } else if let val = variables?[key] {
            if !(val is NSNull) {
                result.append("\(val)")
            }
        } else if options.strict {
            missingKeys.append(key)
            result.append(nsString.substring(with: matchRange))
        } else {
            result.append(nsString.substring(with: matchRange))
        }
    }

    if lastIndex < nsString.length {
        result.append(nsString.substring(with: NSRange(location: lastIndex, length: nsString.length - lastIndex)))
    }

    if options.strict && !missingKeys.isEmpty {
        throw NRouterError.configuration("Missing required prompt template variables: \(missingKeys.joined(separator: ", "))")
    }

    return result
}

