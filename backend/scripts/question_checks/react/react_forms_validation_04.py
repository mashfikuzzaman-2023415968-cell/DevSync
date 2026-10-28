from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: F401


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    out = ctx.node(
        PRELUDE
        + """
function Total() {
  const [qty, setQty] = useState('1');
  return h('div', null, h('input', { type: 'number', value: qty, onChange: (e) => setQty(e.target.value) }), h('p', null, qty + 1));
}
const { c } = mount(h(Total));
typeInto(c.querySelector('input'), '2');
console.log(c.querySelector('p').textContent);
"""
    )
    ctx.expect_only(q, out)
