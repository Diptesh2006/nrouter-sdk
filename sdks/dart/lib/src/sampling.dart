import 'errors.dart';

const double neutralTopP = 1.0;

/// Returns true if the model or provider indicates an Anthropic Claude model.
bool isClaudeModel(String model, [String? provider]) {
  final m = model.toLowerCase();
  final p = provider?.toLowerCase() ?? '';
  return m.contains('claude') ||
      m.contains('anthropic') ||
      m.contains('haiku') ||
      m.contains('sonnet') ||
      m.contains('opus') ||
      p.contains('anthropic');
}

/// Implements Claude sampling policy: mutual exclusion between temperature and top_p.
Map<String, double> buildSamplingParams({
  required bool advanced,
  required String model,
  String? provider,
  double? temperature,
  double? topP,
}) {
  if (!advanced) return {};

  if (temperature != null) {
    if (!temperature.isFinite) {
      throw NRouterConfigurationError('temperature must be a finite number');
    }
    if (temperature < 0.0) {
      throw NRouterConfigurationError('temperature must be 0 or greater, got $temperature');
    }
  }

  if (topP != null) {
    if (!topP.isFinite) {
      throw NRouterConfigurationError('top_p must be a finite number');
    }
    if (topP < 0.0 || topP > 1.0) {
      throw NRouterConfigurationError('top_p must be between 0 and 1.0, got $topP');
    }
  }

  final topPSet = topP != null && topP != neutralTopP;
  final suppressTemperature = topPSet && isClaudeModel(model, provider);

  final out = <String, double>{};
  if (temperature != null && !suppressTemperature) {
    out['temperature'] = temperature;
  }
  if (topP != null && topPSet) {
    out['top_p'] = topP;
  }
  return out;
}
