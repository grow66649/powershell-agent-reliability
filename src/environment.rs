use std::{
    collections::BTreeMap,
    env,
    fs::{self, File},
    io::Read,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

use rmcp::schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

const MAX_CRITICAL_EXECUTABLES: usize = 16;
const MAX_ENV_DELTA_KEYS: usize = 32;
const MAX_TEXT_BYTES: usize = 32_768;
const MAX_FILE_HASH_BYTES: u64 = 64 * 1024 * 1024;

#[derive(Debug, Clone, Deserialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct InspectEnvironmentRequest {
    #[serde(default)]
    #[schemars(extend("maxLength" = 32768))]
    pub shell_executable: Option<String>,
    #[serde(default)]
    #[schemars(extend("maxLength" = 32768))]
    pub cwd: Option<String>,
    #[serde(default)]
    #[schemars(length(max = 16), inner(length(max = 32768)))]
    pub critical_executables: Vec<String>,
    #[serde(default)]
    #[schemars(extend("maxProperties" = 32))]
    pub task_env_delta: BTreeMap<String, String>,
}
#[derive(Debug, Clone, Serialize, JsonSchema)]
pub struct EnvironmentDigest {
    pub schema_version: u32,
    pub observed_at_unix_ms: u64,
    pub shell: Option<ShellIdentity>,
    pub os: OsIdentity,
    pub cwd: CwdIdentity,
    pub path_fingerprint_sha256: String,
    pub critical_executables: Vec<ExecutableIdentity>,
    pub task_env_delta: Vec<EnvDeltaDigest>,
}

#[derive(Debug, Clone, Serialize, JsonSchema)]
#[schemars(inline)]
pub struct ShellIdentity {
    pub family: String,
    pub version: Option<String>,
    pub architecture: String,
    pub resolution_status: String,
    pub resolved_path_sha256: Option<String>,
}

#[derive(Debug, Clone, Serialize, JsonSchema)]
#[schemars(inline)]
pub struct OsIdentity {
    pub family: String,
    pub build: Option<String>,
    pub process_architecture: String,
}
#[derive(Debug, Clone, Serialize, JsonSchema)]
#[schemars(inline)]
pub struct CwdIdentity {
    pub exists: bool,
    pub normalized_path_sha256: String,
}

#[derive(Debug, Clone, Serialize, JsonSchema)]
#[schemars(inline)]
pub struct ExecutableIdentity {
    pub name: String,
    pub resolution_status: String,
    pub source_class: String,
    pub resolved_path_sha256: Option<String>,
    pub version: Option<String>,
    pub file_sha256: Option<String>,
    pub architecture: Option<String>,
}

#[derive(Debug, Clone, Serialize, JsonSchema)]
#[schemars(inline)]
pub struct EnvDeltaDigest {
    pub key: String,
    pub value_sha256: String,
}

#[derive(Debug)]
struct ResolvedExecutable {
    path: PathBuf,
    source_class: &'static str,
}
pub fn inspect_environment(request: InspectEnvironmentRequest) -> Result<EnvironmentDigest, String> {
    validate_request(&request)?;

    let cwd_input = request
        .cwd
        .map(PathBuf::from)
        .unwrap_or_else(|| env::current_dir().unwrap_or_else(|_| PathBuf::from(".")));
    let cwd_exists = cwd_input.exists();
    let cwd_normalized = normalize_path(&cwd_input);
    let path_value = env::var_os("PATH").unwrap_or_default();

    let shell = request
        .shell_executable
        .as_deref()
        .map(shell_identity)
        .transpose()?;

    let mut critical_executables = Vec::with_capacity(request.critical_executables.len());
    for requested in &request.critical_executables {
        critical_executables.push(executable_identity(requested)?);
    }

    let task_env_delta = request
        .task_env_delta
        .into_iter()
        .map(|(key, value)| EnvDeltaDigest {
            key,
            value_sha256: sha256_hex(value.as_bytes()),
        })
        .collect();
    Ok(EnvironmentDigest {
        schema_version: 1,
        observed_at_unix_ms: unix_time_ms(),
        shell,
        os: os_identity(),
        cwd: CwdIdentity {
            exists: cwd_exists,
            normalized_path_sha256: sha256_hex(normalize_for_hash(&cwd_normalized).as_bytes()),
        },
        path_fingerprint_sha256: sha256_hex(path_value.to_string_lossy().as_bytes()),
        critical_executables,
        task_env_delta,
    })
}

fn validate_request(request: &InspectEnvironmentRequest) -> Result<(), String> {
    if request.critical_executables.len() > MAX_CRITICAL_EXECUTABLES {
        return Err(format!(
            "critical_executables exceeds limit of {MAX_CRITICAL_EXECUTABLES}"
        ));
    }
    if request.task_env_delta.len() > MAX_ENV_DELTA_KEYS {
        return Err(format!("task_env_delta exceeds limit of {MAX_ENV_DELTA_KEYS}"));
    }

    for (name, value) in [
        ("shell_executable", request.shell_executable.as_deref()),
        ("cwd", request.cwd.as_deref()),
    ] {
        if value.is_some_and(|text| text.len() > MAX_TEXT_BYTES || text.contains('\0')) {
            return Err(format!("{name} must be bounded and NUL-free"));
        }
    }

    if request.critical_executables.iter().any(|name| {
        name.is_empty() || name.len() > MAX_TEXT_BYTES || name.contains('\0')
    }) {
        return Err("critical executable names must be non-empty, bounded, and NUL-free".to_owned());
    }

    for (key, value) in &request.task_env_delta {
        if key.is_empty()
            || key.len() > MAX_TEXT_BYTES
            || key.contains('=')
            || key.contains('\0')
            || value.len() > MAX_TEXT_BYTES
            || value.contains('\0')
        {
            return Err("task_env_delta entries must be bounded and valid".to_owned());
        }
    }
    Ok(())
}
fn shell_identity(requested: &str) -> Result<ShellIdentity, String> {
    let resolved = resolve_executable(requested);
    let family = shell_family(
        resolved
            .as_ref()
            .map(|item| item.path.as_path())
            .unwrap_or_else(|| Path::new(requested)),
    );

    Ok(match resolved {
        Some(item) => ShellIdentity {
            family,
            version: file_version(&item.path),
            architecture: pe_architecture(&item.path).unwrap_or_else(|| "unknown".to_owned()),
            resolution_status: "resolved".to_owned(),
            resolved_path_sha256: Some(hash_path(&item.path)),
        },
        None => ShellIdentity {
            family,
            version: None,
            architecture: "unknown".to_owned(),
            resolution_status: "not_found".to_owned(),
            resolved_path_sha256: None,
        },
    })
}
fn executable_identity(requested: &str) -> Result<ExecutableIdentity, String> {
    let display_name = Path::new(requested)
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("<path>")
        .to_owned();

    let Some(item) = resolve_executable(requested) else {
        return Ok(ExecutableIdentity {
            name: display_name,
            resolution_status: "not_found".to_owned(),
            source_class: "not_found".to_owned(),
            resolved_path_sha256: None,
            version: None,
            file_sha256: None,
            architecture: None,
        });
    };

    let file_hash = fs::metadata(&item.path)
        .ok()
        .filter(|metadata| metadata.is_file() && metadata.len() <= MAX_FILE_HASH_BYTES)
        .and_then(|_| hash_file(&item.path).ok());

    Ok(ExecutableIdentity {
        name: display_name,
        resolution_status: "resolved".to_owned(),
        source_class: item.source_class.to_owned(),
        resolved_path_sha256: Some(hash_path(&item.path)),
        version: file_version(&item.path),
        file_sha256: file_hash,
        architecture: pe_architecture(&item.path),
    })
}
fn resolve_executable(requested: &str) -> Option<ResolvedExecutable> {
    let path = Path::new(requested);
    if path.is_absolute() || requested.contains('\\') || requested.contains('/') {
        let candidate = normalize_path(path);
        return candidate.is_file().then_some(ResolvedExecutable {
            path: candidate,
            source_class: "explicit_path",
        });
    }

    let mut names = vec![requested.to_owned()];
    if path.extension().is_none() {
        let pathext = env::var("PATHEXT")
            .unwrap_or_else(|_| ".COM;.EXE;.BAT;.CMD".to_owned());
        for extension in pathext.split(';').filter(|item| !item.is_empty()) {
            names.push(format!("{requested}{extension}"));
        }
    }

    let search_path = env::var_os("PATH")?;
    for directory in env::split_paths(&search_path) {
        for name in &names {
            let candidate = directory.join(name);
            if candidate.is_file() {
                return Some(ResolvedExecutable {
                    path: normalize_path(&candidate),
                    source_class: "path",
                });
            }
        }
    }
    None
}
fn normalize_path(path: &Path) -> PathBuf {
    if let Ok(canonical) = fs::canonicalize(path) {
        return canonical;
    }
    if path.is_absolute() {
        return path.to_path_buf();
    }
    env::current_dir()
        .map(|cwd| cwd.join(path))
        .unwrap_or_else(|_| path.to_path_buf())
}

fn normalize_for_hash(path: &Path) -> String {
    let text = path.to_string_lossy().replace('/', "\\");
    if cfg!(windows) {
        text.to_ascii_lowercase()
    } else {
        text
    }
}

fn hash_path(path: &Path) -> String {
    sha256_hex(normalize_for_hash(path).as_bytes())
}

fn sha256_hex(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    let mut output = String::with_capacity(digest.len() * 2);
    for byte in digest {
        use std::fmt::Write as _;
        let _ = write!(&mut output, "{byte:02x}");
    }
    output
}
fn hash_file(path: &Path) -> std::io::Result<String> {
    let mut file = File::open(path)?;
    let mut hasher = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let read = file.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    let digest = hasher.finalize();
    let mut output = String::with_capacity(digest.len() * 2);
    for byte in digest {
        use std::fmt::Write as _;
        let _ = write!(&mut output, "{byte:02x}");
    }
    Ok(output)
}

fn shell_family(path: &Path) -> String {
    match path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase()
        .as_str()
    {
        "powershell.exe" => "WindowsPowerShell".to_owned(),
        "pwsh.exe" | "pwsh" => "PowerShell".to_owned(),
        _ => "Unknown".to_owned(),
    }
}
fn pe_architecture(path: &Path) -> Option<String> {
    let mut file = File::open(path).ok()?;
    let mut dos = [0_u8; 64];
    file.read_exact(&mut dos).ok()?;
    if &dos[..2] != b"MZ" {
        return None;
    }
    let pe_offset = u32::from_le_bytes(dos[60..64].try_into().ok()?) as u64;
    use std::io::{Seek, SeekFrom};
    file.seek(SeekFrom::Start(pe_offset)).ok()?;
    let mut header = [0_u8; 6];
    file.read_exact(&mut header).ok()?;
    if &header[..4] != b"PE\0\0" {
        return None;
    }
    let machine = u16::from_le_bytes([header[4], header[5]]);
    Some(
        match machine {
            0x014c => "x86",
            0x8664 => "x86_64",
            0xaa64 => "arm64",
            0x01c4 => "arm",
            _ => "unknown",
        }
        .to_owned(),
    )
}

fn unix_time_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis().min(u64::MAX as u128) as u64)
        .unwrap_or(0)
}
fn os_identity() -> OsIdentity {
    OsIdentity {
        family: env::consts::OS.to_owned(),
        build: windows_build(),
        process_architecture: env::consts::ARCH.to_owned(),
    }
}

#[cfg(windows)]
fn windows_build() -> Option<String> {
    #[repr(C)]
    struct RtlOsVersionInfoW {
        size: u32,
        major: u32,
        minor: u32,
        build: u32,
        platform_id: u32,
        service_pack: [u16; 128],
    }

    #[link(name = "ntdll")]
    unsafe extern "system" {
        fn RtlGetVersion(info: *mut RtlOsVersionInfoW) -> i32;
    }

    let mut info = RtlOsVersionInfoW {
        size: std::mem::size_of::<RtlOsVersionInfoW>() as u32,
        major: 0,
        minor: 0,
        build: 0,
        platform_id: 0,
        service_pack: [0; 128],
    };
    let status = unsafe { RtlGetVersion(&mut info) };
    if status < 0 {
        return None;
    }
    Some(format!("{}.{}.{}", info.major, info.minor, info.build))
}

#[cfg(not(windows))]
fn windows_build() -> Option<String> {
    None
}

#[cfg(windows)]
fn file_version(path: &Path) -> Option<String> {
    use std::{ffi::c_void, os::windows::ffi::OsStrExt, ptr};

    #[repr(C)]
    struct VsFixedFileInfo {
        signature: u32,
        struct_version: u32,
        file_version_ms: u32,
        file_version_ls: u32,
        product_version_ms: u32,
        product_version_ls: u32,
        file_flags_mask: u32,
        file_flags: u32,
        file_os: u32,
        file_type: u32,
        file_subtype: u32,
        file_date_ms: u32,
        file_date_ls: u32,
    }
    #[link(name = "version")]
    unsafe extern "system" {
        fn GetFileVersionInfoSizeW(filename: *const u16, handle: *mut u32) -> u32;
        fn GetFileVersionInfoW(
            filename: *const u16,
            handle: u32,
            length: u32,
            data: *mut c_void,
        ) -> i32;
        fn VerQueryValueW(
            block: *const c_void,
            sub_block: *const u16,
            buffer: *mut *mut c_void,
            length: *mut u32,
        ) -> i32;
    }

    let wide: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
    let mut ignored = 0_u32;
    let size = unsafe { GetFileVersionInfoSizeW(wide.as_ptr(), &mut ignored) };
    if size == 0 {
        return None;
    }
    let mut data = vec![0_u8; size as usize];
    let ok = unsafe {
        GetFileVersionInfoW(wide.as_ptr(), 0, size, data.as_mut_ptr().cast::<c_void>())
    };
    if ok == 0 {
        return None;
    }
    let root: Vec<u16> = "\\".encode_utf16().chain(Some(0)).collect();
    let mut buffer = ptr::null_mut::<c_void>();
    let mut length = 0_u32;
    let ok = unsafe {
        VerQueryValueW(
            data.as_ptr().cast::<c_void>(),
            root.as_ptr(),
            &mut buffer,
            &mut length,
        )
    };
    if ok == 0 || buffer.is_null() || length < std::mem::size_of::<VsFixedFileInfo>() as u32 {
        return None;
    }

    let info = unsafe { &*(buffer.cast::<VsFixedFileInfo>()) };
    if info.signature != 0xFEEF04BD {
        return None;
    }
    let major = info.file_version_ms >> 16;
    let minor = info.file_version_ms & 0xffff;
    let build = info.file_version_ls >> 16;
    let revision = info.file_version_ls & 0xffff;
    Some(format!("{major}.{minor}.{build}.{revision}"))
}

#[cfg(not(windows))]
fn file_version(_path: &Path) -> Option<String> {
    None
}

