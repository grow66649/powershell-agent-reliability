use std::collections::BTreeMap;

use powershell_agent_reliability::environment::{
    InspectEnvironmentRequest, inspect_environment,
};

#[test]
fn digest_is_privacy_bounded_and_resolves_explicit_executable() {
    let cwd = std::env::current_dir().expect("cwd");
    let exe = std::env::current_exe().expect("current exe");
    let secret = "PSR_SENTINEL_SECRET_VALUE";
    let mut task_env_delta = BTreeMap::new();
    task_env_delta.insert("PSR_TEST_SENTINEL".to_owned(), secret.to_owned());
    let request = InspectEnvironmentRequest {
        shell_executable: Some("powershell.exe".to_owned()),
        cwd: Some(cwd.display().to_string()),
        critical_executables: vec![exe.display().to_string()],
        task_env_delta,
    };

    let digest = inspect_environment(request).expect("inspect environment");
    assert_eq!(digest.schema_version, 1);
    assert!(digest.cwd.exists);
    assert_eq!(digest.critical_executables.len(), 1);
    assert_eq!(digest.critical_executables[0].resolution_status, "resolved");
    let shell = digest.shell.as_ref().expect("shell identity");
    assert_eq!(shell.family, "WindowsPowerShell");
    assert_eq!(shell.resolution_status, "resolved");
    assert!(shell.version.is_some());
    let json = serde_json::to_string(&digest).expect("serialize digest");
    assert!(!json.contains(&cwd.display().to_string()));
    assert!(!json.contains(&std::env::var("PATH").unwrap_or_default()));
    assert!(!json.contains(&exe.display().to_string()));
    assert!(!json.contains(secret));
    assert!(json.contains("PSR_TEST_SENTINEL"));
}

#[test]
fn request_limits_fail_closed() {
    let too_many = InspectEnvironmentRequest {
        shell_executable: None,
        cwd: None,
        critical_executables: (0..17).map(|index| format!("tool-{index}.exe")).collect(),
        task_env_delta: Default::default(),
    };
    assert!(inspect_environment(too_many).is_err());

    let mut invalid_env = BTreeMap::new();
    invalid_env.insert("BAD=KEY".to_owned(), "value".to_owned());
    let invalid = InspectEnvironmentRequest {
        shell_executable: None,
        cwd: None,
        critical_executables: vec![],
        task_env_delta: invalid_env,
    };
    assert!(inspect_environment(invalid).is_err());
}
