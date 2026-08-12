use std::{
    env,
    fs::{self, File},
    io::Read,
    path::{Path, PathBuf},
};

use rmcp::schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

const MAX_CHECKS: usize = 32;
const MAX_PATH_BYTES: usize = 32_768;
const MAX_FILE_HASH_BYTES: u64 = 64 * 1024 * 1024;

#[derive(Debug, Clone, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct VerifyResultRequest {
    #[serde(default)]
    pub command_exit_code: Option<i32>,
    #[serde(default)]
    #[schemars(extend("maxLength" = 32768))]
    pub cwd: Option<String>,
    #[serde(default)]
    pub mode: VerificationMode,
    #[schemars(length(min = 1, max = 32))]
    pub checks: Vec<VerificationCheck>,
}

#[derive(Debug, Clone, Copy, Default, Deserialize, Serialize, JsonSchema)]
#[schemars(inline)]
#[serde(rename_all = "snake_case")]
pub enum VerificationMode {
    #[default]
    All,
    Any,
}
#[derive(Debug, Clone, Deserialize, JsonSchema)]
#[schemars(inline)]
#[serde(tag = "kind", rename_all = "snake_case", deny_unknown_fields)]
pub enum VerificationCheck {
    FileExists {
        #[schemars(extend("maxLength" = 32768))]
        path: String,
    },
    FileAbsent {
        #[schemars(extend("maxLength" = 32768))]
        path: String,
    },
    DirectoryExists {
        #[schemars(extend("maxLength" = 32768))]
        path: String,
    },
    FileSha256 {
        #[schemars(extend("maxLength" = 32768))]
        path: String,
        #[schemars(extend("pattern" = "^[0-9A-Fa-f]{64}$"))]
        expected_sha256: String,
    },
    FileSize {
        #[schemars(extend("maxLength" = 32768))]
        path: String,
        #[serde(default)]
        min_bytes: Option<u64>,
        #[serde(default)]
        max_bytes: Option<u64>,
    },
}

#[derive(Debug, Clone, Serialize, JsonSchema)]
pub struct VerificationResult {
    pub schema_version: u32,
    pub command_exit_code: Option<i32>,
    pub command_succeeded: Option<bool>,
    pub task_succeeded: bool,
    pub mode: VerificationMode,
    pub checks: Vec<VerificationCheckResult>,
}
#[derive(Debug, Clone, Serialize, JsonSchema)]
pub struct VerificationCheckResult {
    pub index: u32,
    pub kind: String,
    pub passed: bool,
    pub status: String,
    pub path_sha256: String,
    pub observed_exists: Option<bool>,
    pub observed_is_directory: Option<bool>,
    pub observed_size_bytes: Option<u64>,
    pub observed_sha256: Option<String>,
    pub error_kind: Option<String>,
}

pub fn verify_result(request: VerifyResultRequest) -> Result<VerificationResult, String> {
    validate_request(&request)?;
    let base = request
        .cwd
        .as_deref()
        .map(PathBuf::from)
        .unwrap_or_else(|| env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));

    let mut results = Vec::with_capacity(request.checks.len());
    for (index, check) in request.checks.iter().enumerate() {
        results.push(evaluate_check(index as u32, &base, check));
    }

    let task_succeeded = match request.mode {
        VerificationMode::All => results.iter().all(|result| result.passed),
        VerificationMode::Any => results.iter().any(|result| result.passed),
    };
    Ok(VerificationResult {
        schema_version: 1,
        command_exit_code: request.command_exit_code,
        command_succeeded: request.command_exit_code.map(|code| code == 0),
        task_succeeded,
        mode: request.mode,
        checks: results,
    })
}

fn validate_request(request: &VerifyResultRequest) -> Result<(), String> {
    if request.checks.is_empty() {
        return Err("checks must contain at least one explicit post-condition".to_owned());
    }
    if request.checks.len() > MAX_CHECKS {
        return Err(format!("checks exceeds limit of {MAX_CHECKS}"));
    }
    if let Some(cwd) = request.cwd.as_deref() {
        validate_path_text("cwd", cwd)?;
    }

    for check in &request.checks {
        match check {
            VerificationCheck::FileExists { path }
            | VerificationCheck::FileAbsent { path }
            | VerificationCheck::DirectoryExists { path } => validate_path_text("path", path)?,
            VerificationCheck::FileSha256 {
                path,
                expected_sha256,
            } => {
                validate_path_text("path", path)?;
                validate_sha256(expected_sha256)?;
            }
            VerificationCheck::FileSize {
                path,
                min_bytes,
                max_bytes,
            } => {
                validate_path_text("path", path)?;
                if matches!((min_bytes, max_bytes), (Some(min), Some(max)) if min > max) {
                    return Err("file_size min_bytes cannot exceed max_bytes".to_owned());
                }
            }
        }
    }
    Ok(())
}

fn validate_path_text(name: &str, value: &str) -> Result<(), String> {
    if value.is_empty() || value.len() > MAX_PATH_BYTES || value.contains('\0') {
        return Err(format!("{name} must be non-empty, bounded, and NUL-free"));
    }
    Ok(())
}

fn validate_sha256(value: &str) -> Result<(), String> {
    if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err("expected_sha256 must be a 64-character hexadecimal SHA-256".to_owned());
    }
    Ok(())
}
fn evaluate_check(index: u32, base: &Path, check: &VerificationCheck) -> VerificationCheckResult {
    match check {
        VerificationCheck::FileExists { path } => {
            let resolved = resolve_path(base, path);
            let metadata = fs::metadata(&resolved);
            match metadata {
                Ok(metadata) => check_result(
                    index,
                    "file_exists",
                    metadata.is_file(),
                    &resolved,
                    Some(true),
                    Some(metadata.is_dir()),
                    Some(metadata.len()),
                    None,
                    None,
                ),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => check_result(
                    index,
                    "file_exists",
                    false,
                    &resolved,
                    Some(false),
                    None,
                    None,
                    None,
                    None,
                ),
                Err(error) => error_result(index, "file_exists", &resolved, &error),
            }
        }
        VerificationCheck::FileAbsent { path } => {
            let resolved = resolve_path(base, path);
            let metadata = fs::metadata(&resolved);
            match metadata {
                Ok(metadata) => check_result(
                    index,
                    "file_absent",
                    false,
                    &resolved,
                    Some(true),
                    Some(metadata.is_dir()),
                    Some(metadata.len()),
                    None,
                    None,
                ),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => check_result(
                    index,
                    "file_absent",
                    true,
                    &resolved,
                    Some(false),
                    None,
                    None,
                    None,
                    None,
                ),
                Err(error) => error_result(index, "file_absent", &resolved, &error),
            }
        }
        VerificationCheck::DirectoryExists { path } => {
            let resolved = resolve_path(base, path);
            let metadata = fs::metadata(&resolved);
            match metadata {
                Ok(metadata) => check_result(
                    index,
                    "directory_exists",
                    metadata.is_dir(),
                    &resolved,
                    Some(true),
                    Some(metadata.is_dir()),
                    Some(metadata.len()),
                    None,
                    None,
                ),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => check_result(
                    index,
                    "directory_exists",
                    false,
                    &resolved,
                    Some(false),
                    None,
                    None,
                    None,
                    None,
                ),
                Err(error) => error_result(index, "directory_exists", &resolved, &error),
            }
        }
        VerificationCheck::FileSha256 {
            path,
            expected_sha256,
        } => {
            let resolved = resolve_path(base, path);
            match hash_file(&resolved) {
                Ok(observed) => check_result(
                    index,
                    "file_sha256",
                    observed.eq_ignore_ascii_case(expected_sha256),
                    &resolved,
                    Some(true),
                    Some(false),
                    fs::metadata(&resolved).ok().map(|metadata| metadata.len()),
                    Some(observed),
                    None,
                ),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => check_result(
                    index,
                    "file_sha256",
                    false,
                    &resolved,
                    Some(false),
                    None,
                    None,
                    None,
                    None,
                ),
                Err(error) => error_result(index, "file_sha256", &resolved, &error),
            }
        }
        VerificationCheck::FileSize {
            path,
            min_bytes,
            max_bytes,
        } => {
            let resolved = resolve_path(base, path);
            match fs::metadata(&resolved) {
                Ok(metadata) => {
                    let size = metadata.len();
                    let min_ok = min_bytes.is_none_or(|min| size >= min);
                    let max_ok = max_bytes.is_none_or(|max| size <= max);
                    check_result(
                        index,
                        "file_size",
                        metadata.is_file() && min_ok && max_ok,
                        &resolved,
                        Some(true),
                        Some(metadata.is_dir()),
                        Some(size),
                        None,
                        None,
                    )
                }
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => check_result(
                    index,
                    "file_size",
                    false,
                    &resolved,
                    Some(false),
                    None,
                    None,
                    None,
                    None,
                ),
                Err(error) => error_result(index, "file_size", &resolved, &error),
            }
        }
    }
}
#[allow(clippy::too_many_arguments)]
fn check_result(
    index: u32,
    kind: &str,
    passed: bool,
    path: &Path,
    observed_exists: Option<bool>,
    observed_is_directory: Option<bool>,
    observed_size_bytes: Option<u64>,
    observed_sha256: Option<String>,
    error_kind: Option<String>,
) -> VerificationCheckResult {
    VerificationCheckResult {
        index,
        kind: kind.to_owned(),
        passed,
        status: if error_kind.is_some() { "error" } else { "evaluated" }.to_owned(),
        path_sha256: hash_path(path),
        observed_exists,
        observed_is_directory,
        observed_size_bytes,
        observed_sha256,
        error_kind,
    }
}

fn error_result(
    index: u32,
    kind: &str,
    path: &Path,
    error: &std::io::Error,
) -> VerificationCheckResult {
    check_result(
        index,
        kind,
        false,
        path,
        None,
        None,
        None,
        None,
        Some(format!("{:?}", error.kind())),
    )
}

fn resolve_path(base: &Path, input: &str) -> PathBuf {
    let path = Path::new(input);
    let joined = if path.is_absolute() {
        path.to_path_buf()
    } else {
        base.join(path)
    };
    fs::canonicalize(&joined).unwrap_or(joined)
}

fn hash_path(path: &Path) -> String {
    let text = path.to_string_lossy().replace('/', "\\");
    let normalized = if cfg!(windows) {
        text.to_ascii_lowercase()
    } else {
        text
    };
    sha256_hex(normalized.as_bytes())
}
fn hash_file(path: &Path) -> std::io::Result<String> {
    let file = File::open(path)?;
    if file.metadata()?.len() > MAX_FILE_HASH_BYTES {
        return Err(std::io::Error::new(
            std::io::ErrorKind::FileTooLarge,
            "file exceeds 64 MiB SHA-256 limit",
        ));
    }

    let mut file = file.take(MAX_FILE_HASH_BYTES + 1);
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    let mut total_read = 0_u64;
    loop {
        let read = file.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        total_read += read as u64;
        if total_read > MAX_FILE_HASH_BYTES {
            return Err(std::io::Error::new(
                std::io::ErrorKind::FileTooLarge,
                "file exceeds 64 MiB SHA-256 limit",
            ));
        }
        hasher.update(&buffer[..read]);
    }
    Ok(digest_to_hex(hasher.finalize().as_slice()))
}

fn sha256_hex(bytes: &[u8]) -> String {
    digest_to_hex(Sha256::digest(bytes).as_slice())
}

fn digest_to_hex(bytes: &[u8]) -> String {
    let mut output = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        use std::fmt::Write as _;
        let _ = write!(&mut output, "{byte:02x}");
    }
    output
}
