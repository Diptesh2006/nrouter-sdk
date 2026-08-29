use nrouter::memory::Memory;
use nrouter::options::{build_extra_body, vet_extra, FeatureOptions};
use nrouter::prompts::{
    prompt_extra_body, prompt_template, prompt_variables, system_variable_conflicts, with_variables,
};
use nrouter::sampling::build_sampling_params;
use serde_json::{json, Map, Value};

fn vars(entries: &[(&str, &str)]) -> Map<String, Value> {
    entries
        .iter()
        .map(|(k, v)| ((*k).into(), Value::String((*v).into())))
        .collect()
}

#[test]
fn prompt_selection_maps_to_gateway_fields() {
    let selection = prompt_template("  tpl_123  ", Some(vars(&[("name", "Ada")]))).unwrap();
    let body = prompt_extra_body(&selection).unwrap();
    assert_eq!(body["nrouter_prompt_template_id"], json!("tpl_123"));
    assert_eq!(body["nrouter_prompt_variables"], json!({"name": "Ada"}));
}

#[test]
fn variables_only_is_supported() {
    let body = prompt_extra_body(&prompt_variables(vars(&[("name", "Ada")]))).unwrap();
    assert_eq!(body["nrouter_prompt_variables"], json!({"name": "Ada"}));
}

#[test]
fn prompt_helpers_do_not_mutate_selections() {
    let selection = prompt_template("tpl", Some(vars(&[("a", "1")]))).unwrap();
    let merged = with_variables(&selection, vars(&[("a", "2"), ("b", "3")]));
    assert_eq!(selection.variables.unwrap()["a"], json!("1"));
    assert_eq!(merged.variables.unwrap(), vars(&[("a", "2"), ("b", "3")]));
}

#[test]
fn guardrails_are_refused_and_cache_false_is_mapped() {
    assert!(build_extra_body(&FeatureOptions {
        guardrail_ids: vec!["gr_1".into()],
        ..FeatureOptions::default()
    })
    .is_err());
    assert!(build_extra_body(&FeatureOptions {
        cache: Some(true),
        ..FeatureOptions::default()
    })
    .unwrap()
    .is_empty());
    assert_eq!(
        build_extra_body(&FeatureOptions {
            cache: Some(false),
            ..FeatureOptions::default()
        })
        .unwrap()["nrouter_cache"],
        json!(false)
    );
}

#[test]
fn extra_body_tenancy_fields_are_refused() {
    let mut extra = Map::new();
    extra.insert("organization_id".into(), json!("spoof"));
    assert!(vet_extra(&extra).is_err());
}

#[test]
fn sampling_policy_matches_claude_rules() {
    assert!(
        build_sampling_params(false, "anthropic/claude-sonnet", None, Some(0.7), Some(0.5))
            .unwrap()
            .is_empty()
    );
    assert_eq!(
        build_sampling_params(true, "anthropic/claude-sonnet", None, Some(0.7), Some(0.5)).unwrap()
            ["top_p"],
        json!(0.5)
    );
    let non_claude =
        build_sampling_params(true, "openai/gpt-5", None, Some(0.7), Some(0.5)).unwrap();
    assert_eq!(non_claude["temperature"], json!(0.7));
    assert_eq!(non_claude["top_p"], json!(0.5));
    assert!(build_sampling_params(true, "openai/gpt-5", None, Some(0.7), Some(2.0)).is_err());
}

#[test]
fn memory_stores_copies_and_refuses_tenancy_fields() {
    let memory = Memory::new();
    let mut message = Map::new();
    message.insert("role".into(), json!("user"));
    message.insert("content".into(), json!("hi"));
    memory.add(message).unwrap();
    assert_eq!(memory.messages().unwrap()[0]["content"], json!("hi"));

    let mut bad = Map::new();
    bad.insert("role".into(), json!("user"));
    bad.insert("content".into(), json!("hi"));
    bad.insert("team_id".into(), json!("team"));
    assert!(memory.add(bad).is_err());
}

#[test]
fn system_variable_conflicts_are_in_gateway_order() {
    assert_eq!(
        system_variable_conflicts(&vars(&[("model", "fake"), ("org_name", "fake")])),
        vec!["org_name", "model"]
    );
}
