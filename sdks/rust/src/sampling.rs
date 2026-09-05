//! Sampling-parameter policy shared with the JavaScript SDK.

use serde_json::{Map, Number, Value};

use crate::NRouterError;

const NEUTRAL_TOP_P: f64 = 1.0;

pub fn is_claude_model(model: &str, provider: Option<&str>) -> bool {
    let m = model.to_ascii_lowercase();
    let p = provider.unwrap_or("").to_ascii_lowercase();
    m.contains("claude")
        || m.contains("anthropic")
        || m.contains("haiku")
        || m.contains("sonnet")
        || m.contains("opus")
        || p.contains("anthropic")
}

pub fn build_sampling_params(
    advanced: bool,
    model: &str,
    provider: Option<&str>,
    temperature: Option<f64>,
    top_p: Option<f64>,
) -> Result<Map<String, Value>, NRouterError> {
    if !advanced {
        return Ok(Map::new());
    }
    if let Some(v) = temperature {
        require_usable("temperature", v, None)?;
    }
    if let Some(v) = top_p {
        require_usable("top_p", v, Some(1.0))?;
    }

    let top_p_set = top_p.is_some_and(|v| v != NEUTRAL_TOP_P);
    let suppress_temperature = top_p_set && is_claude_model(model, provider);
    let mut out = Map::new();
    if let Some(v) = temperature {
        if !suppress_temperature {
            out.insert("temperature".into(), number(v));
        }
    }
    if let Some(v) = top_p {
        if top_p_set {
            out.insert("top_p".into(), number(v));
        }
    }
    Ok(out)
}

fn require_usable(name: &str, value: f64, max: Option<f64>) -> Result<(), NRouterError> {
    if !value.is_finite() {
        return Err(NRouterError::Configuration(format!(
            "{name} must be a finite number; sent as-is it serializes to JSON null."
        )));
    }
    if value < 0.0 || max.is_some_and(|m| value > m) {
        let range = max
            .map(|m| format!("between 0 and {m}"))
            .unwrap_or_else(|| "0 or greater".into());
        return Err(NRouterError::Configuration(format!(
            "{name} must be {range}, got {value}."
        )));
    }
    Ok(())
}

fn number(value: f64) -> Value {
    Value::Number(Number::from_f64(value).expect("validated finite"))
}
