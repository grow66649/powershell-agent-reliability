use std::{path::PathBuf, time::Instant};

use anyhow::{Context, Result};
use rmcp::{
    ServiceExt,
    model::CallToolRequestParams,
    service::QuitReason,
    transport::{ConfigureCommandExt, TokioChildProcess},
};

fn server_binary() -> PathBuf {
    let profile = if cfg!(debug_assertions) { "debug" } else { "release" };
    let binary = if cfg!(windows) {
        "psr-rmcp-native-canary.exe"
    } else {
        "psr-rmcp-native-canary"
    };

    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("target")
        .join(profile)
        .join(binary)
}

#[tokio::test]
async fn stdio_canary_completes_mcp_lifecycle() -> Result<()> {
    let binary = server_binary();
    let lifecycle_started = Instant::now();
    let spawn_started = Instant::now();
    let transport = TokioChildProcess::new(
        tokio::process::Command::new(&binary).configure(|command| {
            command.current_dir(env!("CARGO_MANIFEST_DIR"));
        }),
    )
    .with_context(|| format!("spawn MCP canary at {}", binary.display()))?;
    let spawn_ms = spawn_started.elapsed().as_secs_f64() * 1_000.0;

    let handshake_started = Instant::now();
    let mut client = ().serve(transport).await.context("initialize MCP client")?;
    let handshake_ms = handshake_started.elapsed().as_secs_f64() * 1_000.0;

    let list_started = Instant::now();
    let tools = client.list_all_tools().await.context("list MCP tools")?;
    let list_ms = list_started.elapsed().as_secs_f64() * 1_000.0;
    let names: Vec<_> = tools.iter().map(|tool| tool.name.as_ref()).collect();
    assert_eq!(names, ["psr_ping"]);

    let call_started = Instant::now();
    let result = client
        .call_tool(CallToolRequestParams::new("psr_ping"))
        .await
        .context("call psr_ping")?;
    let call_ms = call_started.elapsed().as_secs_f64() * 1_000.0;
    let text = result
        .content
        .first()
        .and_then(|content| content.as_text())
        .map(|text| text.text.as_str())
        .context("psr_ping should return one text content item")?;
    assert_eq!(text, "psr-ok");

    let close_started = Instant::now();
    let quit_reason = client.close().await.context("graceful client shutdown")?;
    let close_ms = close_started.elapsed().as_secs_f64() * 1_000.0;
    assert!(matches!(quit_reason, QuitReason::Cancelled | QuitReason::Closed));
    assert!(client.is_closed());

    let total_ms = lifecycle_started.elapsed().as_secs_f64() * 1_000.0;
    eprintln!(
        "lifecycle=ok profile={} startup_ms={spawn_ms:.3} handshake_ms={handshake_ms:.3} list_ms={list_ms:.3} call_ms={call_ms:.3} close_ms={close_ms:.3} total_ms={total_ms:.3}",
        if cfg!(debug_assertions) { "debug" } else { "release" },
    );
    Ok(())
}
