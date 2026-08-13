use powershell_agent_reliability::{
    diagnosis::{DiagnoseFailureRequest, DiagnosisResult},
    environment::{EnvironmentDigest, InspectEnvironmentRequest},
    verification::{VerificationResult, VerifyResultRequest},
};
use schemars::schema_for;

#[test]
fn tool_input_schema_exposes_collection_bounds() {
    let environment = serde_json::to_value(schema_for!(InspectEnvironmentRequest))
        .expect("environment schema");
    assert_eq!(
        environment["properties"]["critical_executables"]["maxItems"],
        16
    );
    assert_eq!(
        environment["properties"]["task_env_delta"]["maxProperties"],
        32
    );

    let diagnosis = serde_json::to_value(schema_for!(DiagnoseFailureRequest))
        .expect("diagnosis schema");
    assert_eq!(diagnosis["properties"]["stderr_excerpt"]["maxLength"], 4096);
    assert_eq!(
        diagnosis["properties"]["expected_cwd_sha256"]["pattern"],
        "^[0-9A-Fa-f]{64}$"
    );

    let verification = serde_json::to_value(schema_for!(VerifyResultRequest))
        .expect("verification schema");
    assert_eq!(verification["properties"]["checks"]["minItems"], 1);
    assert_eq!(verification["properties"]["checks"]["maxItems"], 32);
    assert_eq!(verification["properties"]["cwd"]["maxLength"], 32768);
    assert_eq!(
        verification["properties"]["checks"]["items"]["oneOf"][0]["properties"]["path"]["maxLength"],
        32768
    );
    assert_eq!(
        verification["properties"]["checks"]["items"]["oneOf"][3]["properties"]["expected_sha256"]["pattern"],
        "^[0-9A-Fa-f]{64}$"
    );
}
#[test]
fn tool_input_schema_inlines_nested_agent_arguments() {
    use rmcp::handler::server::tool::schema_for_input;

    let diagnosis = serde_json::Value::Object(
        schema_for_input::<DiagnoseFailureRequest>()
            .expect("diagnosis input schema")
            .as_ref()
            .clone(),
    );
    let observed_shell = &diagnosis["properties"]["observed_shell"];
    assert!(!observed_shell.to_string().contains("\"$ref\""));
    assert_eq!(observed_shell["type"], serde_json::json!(["object", "null"]));
    assert_eq!(observed_shell["properties"]["family"]["type"], "string");

    let verification = serde_json::Value::Object(
        schema_for_input::<VerifyResultRequest>()
            .expect("verification input schema")
            .as_ref()
            .clone(),
    );
    assert_eq!(verification["properties"]["mode"]["enum"], serde_json::json!(["all", "any"]));
    let check_items = &verification["properties"]["checks"]["items"];
    assert!(!check_items.to_string().contains("\"$ref\""));
    assert_eq!(check_items["oneOf"][0]["properties"]["kind"]["const"], "file_exists");
    assert_eq!(
        check_items["oneOf"][3]["properties"]["expected_sha256"]["type"],
        "string"
    );
}

#[test]
fn tool_output_schema_inlines_nested_agent_results() {
    use rmcp::handler::server::tool::schema_for_output;

    let diagnosis = serde_json::Value::Object(schema_for_output::<DiagnosisResult>().as_ref().clone());
    assert!(!diagnosis["properties"]["evidence"]["items"].to_string().contains("\"$ref\""));
    assert_eq!(diagnosis["properties"]["evidence"]["items"]["properties"]["code"]["type"], "string");
    assert!(!diagnosis["properties"]["next_action"].to_string().contains("\"$ref\""));

    let environment = serde_json::Value::Object(schema_for_output::<EnvironmentDigest>().as_ref().clone());
    assert!(!environment["properties"]["cwd"].to_string().contains("\"$ref\""));
    assert!(!environment["properties"]["critical_executables"]["items"].to_string().contains("\"$ref\""));

    let verification = serde_json::Value::Object(schema_for_output::<VerificationResult>().as_ref().clone());
    assert!(!verification["properties"]["checks"]["items"].to_string().contains("\"$ref\""));
    assert_eq!(verification["properties"]["checks"]["items"]["properties"]["passed"]["type"], "boolean");
}

#[test]
fn skill_reference_documents_exact_nested_tool_shapes() {
    let reference = include_str!("../skills/powershell-reliability/references/tool-usage.md");
    assert!(reference.contains("\"observed_shell\": {\"family\": \"PowerShell\", \"major\": 7, \"minor\": 6}"));
    assert!(reference.contains("{\"kind\": \"file_sha256\", \"path\": \"output.txt\", \"expected_sha256\":"));
    assert!(reference.contains("{\"kind\": \"file_size\", \"path\": \"output.txt\", \"min_bytes\": 5, \"max_bytes\": 5}"));
}
#[test]
fn tool_input_schema_rejects_unknown_fields() {
    let environment = serde_json::to_value(schema_for!(InspectEnvironmentRequest))
        .expect("environment schema");
    let diagnosis = serde_json::to_value(schema_for!(DiagnoseFailureRequest))
        .expect("diagnosis schema");
    let verification = serde_json::to_value(schema_for!(VerifyResultRequest))
        .expect("verification schema");

    assert_eq!(environment["additionalProperties"], false);
    assert_eq!(diagnosis["additionalProperties"], false);
    assert_eq!(verification["additionalProperties"], false);

    let bad_environment = serde_json::json!({"critical_executables": [], "typo": true});
    assert!(serde_json::from_value::<InspectEnvironmentRequest>(bad_environment).is_err());

    let bad_diagnosis = serde_json::json!({"timed_out": true, "typo": true});
    assert!(serde_json::from_value::<DiagnoseFailureRequest>(bad_diagnosis).is_err());
    let bad_verification = serde_json::json!({
        "checks": [{"kind": "file_exists", "path": "."}],
        "typo": true
    });
    assert!(serde_json::from_value::<VerifyResultRequest>(bad_verification).is_err());

    let bad_check = serde_json::json!({
        "checks": [{"kind": "file_exists", "path": ".", "typo": true}]
    });
    assert!(serde_json::from_value::<VerifyResultRequest>(bad_check).is_err());
}
