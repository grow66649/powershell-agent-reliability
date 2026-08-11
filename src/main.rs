use powershell_agent_reliability::PsrServer;
use rmcp::{ServiceExt, transport::stdio};

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    PsrServer::default().serve(stdio()).await?.waiting().await?;
    Ok(())
}
