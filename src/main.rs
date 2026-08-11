use rmcp::{
    ServerHandler, ServiceExt,
    tool,
    tool_handler,
    tool_router,
    transport::stdio,
};

#[derive(Debug, Clone)]
struct PsrCanary;

#[tool_router]
impl PsrCanary {
    #[tool(
        name = "psr_ping",
        description = "Return a deterministic local MCP canary response."
    )]
    fn psr_ping(&self) -> String {
        "psr-ok".to_owned()
    }
}

#[tool_handler]
impl ServerHandler for PsrCanary {}

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    PsrCanary.serve(stdio()).await?.waiting().await?;
    Ok(())
}
