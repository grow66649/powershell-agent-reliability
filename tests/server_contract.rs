use powershell_agent_reliability::PsrServer;
use rmcp::ServerHandler;

#[test]
fn server_identity_and_instructions_are_product_specific() {
    let info = PsrServer.get_info();
    assert_eq!(info.server_info.name, "powershell-agent-reliability");
    assert_eq!(info.server_info.version, "0.1.0");
    assert_eq!(info.server_info.title.as_deref(), Some("PowerShell Agent Reliability"));
    assert!(
        info.instructions
            .as_deref()
            .is_some_and(|text| text.contains("failure-only"))
    );
    assert!(info.capabilities.tools.is_some());
}
