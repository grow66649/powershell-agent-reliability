pub mod diagnosis;
pub mod environment;
pub mod verification;

use diagnosis::{DiagnosisResult, DiagnoseFailureRequest, diagnose_failure};
use environment::{EnvironmentDigest, InspectEnvironmentRequest, inspect_environment};
use rmcp::{
    Json, ServerHandler,
    handler::server::wrapper::Parameters,
    model::{Implementation, ServerCapabilities, ServerInfo},
    tool, tool_handler, tool_router,
};
use verification::{VerificationResult, VerifyResultRequest, verify_result};

#[derive(Debug, Clone, Default)]
pub struct PsrServer;

async fn run_blocking<T, F>(work: F) -> Result<T, String>
where
    T: Send + 'static,
    F: FnOnce() -> Result<T, String> + Send + 'static,
{
    tokio::task::spawn_blocking(work)
        .await
        .map_err(|_| "blocking worker failed".to_owned())?
}

#[tool_router]
impl PsrServer {
    #[tool(
        name = "inspect_environment",
        description = "Return privacy-bounded shell/cwd/PATH/executable identity for a failed Windows task."
    )]
    async fn inspect_environment(
        &self,
        Parameters(request): Parameters<InspectEnvironmentRequest>,
    ) -> Result<Json<EnvironmentDigest>, String> {
        run_blocking(move || inspect_environment(request)).await.map(Json)
    }
    #[tool(
        name = "diagnose_failure",
        description = "Classify bounded Windows/PowerShell failure evidence and return one conservative next action."
    )]
    fn diagnose_failure(
        &self,
        Parameters(request): Parameters<DiagnoseFailureRequest>,
    ) -> Result<Json<DiagnosisResult>, String> {
        diagnose_failure(request).map(Json)
    }

    #[tool(
        name = "verify_result",
        description = "Evaluate explicit deterministic post-conditions independently from command exit status."
    )]
    async fn verify_result(
        &self,
        Parameters(request): Parameters<VerifyResultRequest>,
    ) -> Result<Json<VerificationResult>, String> {
        run_blocking(move || verify_result(request)).await.map(Json)
    }
}

#[tool_handler]
impl ServerHandler for PsrServer {
    fn get_info(&self) -> ServerInfo {
        ServerInfo::new(ServerCapabilities::builder().enable_tools().build())
            .with_server_info(
                Implementation::new("powershell-agent-reliability", env!("CARGO_PKG_VERSION"))
                    .with_title("PowerShell Agent Reliability")
                    .with_description("Failure-only Windows execution diagnosis and post-condition verification."),
            )
            .with_instructions("Use failure-only after a bounded Windows command failure or failed post-condition. Freeze the task post-condition before diagnosis or repair. Call diagnose_failure once per failure boundary; call it again only after UNKNOWN with new missing facts or after a genuinely new failure boundary. Perform at most one repair. Call verify_result once after repair against the frozen post-condition. Never weaken verification checks. Never use observed candidate output as the expected verification value. Codex Desktop remains the command/process owner. Never request full PATH/environment dumps or weaken sandbox/ACL/security settings.")
    }
}
