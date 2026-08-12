use powershell_agent_reliability::PsrServer;
use rmcp::ServerHandler;

#[test]
fn runtime_instructions_bound_failure_only_intervention() {
    let instructions = PsrServer.get_info().instructions.expect("server instructions");
    assert!(instructions.contains("Freeze the task post-condition before diagnosis or repair"));
    assert!(instructions.contains("diagnose_failure once per failure boundary"));
    assert!(instructions.contains("at most one repair"));
    assert!(instructions.contains("verify_result once after repair"));
    assert!(instructions.contains("Never use observed candidate output as the expected verification value"));
}

#[test]
fn companion_skill_documents_the_same_guardrails() {
    let skill = include_str!("../skills/powershell-reliability/SKILL.md");
    let reference = include_str!("../skills/powershell-reliability/references/tool-usage.md");
    for text in [skill, reference] {
        assert!(text.contains("Freeze the task post-condition before diagnosis or repair"));
        assert!(text.contains("probe/helper errors are not evidence about the original task failure"));
        assert!(text.contains("diagnose_failure once per failure boundary"));
        assert!(text.contains("If that repair fails the frozen post-condition, stop and report failure"));
        assert!(text.contains("Never use observed candidate output as the expected verification value"));
    }
}
