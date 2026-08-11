use powershell_agent_reliability::environment::{
    inspect_environment, InspectEnvironmentRequest,
};

#[test]
fn digest_is_privacy_bounded_and_resolves_explicit_executable() {
    let cwd = std::env::current_dir().expect("cwd");
    let exe = std::env::current_exe().expect("current exe");
    let request = InspectEnvironmentRequest {
        shell_executable: Some("powershell.exe".to_owned()),
        cwd: Some(cwd.display().to_string()),
        critical_executables: vec![exe.display().to_string()],
        task_env_delta: Default::default(),
    };

    let digest = inspect_environment(request).expect("inspect environment");
    assert_eq!(digest.schema_version, 1);
    assert!(digest.cwd.exists);
    assert_eq!(digest.critical_executables.len(), 1);
    assert_eq!(digest.critical_executables[0].resolution_status, "resolved");
    assert!(digest.shell.is_some());

    let json = serde_json::to_string(&digest).expect("serialize digest");
    assert!(!json.contains(&cwd.display().to_string()));
    assert!(!json.contains(&std::env::var("PATH").unwrap_or_default()));
    assert!(!json.contains(&exe.display().to_string()));
}
