pub mod environment;

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
}

#[tool_handler]
impl ServerHandler for PsrServer {}
