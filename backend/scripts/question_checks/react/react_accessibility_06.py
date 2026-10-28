from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: F401


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    r = js(
        ctx,
        """
const { getByLabelText } = require('@testing-library/dom');
const variants = {
  htmlFor: () => [h('label', { htmlFor: 'email' }, 'Email'), h('input', { id: 'email', type: 'email', name: 'email' })],
  nameAttr: () => [h('label', null, 'Email'), h('input', { id: 'email', type: 'email', name: 'Email' })],
  typeText: () => [h('label', null, 'Email'), h('input', { id: 'email', type: 'text', name: 'email' })],
  roleLabel: () => [h('label', { role: 'label' }, 'Email'), h('input', { id: 'email', type: 'email', name: 'email' })],
  original: () => [h('label', null, 'Email'), h('input', { id: 'email', type: 'email', name: 'email' })],
};
const res = {};
for (const [name, make] of Object.entries(variants)) {
  const { c } = mount(h('div', null, ...make()));
  try { getByLabelText(c, 'Email'); res[name] = true; } catch (e) { res[name] = false; }
}
console.log(JSON.stringify(res));
""",
    )
    assert r["original"] is False, r
    verify(
        q,
        {
            "Change the label to <label htmlFor": r["htmlFor"],
            'Change name="email"': r["nameAttr"],
            'Add type="text"': r["typeText"],
            'Add role="label"': r["roleLabel"],
        },
    )
