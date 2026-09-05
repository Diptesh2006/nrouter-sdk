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

class RenderPromptOptions {
  const RenderPromptOptions({
    this.strict = false,
    this.systemVariables,
  });

  final bool strict;
  final Map<String, String>? systemVariables;
}

/// Safely renders a prompt template by interpolating `{{variable}}` or `{{ variable }}` tokens.
///
/// Security & resiliency features:
/// - Single-pass replacement prevents recursive variable expansion loops.
/// - `replaceAllMapped` avoids regex replacement metacharacter injection ($1, $&).
/// - Strict mode: throws `NRouterConfigurationError` when any template variable is missing.
/// - System variables: take precedence over caller variables matching gateway rules.
String renderPrompt(
  String template, [
  Map<String, dynamic>? variables,
  RenderPromptOptions options = const RenderPromptOptions(),
]) {
  if (template.isEmpty) {
    return '';
  }
  final missingKeys = <String>[];
  final regex = RegExp(r'\{\{\s*([a-zA-Z0-9_-]+)\s*\}\}');

  final result = template.replaceAllMapped(regex, (match) {
    final key = match.group(1)!;

    if (options.systemVariables != null &&
        options.systemVariables!.containsKey(key)) {
      return options.systemVariables![key] ?? '';
    }

    if (variables != null && variables.containsKey(key)) {
      final val = variables[key];
      return val == null ? '' : '$val';
    }

    if (options.strict) {
      missingKeys.add(key);
    }
    return match.group(0)!;
  });

  if (options.strict && missingKeys.isNotEmpty) {
    throw NRouterConfigurationError(
        'Missing required prompt template variables: ${missingKeys.join(', ')}');
  }

  return result;
}

