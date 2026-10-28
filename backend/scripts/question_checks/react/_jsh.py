"""Shared helpers for the React question checks (not a check itself; no question id)."""
import json
import re

PRELUDE = r"""
process.on('uncaughtException', () => {});
const { JSDOM } = require('jsdom');
const dom = new JSDOM('<!doctype html><html><body></body></html>', { pretendToBeVisual: true, url: 'http://localhost/' });
const w = dom.window;
globalThis.window = w; globalThis.document = w.document;
Object.defineProperty(globalThis, 'navigator', { value: w.navigator, configurable: true });
for (const k of ['HTMLElement','HTMLInputElement','Node','Event','MouseEvent','KeyboardEvent','MutationObserver','getComputedStyle']) globalThis[k] = w[k];
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
console.error = () => {}; console.warn = () => {};
const React = require('react');
const h = React.createElement;
const { useState, useEffect, useReducer, useCallback, useMemo } = React;
const { createRoot } = require('react-dom/client');
const act = React.act;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
function mount(el) {
  const c = document.createElement('div'); document.body.appendChild(c);
  const root = createRoot(c); act(() => { root.render(el); }); return { c, root };
}
function mountAsync(el) {  // real scheduler, no act: for effects that fetch / use timers
  globalThis.IS_REACT_ACT_ENVIRONMENT = false;
  const c = document.createElement('div'); document.body.appendChild(c);
  const root = createRoot(c); root.render(el); return { c, root };
}
function click(el) { act(() => { el.dispatchEvent(new w.MouseEvent('click', { bubbles: true, cancelable: true })); }); }
function typeInto(input, val) {
  const set = Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype, 'value').set;
  act(() => { set.call(input, val); input.dispatchEvent(new w.Event('input', { bubbles: true })); });
}
"""


def js(ctx, body):
    """Run `body` after the prelude; the script must console.log one JSON value."""
    out = ctx.node(PRELUDE + body)
    return json.loads(out.strip().splitlines()[-1])


def verify(q, truth):
    """truth maps an option's leading text to whether that option is actually true.

    Asserts every option is covered, the marked one is true and every distractor is false."""
    for i, option in enumerate(q["options"]):
        hits = [v for k, v in truth.items() if option.startswith(k)]
        assert len(hits) == 1, f"option {i} {option!r} matched {len(hits)} truth keys"
        want = i == q["correct_index"]
        assert hits[0] is want, f"option {i} {option!r}: proved {hits[0]}, marked {want}"
