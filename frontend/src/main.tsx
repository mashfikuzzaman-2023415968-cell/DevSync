import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { applyStoredPreferences } from "./design/preferences";
import { installNonce } from "./lib/nonce";
import { reportClientError } from "./lib/reportError";
import "./index.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("Root element #root is missing from index.html");
}
applyStoredPreferences();
// Errors outside React's tree (event handlers, promises) are reported too (spec §15.7).
window.addEventListener("error", (e) => {
  void reportClientError(e.error ?? e.message, "unhandled");
});
window.addEventListener("unhandledrejection", (e) => {
  void reportClientError(e.reason, "unhandled");
});
const nonce = installNonce();
createRoot(root).render(
  <StrictMode>
    <App nonce={nonce} />
  </StrictMode>,
);
