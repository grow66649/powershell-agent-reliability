use powershell_agent_reliability::PsrServer;
use rmcp::ServerHandler;

#[test]
fn runtime_instructions_bound_failure_only_intervention() {
    let instructions = PsrServer.get_info().instructions.expect("server instructions");
    assert!(instructions.contains("Freeze the task post-condition before diagnosis or repair"));
    assert!(instructions.contains("diagnose_failure once per failure boundary"));
    assert!(instructions.contains("after UNKNOWN with one newly collected missing fact"));
    assert!(instructions.contains("at most one repair"));
    assert!(instructions.contains("verify_result once after repair"));
    assert!(instructions.contains("Never use observed candidate output as the expected verification value"));
}

#[test]
fn companion_skill_documents_the_same_guardrails() {
    let skill = include_str!("../skills/powershell-reliability/SKILL.md");
    for required in [
        "Before the first execution attempt",
        "Pure command/post-condition disagreement",
        "do not call `inspect_environment`",
        "one missing fact tied to the failed boundary",
        "at most one evidence-backed repair",
        "exactly one `verify_result`",
        "Never weaken criteria",
        "Never derive expected values from repaired candidate output",
    ] {
        assert!(skill.contains(required), "missing Skill guardrail: {required}");
    }
    assert!(!skill.contains("references/tool-usage.md"));
}
