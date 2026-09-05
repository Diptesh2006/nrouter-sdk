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
    // Aliases sonnet, haiku, opus
    assert_eq!(
        build_sampling_params(true, "sonnet-4-5", None, Some(0.7), Some(0.5)).unwrap()["top_p"],
        json!(0.5)
    );
    assert_eq!(
        build_sampling_params(true, "haiku-3-5", None, Some(0.7), Some(0.5)).unwrap()["top_p"],
        json!(0.5)
    );
    assert_eq!(
        build_sampling_params(true, "opus-4", None, Some(0.7), Some(0.5)).unwrap()["top_p"],
        json!(0.5)
    );
    let non_claude =
        build_sampling_params(true, "openai/gpt-5", None, Some(0.7), Some(0.5)).unwrap();
    assert_eq!(non_claude["temperature"], json!(0.7));
    assert_eq!(non_claude["top_p"], json!(0.5));
    assert!(build_sampling_params(true, "openai/gpt-5", None, Some(0.7), Some(2.0)).is_err());

    let normalized = nrouter::http::Client::normalize_anthropic_messages(&json!({
        "model": "claude-sonnet-4-5",
        "system": "Initial system",
        "messages": [
            {"role": "system", "content": "Turn system"},
            {"role": "user", "content": "Hello"}
        ],
        "max_completion_tokens": 1024,
        "stop": "Human:"
    }));
    assert_eq!(normalized["system"], "Initial system\n\nTurn system");
    assert_eq!(normalized["messages"].as_array().unwrap().len(), 1);
    assert_eq!(normalized["max_tokens"], 1024);
    assert_eq!(normalized["stop_sequences"], json!(["Human:"]));
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

    // Developer and tool roles
    let mut dev = Map::new();
    dev.insert("role".into(), json!("developer"));
    dev.insert("content".into(), json!("sys instructions"));
    memory.add(dev).unwrap();

    let mut tool = Map::new();
    tool.insert("role".into(), json!("tool"));
    tool.insert("content".into(), json!("result"));
    memory.add(tool).unwrap();

    // Assistant with tool_calls and null content
    let mut asst = Map::new();
    asst.insert("role".into(), json!("assistant"));
    asst.insert("content".into(), json!(null));
    asst.insert("tool_calls".into(), json!([{"id": "call_1"}]));
    memory.add(asst).unwrap();

    let msgs = memory.messages().unwrap();
    assert_eq!(msgs.len(), 4);
    assert_eq!(msgs[1]["role"], json!("developer"));
    assert_eq!(msgs[2]["role"], json!("tool"));
    assert_eq!(msgs[3]["role"], json!("assistant"));
    assert_eq!(msgs[3]["content"], json!(null));

    // Sliding window
    let windowed = memory.window(2, false).unwrap();
    assert_eq!(windowed.len(), 2);
    assert_eq!(windowed[1]["role"], json!("assistant"));
}

#[test]
fn system_variable_conflicts_are_in_gateway_order() {
    assert_eq!(
        system_variable_conflicts(&vars(&[("model", "fake"), ("org_name", "fake")])),
        vec!["org_name", "model"]
    );
}

#[test]
fn render_prompt_whitespace_and_type_formatting() {
    use nrouter::prompts::render_prompt;
    let mut map = Map::new();
    map.insert("name".into(), json!("Alice"));
    map.insert("age".into(), json!(30));
    map.insert("active".into(), json!(true));

    let tpl = "Hello {{name}}! Age: {{  age  }}, active: {{ active }}.";
    let out = render_prompt(tpl, Some(&map), None).unwrap();
    assert_eq!(out, "Hello Alice! Age: 30, active: true.");
}

#[test]
fn render_prompt_prevents_recursive_expansion() {
    use nrouter::prompts::render_prompt;
    let mut map = Map::new();
    map.insert("a".into(), json!("{{b}}"));
    map.insert("b".into(), json!("final"));

    let tpl = "Expanded: {{a}}";
    let out = render_prompt(tpl, Some(&map), None).unwrap();
    assert_eq!(out, "Expanded: {{b}}");
}

#[test]
fn render_prompt_strict_mode_and_preservation() {
    use nrouter::prompts::{render_prompt, RenderPromptOptions};
    let mut map = Map::new();
    map.insert("hello".into(), json!("hi"));

    let tpl = "Greeting: {{hello}}, missing: {{world}}";
    let out = render_prompt(tpl, Some(&map), None).unwrap();
    assert_eq!(out, "Greeting: hi, missing: {{world}}");

    let err = render_prompt(
        tpl,
        Some(&map),
        Some(RenderPromptOptions {
            strict: true,
            system_variables: None,
        }),
    );
    assert!(err.is_err());
}

#[test]
fn render_prompt_system_variables_precedence() {
    use nrouter::prompts::{render_prompt, RenderPromptOptions};
    let mut map = Map::new();
    map.insert("model".into(), json!("user-model"));
    map.insert("user".into(), json!("alice"));

    let mut sys = Map::new();
    sys.insert("model".into(), json!("claude-3-7-sonnet"));

    let tpl = "Model: {{model}}, User: {{user}}";
    let out = render_prompt(
        tpl,
        Some(&map),
        Some(RenderPromptOptions {
            strict: false,
            system_variables: Some(sys),
        }),
    )
    .unwrap();
    assert_eq!(out, "Model: claude-3-7-sonnet, User: alice");
}

#[test]
fn audio_format_validation() {
    use nrouter::{validate_audio_format, VALID_AUDIO_FORMATS};
    for fmt in VALID_AUDIO_FORMATS {
        assert!(validate_audio_format(fmt).is_ok());
        assert!(validate_audio_format(&format!(" {} ", fmt.to_ascii_uppercase())).is_ok());
    }
    assert!(validate_audio_format("ogg").is_err());
    assert!(validate_audio_format("mp4").is_err());
    assert!(validate_audio_format("").is_err());
}
