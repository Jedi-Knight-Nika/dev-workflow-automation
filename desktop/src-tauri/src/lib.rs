use std::net::TcpStream;
use std::path::PathBuf;
use std::process::Command;
use std::time::Duration;

use tauri::{Emitter, Manager};

const UI_PORT: u16 = 3000;

/// Location of the repo (compose.yaml lives at its root). Override with
/// AEW_REPO_ROOT for machines where the checkout isn't at the default path.
fn repo_root() -> PathBuf {
    if let Ok(path) = std::env::var("AEW_REPO_ROOT") {
        return PathBuf::from(path);
    }

    #[cfg(debug_assertions)]
    {
        // desktop/src-tauri -> repo root, when run via `cargo tauri dev`.
        let dev_root = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..");
        if let Ok(canonical) = dev_root.canonicalize() {
            return canonical;
        }
    }

    PathBuf::from("/Users/nika/Documents/business/dev-workflow-automation")
}

fn port_open(port: u16) -> bool {
    TcpStream::connect_timeout(&([127, 0, 0, 1], port).into(), Duration::from_millis(300)).is_ok()
}

fn start_stack(handle: tauri::AppHandle) {
    let root = repo_root();
    eprintln!("[launcher] repo_root = {}", root.display());

    if !root.join("compose.yaml").is_file() {
        eprintln!("[launcher] compose.yaml missing at {}", root.display());
        let _ = handle.emit(
            "stack-error",
            format!(
                "compose.yaml not found at {}. Set AEW_REPO_ROOT to the repo checkout.",
                root.display()
            ),
        );
        return;
    }

    eprintln!("[launcher] running: docker compose up -d --wait (cwd={})", root.display());
    let output = Command::new("docker")
        .args(["compose", "up", "-d", "--wait"])
        .current_dir(&root)
        .output();

    match output {
        Ok(result) if result.status.success() => {
            eprintln!("[launcher] docker compose up succeeded");
        }
        Ok(result) => {
            let stderr = String::from_utf8_lossy(&result.stderr).to_string();
            eprintln!("[launcher] docker compose up failed (status={:?}): {stderr}", result.status);
            let _ = handle.emit("stack-error", format!("docker compose up failed:\n{stderr}"));
            return;
        }
        Err(err) => {
            eprintln!("[launcher] failed to spawn docker: {err}");
            let _ = handle.emit(
                "stack-error",
                format!("could not run docker compose (is Docker running?): {err}"),
            );
            return;
        }
    }

    // compose --wait only covers services with healthchecks; the frontend
    // container has none, so poll the port before handing off the window.
    let mut ready = false;
    for _ in 0..60 {
        if port_open(UI_PORT) {
            ready = true;
            break;
        }
        std::thread::sleep(Duration::from_millis(500));
    }
    eprintln!("[launcher] port {UI_PORT} ready = {ready}");

    match handle.get_webview_window("main") {
        Some(window) => match format!("http://localhost:{UI_PORT}").parse() {
            Ok(url) => {
                eprintln!("[launcher] navigating main window to {url}");
                if let Err(err) = window.navigate(url) {
                    eprintln!("[launcher] navigate() failed: {err}");
                }
            }
            Err(err) => eprintln!("[launcher] failed to parse URL: {err}"),
        },
        None => eprintln!("[launcher] no webview window labeled 'main' found"),
    }
}

#[tauri::command]
fn frontend_ready(app: tauri::AppHandle) {
    // Frontend calls this only after its event listener is registered,
    // so an early docker-compose failure can never race the splash page's
    // "stack-error" listener and get lost.
    std::thread::spawn(move || start_stack(app));
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![frontend_ready])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
