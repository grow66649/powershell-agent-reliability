use std::{fs, path::PathBuf, time::Duration};

use anyhow::{Context, Result};
use rmcp::{
    ServiceExt,
    model::CallToolRequestParams,
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

fn args(value: serde_json::Value) -> serde_json::Map<String, serde_json::Value> {
    serde_json::from_value(value).expect("object tool arguments")
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn concurrent_calls_keep_results_isolated() -> Result<()> {
    let transport = TokioChildProcess::new(
        tokio::process::Command::new(server_binary()).configure(|command| {
            command.current_dir(env!("CARGO_MANIFEST_DIR"));
        }),
    )?;
    let mut client = ().serve(transport).await.context("initialize client")?;

    let timeout = CallToolRequestParams::new("diagnose_failure")
        .with_arguments(args(json!({"timed_out": true})));
    let native = CallToolRequestParams::new("diagnose_failure")
        .with_arguments(args(json!({"exit_code": 7, "native_process": true})));
    let verify = CallToolRequestParams::new("verify_result").with_arguments(args(json!({
        "command_exit_code": 0,
        "mode": "all",
        "checks": [{"kind": "directory_exists", "path": "."}]
    })));

    let (timeout, native, verify) = tokio::join!(
        client.call_tool(timeout),
        client.call_tool(native),
        client.call_tool(verify),
    );

    let timeout = timeout?
        .structured_content
        .context("timeout structured result")?;
    let native = native?
        .structured_content
        .context("native structured result")?;
    let verify = verify?
        .structured_content
        .context("verify structured result")?;
    assert_eq!(timeout["failure_class"], "TIMEOUT_CANCELLATION");
    assert_eq!(native["failure_class"], "NATIVE_PROCESS_OUTCOME");
    assert_eq!(verify["task_succeeded"], true);

    let invalid = CallToolRequestParams::new("diagnose_failure")
        .with_arguments(args(json!({"expected_cwd_sha256": "bad"})));
    let timeout = CallToolRequestParams::new("diagnose_failure")
        .with_arguments(args(json!({"timed_out": true})));
    let (invalid, timeout) = tokio::join!(client.call_tool(invalid), client.call_tool(timeout));
    assert_eq!(invalid?.is_error, Some(true));
    let timeout = timeout?
        .structured_content
        .context("timeout after peer error")?;
    assert_eq!(timeout["failure_class"], "TIMEOUT_CANCELLATION");

    client.close().await.context("close client")?;
    Ok(())
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn blocking_verification_does_not_starve_diagnosis() -> Result<()> {
    let root = std::env::temp_dir().join(format!("psr-concurrency-{}", std::process::id()));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root)?;
    let artifact = root.join("large.bin");
    let file = fs::File::create(&artifact)?;
    file.set_len(64 * 1024 * 1024)?;

    let transport = TokioChildProcess::new(
        tokio::process::Command::new(server_binary()).configure(|command| {
            command.current_dir(env!("CARGO_MANIFEST_DIR"));
        }),
    )?;
    let mut client = ().serve(transport).await.context("initialize client")?;
    let checks: Vec<_> = (0..32)
        .map(|_| {
            json!({
                "kind": "file_sha256",
                "path": "large.bin",
                "expected_sha256": "0".repeat(64)
            })
        })
        .collect();
    let verify = CallToolRequestParams::new("verify_result").with_arguments(args(json!({
        "cwd": root.display().to_string(), "mode": "all", "checks": checks
    })));

    let verify_peer = client.peer().clone();
    let verify_task = tokio::spawn(async move { verify_peer.call_tool(verify).await });
    tokio::time::sleep(Duration::from_millis(20)).await;

    let diagnose = CallToolRequestParams::new("diagnose_failure")
        .with_arguments(args(json!({"timed_out": true})));
    let diagnose = tokio::time::timeout(Duration::from_millis(100), client.call_tool(diagnose))
        .await
        .context("diagnosis was starved by file hashing")??;
    let structured = diagnose
        .structured_content
        .context("diagnosis structured result")?;
    assert_eq!(structured["failure_class"], "TIMEOUT_CANCELLATION");

    let verify = verify_task.await.context("join verify request")??;
    let structured = verify
        .structured_content
        .context("verify structured result")?;
    assert_eq!(structured["checks"].as_array().map(Vec::len), Some(32));

    client.close().await.context("close client")?;
    let _ = fs::remove_dir_all(&root);
    Ok(())
}
