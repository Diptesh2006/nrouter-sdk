import 'errors.dart';

const promptTemplateIdField = 'nrouter_prompt_template_id';
const promptVariablesField = 'nrouter_prompt_variables';

const promptWireFields = [promptTemplateIdField, promptVariablesField];
const systemVariableNames = ['org_name', 'model', 'timestamp', 'user_id'];

class PromptSelection {
  const PromptSelection({
    this.templateId,
    this.variables = const {},
  });

  final String? templateId;
  final Map<String, dynamic> variables;

  PromptSelection withVariables(Map<String, dynamic> newVars) {
    return PromptSelection(
      templateId: templateId,
      variables: {...variables, ...newVars},
    );
  }

  void applyTo(Map<String, dynamic> extra) {
    if (templateId != null && templateId!.isNotEmpty) {
      extra[promptTemplateIdField] = templateId;
    }
    if (variables.isNotEmpty) {
      extra[promptVariablesField] = variables;
    }
  }
}

PromptSelection promptTemplate(String id, [Map<String, dynamic>? variables]) {
  final trimmed = id.trim();
  if (trimmed.isEmpty) {
    throw const NRouterConfigurationError(
        'promptTemplate requires a non-empty template id');
  }
  return PromptSelection(
    templateId: trimmed,
    variables: variables ?? const {},
  );
}

PromptSelection promptVariables(Map<String, dynamic> variables) =>
    PromptSelection(variables: variables);

List<String> systemVariableConflicts(Map<String, dynamic>? variables) {
  if (variables == null) return const [];
  final conflicts = <String>[];
  for (final sysVar in systemVariableNames) {
    if (variables.containsKey(sysVar)) {
      conflicts.add(sysVar);
    }
  }
  return conflicts;
}
