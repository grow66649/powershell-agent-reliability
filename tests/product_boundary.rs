use std::{fs, path::PathBuf};

fn source_text() -> String {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("src");
    let mut combined = String::new();
    for entry in fs::read_dir(root).expect("read src") {
        let path = entry.expect("src entry").path();
        if path.extension().and_then(|value| value.to_str()) == Some("rs") {
            combined.push_str(&fs::read_to_string(path).expect("read source"));
        }
    }
    combined
}

#[test]
fn product_source_does_not_grow_a_command_runner_or_network_transport() {
    let source = source_text();
    for forbidden in [
        "std::process::Command",
        "tokio::process::Command",
        "Command::new(",
        "TcpStream",
        "TcpListener",
        "UdpSocket",
        "reqwest",
        "ureq",
    ] {
        assert!(!source.contains(forbidden), "forbidden product surface: {forbidden}");
    }
}

#[test]
fn product_source_does_not_dump_or_mutate_the_process_environment() {
    let source = source_text();
    for forbidden in [
        "env::vars()",
        "env::vars_os()",
        "std::env::vars()",
        "std::env::vars_os()",
        "env::set_var(",
        "env::remove_var(",
    ] {
        assert!(!source.contains(forbidden), "forbidden environment surface: {forbidden}");
    }

    let cargo = fs::read_to_string(
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("Cargo.toml"),
    )
    .expect("read Cargo.toml");
    assert!(cargo.contains("transport-io"));
    assert!(!cargo.contains("transport-streamable-http"));
}
