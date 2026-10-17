import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { applyStoredPreferences } from "./design/preferences";
import { installNonce } from "./lib/nonce";
import "./index.css";

const root = document.getElementById("root");
if (!root) {
  throw new Error("Root element #root is missing from index.html");
}
applyStoredPreferences();
const nonce = installNonce();
createRoot(root).render(
  <StrictMode>
    <App nonce={nonce} />
  </StrictMode>,
);
