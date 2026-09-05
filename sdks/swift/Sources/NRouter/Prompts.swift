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
