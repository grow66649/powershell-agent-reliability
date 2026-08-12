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




#[test]
fn invalid_or_empty_post_conditions_fail_closed() {
    let empty = VerifyResultRequest {
        command_exit_code: Some(0),
        cwd: None,
        mode: VerificationMode::All,
        checks: vec![],
    };
    assert!(verify_result(empty).is_err());

    let invalid_hash = VerifyResultRequest {
        command_exit_code: Some(0),
        cwd: None,
        mode: VerificationMode::All,
        checks: vec![VerificationCheck::FileSha256 {
            path: "artifact.txt".to_owned(),
            expected_sha256: "not-a-sha256".to_owned(),
        }],
    };
    assert!(verify_result(invalid_hash).is_err());
}

#[test]
fn any_mode_succeeds_when_one_explicit_check_passes() {
    let root = fixture_root();
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).expect("create fixture root");
    fs::write(root.join("present.txt"), b"ok").expect("write fixture");
    let result = verify_result(VerifyResultRequest {
        command_exit_code: None,
        cwd: Some(root.display().to_string()),
        mode: VerificationMode::Any,
        checks: vec![
            VerificationCheck::FileExists {
                path: "missing.txt".to_owned(),
            },
            VerificationCheck::FileExists {
                path: "present.txt".to_owned(),
            },
        ],
    })
    .expect("verify any mode");
    assert!(result.task_succeeded);
    assert_eq!(result.checks.iter().filter(|check| check.passed).count(), 1);
    let _ = fs::remove_dir_all(&root);
}

#[test]
fn file_sha256_rejects_files_larger_than_64_mib() {
    let root = fixture_root();
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root).expect("create fixture root");
    let artifact = root.join("too-large.bin");
    let file = fs::File::create(&artifact).expect("create oversized fixture");
    file.set_len(64 * 1024 * 1024 + 1)
        .expect("size oversized fixture");

    let result = verify_result(VerifyResultRequest {
        command_exit_code: None,
        cwd: Some(root.display().to_string()),
        mode: VerificationMode::All,
        checks: vec![VerificationCheck::FileSha256 {
            path: "too-large.bin".to_owned(),
            expected_sha256: "0".repeat(64),
        }],
    })
    .expect("oversized hash request should return a bounded check result");

    assert!(!result.task_succeeded);
    assert_eq!(result.checks[0].status, "error");
    assert_eq!(result.checks[0].error_kind.as_deref(), Some("FileTooLarge"));
    assert!(result.checks[0].observed_sha256.is_none());
    let _ = fs::remove_dir_all(&root);
}
