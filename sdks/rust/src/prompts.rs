//! Managed prompt helpers for the nRouter request fields.

use serde_json::{Map, Value};

use crate::options::{
    build_extra_body, FeatureOptions, PROMPT_TEMPLATE_ID_FIELD, PROMPT_VARIABLES_FIELD,
};
use crate::NRouterError;

pub const PROMPT_WIRE_FIELDS: [&str; 2] = [PROMPT_TEMPLATE_ID_FIELD, PROMPT_VARIABLES_FIELD];
pub const SYSTEM_VARIABLE_NAMES: [&str; 4] = ["org_name", "model", "timestamp", "user_id"];

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct PromptSelection {
    pub template_id: Option<String>,
    pub variables: Option<Map<String, Value>>,
}

pub fn prompt_template(
    template_id: impl Into<String>,
    variables: Option<Map<String, Value>>,
) -> Result<PromptSelection, NRouterError> {
    let trimmed = template_id.into().trim().to_string();
    if trimmed.is_empty() {
        return Err(NRouterError::Configuration(
            "prompt_template requires a template id. Use prompt_variables() to render the assigned prompt."
                .into(),
        ));
    }
    Ok(PromptSelection {
        template_id: Some(trimmed),
        variables,
    })
}

pub fn prompt_variables(variables: Map<String, Value>) -> PromptSelection {
    PromptSelection {
        template_id: None,
        variables: Some(variables),
    }
}

pub fn with_variables(selection: &PromptSelection, more: Map<String, Value>) -> PromptSelection {
    let mut variables = selection.variables.clone().unwrap_or_default();
    variables.extend(more);
    PromptSelection {
        template_id: selection.template_id.clone(),
        variables: Some(variables),
    }
}

pub fn prompt_extra_body(selection: &PromptSelection) -> Result<Map<String, Value>, NRouterError> {
    build_extra_body(&FeatureOptions {
        prompt_template_id: selection.template_id.clone(),
        prompt_variables: selection.variables.clone(),
        ..FeatureOptions::default()
    })
}

pub fn apply_prompt(options: &mut FeatureOptions, selection: &PromptSelection) {
    if let Some(template_id) = &selection.template_id {
        options.prompt_template_id = Some(template_id.clone());
    }
    if let Some(vars) = &selection.variables {
        let mut merged = options.prompt_variables.clone().unwrap_or_default();
        merged.extend(vars.clone());
        options.prompt_variables = Some(merged);
    }
}

pub fn system_variable_conflicts(variables: &Map<String, Value>) -> Vec<&'static str> {
    SYSTEM_VARIABLE_NAMES
        .iter()
        .copied()
        .filter(|name| variables.contains_key(*name))
        .collect()
}
