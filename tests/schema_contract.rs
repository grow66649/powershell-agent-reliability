use powershell_agent_reliability::{
    diagnosis::DiagnoseFailureRequest,
    environment::InspectEnvironmentRequest,
    verification::VerifyResultRequest,
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
        verification["$defs"]["VerificationCheck"]["oneOf"][0]["properties"]["path"]["maxLength"],
        32768
    );
    assert_eq!(
        verification["$defs"]["VerificationCheck"]["oneOf"][3]["properties"]["expected_sha256"]["pattern"],
        "^[0-9A-Fa-f]{64}$"
    );
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
