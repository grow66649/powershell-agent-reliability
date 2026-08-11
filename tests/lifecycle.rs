use std::{path::PathBuf, time::Instant};

use anyhow::{Context, Result};
use rmcp::{
    ServiceExt,
    model::CallToolRequestParams,
    service::QuitReason,
    transport::{ConfigureCommandExt, TokioChildProcess},
};
use serde_json::json;

fn server_binary() -> PathBuf {
    let profile = if cfg!(debug_assertions) { "debug" } else { "release" };
    let binary = if cfg!(windows) {
        "powershell-agent-reliability.exe"
    } else {
        "powershell-agent-reliability"
    };

    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("target")
        .join(profile)
        .join(binary)
}

#[tokio::test]
async fn stdio_server_completes_mcp_lifecycle() -> Result<()> {
    let binary = server_binary();
    let lifecycle_started = Instant::now();
    let transport = TokioChildProcess::new(
        tokio::process::Command::new(&binary).configure(|command| {
            command.current_dir(env!("CARGO_MANIFEST_DIR"));
        }),
    )
    .with_context(|| format!("spawn MCP server at {}", binary.display()))?;
    let mut client = ().serve(transport).await.context("initialize MCP client")?;
    let tools = client.list_all_tools().await.context("list MCP tools")?;
    let mut names: Vec<_> = tools.iter().map(|tool| tool.name.to_string()).collect();
    names.sort();
    assert_eq!(names, ["diagnose_failure", "inspect_environment", "verify_result"]);

    let inspect_arguments = serde_json::from_value(json!({
        "critical_executables": [],
        "task_env_delta": {}
    }))
    .context("build inspect_environment arguments")?;
    let inspect_result = client
        .call_tool(
            CallToolRequestParams::new("inspect_environment").with_arguments(inspect_arguments),
        )
        .await
        .context("call inspect_environment")?;
    let structured = inspect_result
        .structured_content
        .context("inspect_environment should return structured content")?;
    assert_eq!(structured["schema_version"], 1);
    assert!(structured["path_fingerprint_sha256"].as_str().is_some());
    let diagnose_arguments = serde_json::from_value(json!({
        "timed_out": true
    }))
    .context("build diagnose_failure arguments")?;
    let diagnose_result = client
        .call_tool(
            CallToolRequestParams::new("diagnose_failure").with_arguments(diagnose_arguments),
        )
        .await
        .context("call diagnose_failure")?;
    let structured = diagnose_result
        .structured_content
        .context("diagnose_failure should return structured content")?;
    assert_eq!(structured["failure_class"], "TIMEOUT_CANCELLATION");

    let verify_arguments = serde_json::from_value(json!({
        "command_exit_code": 0,
        "mode": "all",
        "checks": [{"kind": "directory_exists", "path": "."}]
    }))
    .context("build verify_result arguments")?;
    let verify_result = client
        .call_tool(CallToolRequestParams::new("verify_result").with_arguments(verify_arguments))
        .await
        .context("call verify_result")?;
    let structured = verify_result
        .structured_content
        .context("verify_result should return structured content")?;
    assert_eq!(structured["task_succeeded"], true);

    let quit_reason = client.close().await.context("graceful client shutdown")?;
    assert!(matches!(quit_reason, QuitReason::Cancelled | QuitReason::Closed));
    assert!(client.is_closed());

    let total_ms = lifecycle_started.elapsed().as_secs_f64() * 1_000.0;
    eprintln!("lifecycle=ok profile={} total_ms={total_ms:.3}", if cfg!(debug_assertions) { "debug" } else { "release" });
    Ok(())
}
