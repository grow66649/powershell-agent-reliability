pub mod diagnosis;
pub mod environment;

use diagnosis::{DiagnosisResult, DiagnoseFailureRequest, diagnose_failure};
use environment::{EnvironmentDigest, InspectEnvironmentRequest, inspect_environment};
use rmcp::{
    Json, ServerHandler,
    handler::server::wrapper::Parameters,
    tool, tool_handler, tool_router,
};

#[derive(Debug, Clone, Default)]
pub struct PsrServer;

#[tool_router]
impl PsrServer {
    #[tool(
        name = "inspect_environment",
        description = "Return privacy-bounded shell/cwd/PATH/executable identity for a failed Windows task."
    )]
    fn inspect_environment(
        &self,
        Parameters(request): Parameters<InspectEnvironmentRequest>,
    ) -> Result<Json<EnvironmentDigest>, String> {
        inspect_environment(request).map(Json)
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
}

#[tool_handler]
impl ServerHandler for PsrServer {}
