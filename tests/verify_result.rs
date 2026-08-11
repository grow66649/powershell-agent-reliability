use std::{fs, process, sync::atomic::{AtomicUsize, Ordering}};

use sha2::Digest;

use powershell_agent_reliability::verification::{
    VerificationCheck, VerificationMode, VerifyResultRequest, verify_result,
};

static FIXTURE_COUNTER: AtomicUsize = AtomicUsize::new(0);

fn fixture_root() -> std::path::PathBuf {
    let sequence = FIXTURE_COUNTER.fetch_add(1, Ordering::Relaxed);
    std::env::temp_dir().join(format!("psr-verify-result-{}-{sequence}", process::id()))
}

#[test]
fn task_outcome_is_independent_from_command_exit_code() {
    let root = fixture_root();
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).expect("create fixture root");
    fs::write(root.join("artifact.txt"), b"ok").expect("write fixture");

    let result = verify_result(VerifyResultRequest {
        command_exit_code: Some(7),
        cwd: Some(root.display().to_string()),
        mode: VerificationMode::All,
        checks: vec![VerificationCheck::FileExists {
            path: "artifact.txt".to_owned(),
        }],
    })
    .expect("verify result");

    assert_eq!(result.command_succeeded, Some(false));
    assert!(result.task_succeeded);
    assert!(result.checks[0].passed);
    let _ = fs::remove_dir_all(&root);
}
#[test]
fn missing_required_artifact_blocks_false_completion() {
    let root = fixture_root();
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).expect("create fixture root");

    let result = verify_result(VerifyResultRequest {
        command_exit_code: Some(0),
        cwd: Some(root.display().to_string()),
        mode: VerificationMode::All,
        checks: vec![VerificationCheck::FileExists {
            path: "missing.txt".to_owned(),
        }],
    })
    .expect("verify result");

    assert_eq!(result.command_succeeded, Some(true));
    assert!(!result.task_succeeded);
    assert!(!result.checks[0].passed);
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn hash_and_absence_checks_are_deterministic_and_private() {
    let root = fixture_root();
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).expect("create fixture root");
    fs::write(root.join("artifact.txt"), b"ok").expect("write fixture");
    let expected = sha2::Sha256::digest(b"ok")
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect::<String>();
    let result = verify_result(VerifyResultRequest {
        command_exit_code: None,
        cwd: Some(root.display().to_string()),
        mode: VerificationMode::All,
        checks: vec![
            VerificationCheck::FileSha256 {
                path: "artifact.txt".to_owned(),
                expected_sha256: expected,
            },
            VerificationCheck::FileAbsent {
                path: "not-created.txt".to_owned(),
            },
        ],
    })
    .expect("verify result");

    assert!(result.task_succeeded);
    assert!(result.checks.iter().all(|check| check.passed));
    let json = serde_json::to_string(&result).expect("serialize verification result");
    assert!(!json.contains(&root.display().to_string()));
    let _ = fs::remove_dir_all(&root);
}



