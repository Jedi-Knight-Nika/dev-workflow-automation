const { listen } = window.__TAURI__.event;
const { invoke } = window.__TAURI__.core;

const statusEl = document.getElementById("status");
const hintEl = document.getElementById("hint");

// Register the listener and wait for it to be live before telling Rust to
// start docker compose, so an early failure can't fire before anyone is
// listening for it.
listen("stack-error", (event) => {
  statusEl.textContent = "Failed to start the local stack.";
  hintEl.textContent = event.payload;
  hintEl.style.color = "#e5484d";
}).then(() => invoke("frontend_ready"));
