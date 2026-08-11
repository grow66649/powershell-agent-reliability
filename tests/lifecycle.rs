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
    let names: Vec<_> = tools.iter().map(|tool| tool.name.as_ref()).collect();
    assert_eq!(names, ["inspect_environment"]);

    let arguments = serde_json::from_value(json!({
        "critical_executables": [],
        "task_env_delta": {}
    }))
    .context("build inspect_environment arguments")?;
    let result = client
        .call_tool(CallToolRequestParams::new("inspect_environment").with_arguments(arguments))
        .await
        .context("call inspect_environment")?;
    let structured = result
        .structured_content
        .context("inspect_environment should return structured content")?;
    assert_eq!(structured["schema_version"], 1);
    assert!(structured["path_fingerprint_sha256"].as_str().is_some());

    let quit_reason = client.close().await.context("graceful client shutdown")?;
    assert!(matches!(quit_reason, QuitReason::Cancelled | QuitReason::Closed));
    assert!(client.is_closed());

    let total_ms = lifecycle_started.elapsed().as_secs_f64() * 1_000.0;
    eprintln!("lifecycle=ok profile={} total_ms={total_ms:.3}", if cfg!(debug_assertions) { "debug" } else { "release" });
    Ok(())
}
