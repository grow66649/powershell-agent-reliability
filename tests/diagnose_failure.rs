use powershell_agent_reliability::diagnosis::{
    DiagnoseFailureRequest, ShellObservation, ShellRequirement, diagnose_failure,
};

fn base() -> DiagnoseFailureRequest {
    DiagnoseFailureRequest::default()
}

#[test]
fn classifies_timeout_and_post_condition_mismatch() {
    let timeout = diagnose_failure(DiagnoseFailureRequest {
        timed_out: true,
        ..base()
    })
    .expect("timeout diagnosis");
    assert_eq!(timeout.failure_class, "TIMEOUT_CANCELLATION");
    assert_eq!(timeout.confidence, "high");

    let mismatch = diagnose_failure(DiagnoseFailureRequest {
        exit_code: Some(0),
        post_condition: Some(false),
        ..base()
    })
    .expect("post condition diagnosis");
    assert_eq!(mismatch.failure_class, "POST_CONDITION_MISMATCH");
}
#[test]
fn classifies_environment_cwd_and_shell_boundaries() {
    let environment = diagnose_failure(DiagnoseFailureRequest {
        resolution_before_sha256: Some("a".repeat(64)),
        resolution_after_sha256: Some("b".repeat(64)),
        ..base()
    })
    .expect("environment diagnosis");
    assert_eq!(environment.failure_class, "ENVIRONMENT_STALENESS");

    let cwd = diagnose_failure(DiagnoseFailureRequest {
        expected_cwd_sha256: Some("c".repeat(64)),
        actual_cwd_sha256: Some("d".repeat(64)),
        ..base()
    })
    .expect("cwd diagnosis");
    assert_eq!(cwd.failure_class, "CWD_PATH_IDENTITY");

    let shell = diagnose_failure(DiagnoseFailureRequest {
        required_shell: Some(ShellRequirement {
            family: "PowerShell".to_owned(),
            minimum_major: Some(7),
            minimum_minor: Some(4),
        }),
        observed_shell: Some(ShellObservation {
            family: "WindowsPowerShell".to_owned(),
            major: Some(5),
            minor: Some(1),
        }),
        ..base()
    })
    .expect("shell diagnosis");
    assert_eq!(shell.failure_class, "SHELL_VERSION_MISMATCH");
}
#[test]
fn classifies_quoting_native_and_desktop_boundaries() {
    let quoting = diagnose_failure(DiagnoseFailureRequest {
        parser_or_binding_failure: true,
        nested_command_boundary: true,
        literal_dollar_expected: true,
        ..base()
    })
    .expect("quoting diagnosis");
    assert_eq!(quoting.failure_class, "QUOTING_EXPANSION");

    let native = diagnose_failure(DiagnoseFailureRequest {
        exit_code: Some(7),
        native_process: true,
        stderr_excerpt: Some("ERR".to_owned()),
        ..base()
    })
    .expect("native diagnosis");
    assert_eq!(native.failure_class, "NATIVE_PROCESS_OUTCOME");

    let sandbox = diagnose_failure(DiagnoseFailureRequest {
        desktop_sandbox_signal: true,
        stderr_excerpt: Some("Access denied".to_owned()),
        ..base()
    })
    .expect("sandbox diagnosis");
    assert_eq!(sandbox.failure_class, "DESKTOP_SANDBOX_BOUNDARY");
}

fn assert_specific_with_mismatch(request: DiagnoseFailureRequest, expected: &str) {
    let diagnosis = diagnose_failure(request).expect("specific diagnosis");
    assert_eq!(diagnosis.failure_class, expected);
    assert!(diagnosis.evidence.iter().any(|item| item.code == "command_task_outcome_disagree"));
}

#[test]
fn specific_causal_evidence_outranks_command_task_mismatch() {
    assert_specific_with_mismatch(DiagnoseFailureRequest { exit_code: Some(0), post_condition: Some(false), resolution_before_sha256: Some("a".repeat(64)), resolution_after_sha256: Some("b".repeat(64)), ..base() }, "ENVIRONMENT_STALENESS");
    assert_specific_with_mismatch(DiagnoseFailureRequest { exit_code: Some(0), post_condition: Some(false), expected_cwd_sha256: Some("c".repeat(64)), actual_cwd_sha256: Some("d".repeat(64)), ..base() }, "CWD_PATH_IDENTITY");
    assert_specific_with_mismatch(DiagnoseFailureRequest { exit_code: Some(0), post_condition: Some(false), required_shell: Some(ShellRequirement { family: "PowerShell".to_owned(), minimum_major: Some(7), minimum_minor: Some(0) }), observed_shell: Some(ShellObservation { family: "WindowsPowerShell".to_owned(), major: Some(5), minor: Some(1) }), ..base() }, "SHELL_VERSION_MISMATCH");
    assert_specific_with_mismatch(DiagnoseFailureRequest { exit_code: Some(0), post_condition: Some(false), parser_or_binding_failure: true, nested_command_boundary: true, literal_dollar_expected: true, ..base() }, "QUOTING_EXPANSION");
    assert_specific_with_mismatch(DiagnoseFailureRequest { exit_code: Some(7), post_condition: Some(true), native_process: true, ..base() }, "NATIVE_PROCESS_OUTCOME");
}

#[test]
fn ambiguous_evidence_stays_unknown() {
    let diagnosis = diagnose_failure(base()).expect("unknown diagnosis");
    assert_eq!(diagnosis.failure_class, "UNKNOWN");
    assert_eq!(diagnosis.confidence, "low");
}
#[test]
fn post_condition_without_command_exit_does_not_invent_command_failure() {
    let diagnosis = diagnose_failure(DiagnoseFailureRequest {
        post_condition: Some(true),
        ..base()
    })
    .expect("diagnosis without exit code");
    assert_eq!(diagnosis.failure_class, "UNKNOWN");
}
#[test]
fn windowsapps_path_without_access_signal_is_not_enough_for_sandbox_classification() {
    let diagnosis = diagnose_failure(DiagnoseFailureRequest {
        exit_code: Some(7),
        native_process: true,
        stderr_excerpt: Some("C:\\Program Files\\WindowsApps\\tool.exe returned 7".to_owned()),
        ..base()
    })
    .expect("windowsapps path diagnosis");
    assert_eq!(diagnosis.failure_class, "NATIVE_PROCESS_OUTCOME");
}

#[test]
fn diagnosis_does_not_echo_bounded_log_excerpt() {
    let sentinel = "Access denied PSR_PRIVATE_SENTINEL";
    let diagnosis = diagnose_failure(DiagnoseFailureRequest {
        stderr_excerpt: Some(sentinel.to_owned()),
        ..base()
    })
    .expect("diagnosis");
    assert_eq!(diagnosis.failure_class, "DESKTOP_SANDBOX_BOUNDARY");
    let json = serde_json::to_string(&diagnosis).expect("serialize diagnosis");
    assert!(!json.contains("PSR_PRIVATE_SENTINEL"));
}

#[test]
fn invalid_hashes_and_oversized_excerpts_fail_closed() {
    let invalid_hash = diagnose_failure(DiagnoseFailureRequest {
        expected_cwd_sha256: Some("bad".to_owned()),
        ..base()
    });
    assert!(invalid_hash.is_err());

    let oversized = diagnose_failure(DiagnoseFailureRequest {
        stderr_excerpt: Some("x".repeat(4097)),
        ..base()
    });
    assert!(oversized.is_err());
}
