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

#[test]
fn ambiguous_evidence_stays_unknown() {
    let diagnosis = diagnose_failure(base()).expect("unknown diagnosis");
    assert_eq!(diagnosis.failure_class, "UNKNOWN");
    assert_eq!(diagnosis.confidence, "low");
}
