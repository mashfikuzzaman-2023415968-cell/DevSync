/**
 * Per-response CSP nonce for the few libraries that must add a <style> element at runtime
 * (Radix scroll lock via react-style-singleton; DECISIONS D23). Nginx replaces the
 * placeholder in index.html with the request id and lists it in `style-src`. Scripts never
 * use it. In development the placeholder stays and the dev CSP is relaxed.
 */
import { setNonce } from "get-nonce";

const NONCE_PATTERN = /^[0-9a-f]{32}$/;

export function readNonce(doc: Document = document): string | undefined {
  const value = doc.querySelector('meta[name="csp-nonce"]')?.getAttribute("content") ?? "";
  return NONCE_PATTERN.test(value) ? value : undefined;
}

export function installNonce(doc: Document = document): string | undefined {
  const nonce = readNonce(doc);
  if (nonce) setNonce(nonce);
  return nonce;
}
