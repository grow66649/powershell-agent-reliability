use rmcp::schemars::JsonSchema;
use serde::{Deserialize, Serialize};

const MAX_EXCERPT_BYTES: usize = 4096;

#[derive(Debug, Clone, Default, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct DiagnoseFailureRequest {
    #[serde(default)]
    pub exit_code: Option<i32>,
    #[serde(default)]
    #[schemars(extend("maxLength" = 4096))]
    pub stdout_excerpt: Option<String>,
    #[serde(default)]
    #[schemars(extend("maxLength" = 4096))]
    pub stderr_excerpt: Option<String>,
    #[serde(default)]
    pub timed_out: bool,
    #[serde(default)]
    pub post_condition: Option<bool>,
    #[serde(default)]
    pub native_process: bool,
    #[serde(default)]
    pub parser_or_binding_failure: bool,
    #[serde(default)]
    pub nested_command_boundary: bool,
    #[serde(default)]
    pub literal_dollar_expected: bool,
    #[serde(default)]
    pub desktop_sandbox_signal: bool,
    #[serde(default)]
    #[schemars(extend("pattern" = "^[0-9A-Fa-f]{64}$"))]
    pub expected_cwd_sha256: Option<String>,
    #[serde(default)]
    #[schemars(extend("pattern" = "^[0-9A-Fa-f]{64}$"))]
    pub actual_cwd_sha256: Option<String>,
    #[serde(default)]
    pub required_shell: Option<ShellRequirement>,
    #[serde(default)]
    pub observed_shell: Option<ShellObservation>,
    #[serde(default)]
    #[schemars(extend("pattern" = "^[0-9A-Fa-f]{64}$"))]
    pub resolution_before_sha256: Option<String>,
    #[serde(default)]
    #[schemars(extend("pattern" = "^[0-9A-Fa-f]{64}$"))]
    pub resolution_after_sha256: Option<String>,
}

#[derive(Debug, Clone, Deserialize, JsonSchema)]
#[schemars(inline)]
#[serde(deny_unknown_fields)]
pub struct ShellRequirement {
    pub family: String,
    #[serde(default)]
    pub minimum_major: Option<u32>,
    #[serde(default)]
    pub minimum_minor: Option<u32>,
}

#[derive(Debug, Clone, Deserialize, JsonSchema)]
#[schemars(inline)]
#[serde(deny_unknown_fields)]
pub struct ShellObservation {
    pub family: String,
    #[serde(default)]
    pub major: Option<u32>,
    #[serde(default)]
    pub minor: Option<u32>,
}
#[derive(Debug, Clone, Serialize, JsonSchema)]
pub struct DiagnosisResult {
    pub schema_version: u32,
    pub failure_class: String,
    pub confidence: String,
    pub evidence: Vec<DiagnosisEvidence>,
    pub next_action: DiagnosisAction,
}

#[derive(Debug, Clone, Serialize, JsonSchema)]
#[schemars(inline)]
pub struct DiagnosisEvidence {
    pub code: String,
    pub detail: String,
}

#[derive(Debug, Clone, Serialize, JsonSchema)]
#[schemars(inline)]
pub struct DiagnosisAction {
    pub kind: String,
    pub guidance: String,
}

pub fn diagnose_failure(request: DiagnoseFailureRequest) -> Result<DiagnosisResult, String> {
    validate_request(&request)?;

    if request.desktop_sandbox_signal {
        return Ok(result(
            "DESKTOP_SANDBOX_BOUNDARY",
            "high",
            "desktop_sandbox_signal",
            "Caller supplied an explicit Desktop/sandbox boundary signal.",
            "inspect_desktop_boundary",
            "Keep the failure attributed to the Desktop/sandbox boundary; do not weaken ACLs, sandboxing, approvals, or global security settings.",
        ));
    }
    if request.timed_out {
        return Ok(result(
            "TIMEOUT_CANCELLATION",
            "high",
            "timed_out",
            "The observed command boundary reported a timeout.",
            "verify_timeout_owner",
            "Identify which layer timed out, verify the owned process state, and keep timeout/cancellation separate from task completion.",
        ));
    }

    if let (Some(exit_code), Some(post_condition)) = (request.exit_code, request.post_condition) {
        let command_succeeded = exit_code == 0;
        if command_succeeded != post_condition {
            return Ok(result(
                "POST_CONDITION_MISMATCH",
                "high",
                "command_task_outcome_disagree",
                "Command exit status and the explicit task post-condition disagree.",
                "trust_post_condition_separately",
                "Preserve both facts. Do not infer task completion from exit code alone; inspect the failed or satisfied post-condition before any repair.",
            ));
        }
    }

    if hashes_differ(
        request.resolution_before_sha256.as_deref(),
        request.resolution_after_sha256.as_deref(),
    ) {
        return Ok(result(
            "ENVIRONMENT_STALENESS",
            "high",
            "critical_resolution_changed",
            "A declared critical executable resolved to a different identity across an environment boundary.",
            "refresh_environment_digest",
            "Recompute the bounded environment digest and reason from the new executable identity instead of reusing stale resolution assumptions.",
        ));
    }
    if hashes_differ(
        request.expected_cwd_sha256.as_deref(),
        request.actual_cwd_sha256.as_deref(),
    ) {
        return Ok(result(
            "CWD_PATH_IDENTITY",
            "high",
            "cwd_identity_mismatch",
            "Expected and observed working-directory identities differ.",
            "bind_cwd_explicitly",
            "Bind the intended working directory explicitly and re-evaluate relative paths against that identity before searching or moving files.",
        ));
    }

    if shell_mismatch(request.required_shell.as_ref(), request.observed_shell.as_ref()) {
        return Ok(result(
            "SHELL_VERSION_MISMATCH",
            "high",
            "shell_requirement_mismatch",
            "The observed shell family/version does not satisfy the declared requirement.",
            "select_compatible_shell",
            "Use a shell that satisfies the declared capability requirement or choose syntax supported by the observed shell; do not retry unchanged across shell families.",
        ));
    }

    if request.parser_or_binding_failure
        && request.nested_command_boundary
        && request.literal_dollar_expected
    {
        return Ok(result(
            "QUOTING_EXPANSION",
            "high",
            "nested_literal_expansion_risk",
            "A parser/binding failure occurred across a nested command boundary where a literal dollar token was expected.",
            "replace_nested_string_boundary",
            "Prefer structured argv for native commands or an explicit PowerShell script boundary instead of adding a universal escape rule.",
        ));
    }
    if stderr_indicates_desktop_boundary(request.stderr_excerpt.as_deref()) {
        return Ok(result(
            "DESKTOP_SANDBOX_BOUNDARY",
            "medium",
            "stderr_desktop_boundary_pattern",
            "The bounded stderr excerpt contains a known access/sandbox boundary pattern.",
            "confirm_desktop_boundary",
            "Confirm the failing ownership/permission boundary before changing command construction. Do not weaken ACLs or sandboxing automatically.",
        ));
    }

    if request.native_process && request.exit_code.is_some_and(|code| code != 0) {
        let mut diagnosis = result(
            "NATIVE_PROCESS_OUTCOME",
            "medium",
            "native_nonzero_exit",
            "A caller-declared native process exited non-zero.",
            "inspect_native_outcome",
            "Keep exit code, stdout, stderr, and task post-condition separate; use the program-specific evidence before choosing a repair.",
        );
        if request.stdout_excerpt.as_deref().is_some_and(|value| !value.is_empty()) {
            diagnosis.evidence.push(DiagnosisEvidence {
                code: "stdout_present".to_owned(),
                detail: "A bounded stdout excerpt was supplied.".to_owned(),
            });
        }
        if request.stderr_excerpt.as_deref().is_some_and(|value| !value.is_empty()) {
            diagnosis.evidence.push(DiagnosisEvidence {
                code: "stderr_present".to_owned(),
                detail: "A bounded stderr excerpt was supplied.".to_owned(),
            });
        }
        return Ok(diagnosis);
    }

    Ok(result(
        "UNKNOWN",
        "low",
        "insufficient_specific_evidence",
        "The supplied facts do not support a safer specific classification.",
        "collect_minimal_evidence",
        "Collect only the missing shell/cwd/resolution/exit/post-condition facts tied to the failed boundary, then classify again.",
    ))
}
fn validate_request(request: &DiagnoseFailureRequest) -> Result<(), String> {
    for (name, value) in [
        ("stdout_excerpt", request.stdout_excerpt.as_deref()),
        ("stderr_excerpt", request.stderr_excerpt.as_deref()),
    ] {
        if value.is_some_and(|text| text.len() > MAX_EXCERPT_BYTES) {
            return Err(format!("{name} exceeds {MAX_EXCERPT_BYTES} bytes"));
        }
    }

    for (name, value) in [
        ("expected_cwd_sha256", request.expected_cwd_sha256.as_deref()),
        ("actual_cwd_sha256", request.actual_cwd_sha256.as_deref()),
        (
            "resolution_before_sha256",
            request.resolution_before_sha256.as_deref(),
        ),
        (
            "resolution_after_sha256",
            request.resolution_after_sha256.as_deref(),
        ),
    ] {
        if let Some(hash) = value {
            validate_sha256(name, hash)?;
        }
    }
    Ok(())
}

fn validate_sha256(name: &str, value: &str) -> Result<(), String> {
    if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err(format!("{name} must be a 64-character hexadecimal SHA-256"));
    }
    Ok(())
}
fn hashes_differ(before: Option<&str>, after: Option<&str>) -> bool {
    matches!((before, after), (Some(left), Some(right)) if left != right)
}

fn shell_mismatch(
    required: Option<&ShellRequirement>,
    observed: Option<&ShellObservation>,
) -> bool {
    let (Some(required), Some(observed)) = (required, observed) else {
        return false;
    };
    if !required.family.eq_ignore_ascii_case(&observed.family) {
        return true;
    }

    let Some(required_major) = required.minimum_major else {
        return false;
    };
    let Some(observed_major) = observed.major else {
        return true;
    };
    if observed_major != required_major {
        return observed_major < required_major;
    }

    let required_minor = required.minimum_minor.unwrap_or(0);
    observed.minor.unwrap_or(0) < required_minor
}

fn stderr_indicates_desktop_boundary(stderr: Option<&str>) -> bool {
    let Some(stderr) = stderr else {
        return false;
    };
    let text = stderr.to_ascii_lowercase();
    [
        "access is denied",
        "access denied",
        "eperm",
        "createprocessasuserw",
        "sandbox helper",
        "operation not permitted",
    ]
    .iter()
    .any(|needle| text.contains(needle))
}
fn result(
    failure_class: &str,
    confidence: &str,
    evidence_code: &str,
    evidence_detail: &str,
    action_kind: &str,
    guidance: &str,
) -> DiagnosisResult {
    DiagnosisResult {
        schema_version: 1,
        failure_class: failure_class.to_owned(),
        confidence: confidence.to_owned(),
        evidence: vec![DiagnosisEvidence {
            code: evidence_code.to_owned(),
            detail: evidence_detail.to_owned(),
        }],
        next_action: DiagnosisAction {
            kind: action_kind.to_owned(),
            guidance: guidance.to_owned(),
        },
    }
}
