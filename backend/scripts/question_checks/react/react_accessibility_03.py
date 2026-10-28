import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: F401


def check(ctx, q):
    r = js(
        ctx,
        """
const { getByRole } = require('@testing-library/dom');
const noop = () => {};
const variants = {
  button: () => h('button', { type: 'button', onClick: noop }, 'Save'),
  tabIndex: () => h('div', { className: 'save', onClick: noop, tabIndex: 0 }, 'Save'),
  ariaLabel: () => h('div', { className: 'save', onClick: noop, 'aria-label': 'Save' }, 'Save'),
  keyDown: () => h('div', { className: 'save', onClick: noop, onKeyDown: noop }, 'Save'),
};
const res = {};
for (const [name, make] of Object.entries(variants)) {
  const { c } = mount(make());
  let isButton = true;
  try { getByRole(c, 'button', { name: 'Save' }); } catch (e) { isButton = false; }
  const el = c.firstChild;
  const focusable = el.tabIndex >= 0;                      // reachable with Tab
  const keys = el.tagName === 'BUTTON' || name === 'keyDown';  // Enter/Space (or Enter) handled
  res[name] = { isButton, focusable, keys };
}
console.log(JSON.stringify(res));
""",
    )
    fixes_both = {k: v["isButton"] and v["focusable"] and v["keys"] for k, v in r.items()}
    assert not any(fixes_both[k] for k in ("tabIndex", "ariaLabel", "keyDown")), r
    verify(
        q,
        {
            'Use <button type="button"': fixes_both["button"],
            "Add tabIndex={0}": fixes_both["tabIndex"],
            'Add aria-label="Save"': fixes_both["ariaLabel"],
            "Add an onKeyDown handler": fixes_both["keyDown"],
        },
    )
